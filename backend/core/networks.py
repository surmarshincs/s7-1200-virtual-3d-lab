# -*- coding: utf-8 -*-
"""声明式梯形图网络 + 能流 DFS 求值器。

同一份 JSON 网络定义三处共用：
    后端：本模块逐周期求值，产生能流表 flow
    前端：渲染梯形图 SVG、按 flow 做能流高亮
    教学：断点按元件 uid 设置/触发

rung 结构（覆盖教学常用梯形图）：
    branches —— 左部并联分支，每个分支是串联元件列表（分支间为或）
    series   —— 右部串联元件（与分支结果为与）
    outputs  —— 输出元件（线圈/置位/复位/MOVE/SEG/TON/CTU/CALL），由能流驱动

元件 kind 一览：
    触点：NO 常开 / NC 常闭 / P 上升沿 / CMP 比较(op: == >= <=)
    输出：COIL 线圈 / SET 置位 / RST 复位 / MOVE 传送 / SEG 七段译码
          TON 通电延时 / CTU 加计数 / CALL 调用 FB 实例

引用（ref）规则：
    数字            —— 立即数
    "#name"/"#a.b"  —— 当前 FB 实例背景数据块（仅在 FB 网络内合法）
    "DB1.field"     —— 指定背景数据块字段
    "I0.0"/"MB10"   —— 全局存储区地址（位/字节/字按地址形式自动判断）
"""
from __future__ import annotations

from typing import Any

from .datablock import DataBlock
from .memory import Memory
from .primitives import CTU_INTERFACE, TON_INTERFACE, ctu_update, seg_decode, ton_update

MAX_CALL_DEPTH = 4  # FB 嵌套调用深度保护


class EvalError(Exception):
    """梯形图求值错误（配置写错时立刻暴露，不静默吞掉）。"""


class EvalContext:
    """一次扫描周期内的求值上下文。"""

    def __init__(
        self,
        mem: Memory,
        dbs: dict[str, DataBlock],
        fb_defs: dict[str, dict],
        dt_ms: int,
        scope_db: DataBlock | None = None,
        scope_key: str = "OB1",
        elem_states: dict[str, Any] | None = None,
        flow: dict[str, int] | None = None,
        breakpoints: dict[str, dict] | None = None,
        drop: set[str] | None = None,
        depth: int = 0,
    ) -> None:
        self.mem = mem
        self.dbs = dbs
        self.fb_defs = fb_defs
        self.dt_ms = dt_ms
        self.scope_db = scope_db            # 当前 FB 实例 DB（OB1 时为 None）
        self.scope_key = scope_key          # "OB1" 或实例名，用于元件状态/断点 uid
        self.elem_states = elem_states if elem_states is not None else {}
        self.flow = flow if flow is not None else {}
        self.breakpoints = breakpoints or {}
        self.drop = drop or set()           # 故障变体：被删除元件的 uid 集合
        self.depth = depth
        self.hit_breakpoints: list[dict] = []  # 本周期命中的断点

    # ------------------------------------------------------------------ 引用读写
    def read(self, ref):
        if isinstance(ref, (int, float)):
            return ref
        if not isinstance(ref, str):
            raise EvalError(f"非法引用: {ref!r}")
        if ref.startswith("#"):
            if self.scope_db is None:
                raise EvalError(f"OB1 中不能使用实例变量 {ref!r}")
            return self.scope_db.get(ref[1:])
        head, _, rest = ref.partition(".")
        if head in self.dbs:
            return self.dbs[head].get(rest) if rest else (_raise(f"DB 引用缺字段: {ref!r}"))
        return self.mem.read(ref)

    def write(self, ref, value) -> None:
        if not isinstance(ref, str):
            raise EvalError(f"写入目标必须是地址: {ref!r}")
        if ref.startswith("#"):
            if self.scope_db is None:
                raise EvalError(f"OB1 中不能使用实例变量 {ref!r}")
            self.scope_db.set(ref[1:], value)
            return
        head, _, rest = ref.partition(".")
        if head in self.dbs:
            if not rest:
                raise EvalError(f"DB 引用缺字段: {ref!r}")
            self.dbs[head].set(rest, value)
            return
        self.mem.write(ref, value)

    # ------------------------------------------------------------------ 元件状态（P 触点等）
    def elem_state(self, uid: str, default=0):
        return self.elem_states.get(f"{self.scope_key}:{uid}", default)

    def set_elem_state(self, uid: str, value) -> None:
        self.elem_states[f"{self.scope_key}:{uid}"] = value


def _raise(msg: str):
    raise EvalError(msg)


# ---------------------------------------------------------------------- 构建 DB
def collect_timer_dbs(networks: list[dict], dbs: dict[str, DataBlock],
                      scope_db: DataBlock | None = None) -> None:
    """扫描网络里的 TON/CTU 元件，自动生成对应背景数据块。"""
    for net in networks:
        for rung in net.get("rungs", []):
            for el in rung.get("outputs", []):
                k = el.get("k")
                if k in ("TON", "CTU"):
                    inst = el["inst"]
                    iface = TON_INTERFACE if k == "TON" else CTU_INTERFACE
                    if inst.startswith("#"):
                        if scope_db is None:
                            raise EvalError(f"OB1 中的 {k} 实例名不能以 # 开头: {inst}")
                        scope_db.ensure_sub(inst[1:], iface)
                    else:
                        if inst not in dbs:
                            dbs[inst] = DataBlock(inst, iface)


# ---------------------------------------------------------------------- 求值
def eval_networks(networks: list[dict], ctx: EvalContext) -> None:
    for net in networks:
        for rung in net.get("rungs", []):
            _eval_rung(net["id"], rung, ctx)


def _eval_rung(net_id: str, rung: dict, ctx: EvalContext) -> None:
    rid = rung["id"]

    # 1. 并联分支（或）：每个分支内部串联（与）
    branch_power = False
    for bi, branch in enumerate(rung.get("branches", [])):
        p = True
        for ei, el in enumerate(branch):
            uid = f"{net_id}.{rid}.b{bi}e{ei}"
            if uid in ctx.drop:
                continue  # 故障变体：元件被拆除，能流直接通过
            cond = _eval_contact(el, uid, ctx)
            glow = p and cond
            ctx.flow[f"{ctx.scope_key}:{uid}"] = 1 if glow else 0
            _check_breakpoint(ctx, uid, el, glow)
            p = p and cond
        branch_power = branch_power or p

    # 2. 右部串联
    power = branch_power if rung.get("branches") else True
    for ei, el in enumerate(rung.get("series", [])):
        uid = f"{net_id}.{rid}.s{ei}"
        if uid in ctx.drop:
            continue
        cond = _eval_contact(el, uid, ctx)
        glow = power and cond
        ctx.flow[f"{ctx.scope_key}:{uid}"] = 1 if glow else 0
        _check_breakpoint(ctx, uid, el, glow)
        power = power and cond

    ctx.flow[f"{ctx.scope_key}:{net_id}.{rid}"] = 1 if power else 0

    # 3. 输出元件
    for oi, el in enumerate(rung.get("outputs", [])):
        uid = f"{net_id}.{rid}.o{oi}"
        if uid in ctx.drop:
            continue
        ctx.flow[f"{ctx.scope_key}:{uid}"] = 1 if power else 0
        _exec_output(el, uid, power, ctx)


def _eval_contact(el: dict, uid: str, ctx: EvalContext) -> bool:
    """触点类元件求值，返回元件本身是否导通。"""
    k = el["k"]
    if k == "NO":
        return bool(ctx.read(el["addr"]))
    if k == "NC":
        return not ctx.read(el["addr"])
    if k == "P":  # 上升沿：本周期为 1 且上周期为 0
        cur = bool(ctx.read(el["addr"]))
        prev = bool(ctx.elem_state(uid, 0))
        ctx.set_elem_state(uid, 1 if cur else 0)
        return cur and not prev
    if k == "CMP":
        a, b = ctx.read(el["a"]), ctx.read(el["b"])
        op = el["op"]
        if op == "==":
            return a == b
        if op == ">=":
            return a >= b
        if op == "<=":
            return a <= b
        raise EvalError(f"不支持的比较运算: {op}")
    raise EvalError(f"元件 {el.get('k')} 不能用作触点")


def _exec_output(el: dict, uid: str, power: bool, ctx: EvalContext) -> None:
    """输出类元件执行。TON/CTU 无论能流与否都要刷新（IN=0 时 ET 清零）。"""
    k = el["k"]
    if k == "COIL":
        ctx.write(el["addr"], 1 if power else 0)
    elif k == "SET":
        if power:
            ctx.write(el["addr"], 1)
    elif k == "RST":
        if power:
            ctx.write(el["addr"], 0)
    elif k == "MOVE":
        if power:
            ctx.write(el["dst"], ctx.read(el["src"]))
    elif k == "SEG":
        if power:
            ctx.write(el["dst"], seg_decode(ctx.read(el["src"])))
    elif k == "TON":
        db = _timer_db(el["inst"], TON_INTERFACE, ctx)
        db.fields["IN"] = 1 if power else 0
        db.fields["PT"] = int(ctx.read(el["pt"])) if "pt" in el else db.fields["PT"]
        ton_update(db.fields, ctx.dt_ms)
    elif k == "CTU":
        db = _timer_db(el["inst"], CTU_INTERFACE, ctx)
        db.fields["CU"] = 1 if power else 0
        if "pv" in el:
            db.fields["PV"] = int(ctx.read(el["pv"]))
        db.fields["R"] = 1 if (el.get("r") is not None and ctx.read(el["r"])) else 0
        ctu_update(db.fields)
    elif k == "SR":
        # SR 锁存（复位优先）：S 置位、R1 复位；state 存元件状态
        if power:
            s = bool(ctx.read(el["s"]))
            r1 = bool(ctx.read(el["r1"]))
            st = ctx.elem_state(uid, 0)
            st = 0 if r1 else (1 if s else st)
            ctx.set_elem_state(uid, st)
            ctx.write(el["q"], st)
    elif k == "RS":
        # RS 锁存（置位优先）
        if power:
            s1 = bool(ctx.read(el["s1"]))
            r = bool(ctx.read(el["r"]))
            st = ctx.elem_state(uid, 0)
            st = 1 if s1 else (0 if r else st)
            ctx.set_elem_state(uid, st)
            ctx.write(el["q"], st)
    elif k == "CALL":
        if power:
            _call_fb(el, ctx)
    else:
        raise EvalError(f"未知输出元件: {k}")


def _timer_db(inst: str, interface: dict, ctx: EvalContext) -> DataBlock:
    """取定时器/计数器的背景数据块（不存在则自动生成）。"""
    if inst.startswith("#"):
        if ctx.scope_db is None:
            raise EvalError(f"OB1 中的定时器实例名不能以 # 开头: {inst}")
        return ctx.scope_db.ensure_sub(inst[1:], interface)
    if inst not in ctx.dbs:
        ctx.dbs[inst] = DataBlock(inst, interface)
    return ctx.dbs[inst]


def _call_fb(el: dict, ctx: EvalContext) -> None:
    """调用 FB 实例：IN 实参→形参 → 执行内部网络 → OUT 形参→实参。"""
    if ctx.depth >= MAX_CALL_DEPTH:
        raise EvalError("FB 嵌套调用过深")
    fb_name, inst_name = el["fb"], el["inst"]
    fb_def = ctx.fb_defs.get(fb_name)
    if fb_def is None:
        raise EvalError(f"未定义的 FB: {fb_name}")
    db = ctx.dbs.get(inst_name)
    if db is None:
        db = ctx.dbs[inst_name] = DataBlock(inst_name, fb_def.get("interface"))
    args = el.get("args", {})
    iface_in = set(fb_def.get("interface", {}).get("IN", {}))
    iface_out = set(fb_def.get("interface", {}).get("OUT", {}))
    # 1. IN 实参 → 背景数据块
    for param, actual in args.items():
        if param in iface_in:
            db.set(param, ctx.read(actual))
    # 2. 执行内部网络（元件状态/断点 uid 以实例名隔离，多实例互不干扰）
    sub = EvalContext(
        mem=ctx.mem, dbs=ctx.dbs, fb_defs=ctx.fb_defs, dt_ms=ctx.dt_ms,
        scope_db=db, scope_key=inst_name,
        elem_states=ctx.elem_states, flow=ctx.flow,
        breakpoints=ctx.breakpoints, drop=ctx.drop, depth=ctx.depth + 1,
    )
    eval_networks(fb_def.get("networks", []), sub)
    ctx.hit_breakpoints.extend(sub.hit_breakpoints)
    # 3. OUT 形参 → 实参
    for param, actual in args.items():
        if param in iface_out:
            ctx.write(actual, db.get(param))


def _check_breakpoint(ctx: EvalContext, uid: str, el: dict, glow: bool) -> None:
    """断点：能流"经过"（得电上升沿）时命中。一次断点命中后自动删除。"""
    full = f"{ctx.scope_key}:{uid}"
    bp = ctx.breakpoints.get(full)
    if bp is None:
        return
    prev = ctx.elem_state(f"bp:{uid}", 0)
    ctx.set_elem_state(f"bp:{uid}", 1 if glow else 0)
    if glow and not prev:
        addr = el.get("addr") or el.get("a") or ""
        try:
            val = ctx.read(addr) if addr else ""
        except Exception:
            val = ""
        ctx.hit_breakpoints.append({
            "uid": full, "kind": el.get("k"), "addr": addr, "value": val,
            "label": el.get("label", ""),
        })
        if bp.get("once"):
            del ctx.breakpoints[full]


# ---------------------------------------------------------------------- 工具
def collect_m_watch(networks: list[dict], fb_defs: dict[str, dict]) -> set[str]:
    """收集项目引用到的全部 M 区地址（决定 M 区快照范围）。"""
    out: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            for key, val in node.items():
                if key in ("addr", "src", "dst", "a", "b", "q", "s", "r", "s1", "r1") \
                        and isinstance(val, str) and val.startswith("M"):
                    out.add(val)
                else:
                    walk(val)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(networks)
    for fb in fb_defs.values():
        walk(fb.get("networks", []))
    return out
