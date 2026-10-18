# -*- coding: utf-8 -*-
"""扫描循环引擎（asyncio）：严格 IEC 61131-3 模型。

每周期顺序：①采样输入锁存到 I 区 → ②执行 OB1 → ③写 Q 映像 → ④广播状态事件。
非采样时刻的外部信号变化只进 pending 缓冲，下一采样点才生效（"滞后一拍"教学点）。

双时钟（协议决策 D2）：
    ts_ms  真实墙钟；vts_ms 虚拟时钟（TON、时间轴、示波器横轴一律用它）。
    慢速 slow 模式下真实扫描节奏不变、虚拟时钟按 ×0.1 步进 —— 5 秒延时在
    示波器上真实拉伸 10 倍，视图刷新依旧流畅。
"""
from __future__ import annotations

import asyncio
import time

from .blocks import validate_ob1_structure
from .datablock import DataBlock
from .events import EventBus
from .memory import Memory
from .networks import (EvalContext, collect_m_watch, collect_timer_dbs,
                       eval_networks)

PERIOD_MIN, PERIOD_MAX = 50, 2000  # 扫描周期可调范围（ms）


class ScanEngine:
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self.mem = Memory()
        self.dbs: dict[str, DataBlock] = {}
        self.project: dict | None = None

        self.period_ms = 100
        self.mode = "run"          # run | pause | slow
        self.cycle = 0             # 严格递增，全局唯一时间轴锚点（换项目也不回退）
        self.vts_ms = 0            # 虚拟时钟
        self.epoch = 0             # 项目加载纪元，(epoch, cycle) 全局唯一

        self.pending_inputs: dict[str, int] = {}   # 待采样输入缓冲
        self.elem_states: dict[str, object] = {}   # P 触点等元件状态
        self.breakpoints: dict[str, dict] = {}     # uid -> {"once": bool}
        self.faults_on: set[str] = set()           # 已注入故障 id
        self.m_watch: set[str] = set()             # M 区快照范围

        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self.last_scan: dict | None = None  # 最近一次 scan 消息（快照用）

    # ------------------------------------------------------------------ 项目装载
    def load_project(self, cfg: dict) -> None:
        """装载项目 CONFIG：重置存储区、自动建背景数据块、校验结构。五项目共用此路径。"""
        validate_ob1_structure(cfg)
        self.project = cfg
        self.mem.reset()
        self.dbs = {}
        self.elem_states = {}
        self.breakpoints = {}
        self.faults_on = set()
        self.pending_inputs = {}
        self.vts_ms = 0
        self.epoch += 1
        self.last_scan = None  # 旧项目的快照作废，客户端等待新项目首帧
        # OB1 网络里的 TON/CTU 背景数据块
        collect_timer_dbs(cfg.get("networks", []), self.dbs)
        # FB 实例背景数据块 + FB 内部 #T1 这类嵌套定时器
        fb_defs = cfg.get("fbs", {})
        for net in cfg.get("networks", []):
            for rung in net.get("rungs", []):
                for el in rung.get("outputs", []):
                    if el.get("k") == "CALL":
                        fb_def = fb_defs[el["fb"]]
                        db = self.dbs.setdefault(
                            el["inst"], DataBlock(el["inst"], fb_def.get("interface")))
                        collect_timer_dbs(fb_def.get("networks", []), self.dbs, scope_db=db)
        self.m_watch = collect_m_watch(cfg.get("networks", []), fb_defs)
        self.m_watch.update(cfg.get("m_watch_extra", []))

    # ------------------------------------------------------------------ 循环
    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        while True:
            if self.project is None or self.mode == "pause":
                await asyncio.sleep(0.05)
                continue
            await asyncio.sleep(self.period_ms / 1000)
            # 慢速 ×0.1：真实节奏不变，虚拟时钟步进缩小
            vdt = self.period_ms if self.mode == "run" else max(1, self.period_ms // 10)
            await self.do_scan(vdt)

    async def step(self) -> None:
        """单步：暂停模式下推进一个周期（虚拟时钟按一个整周期步进）。"""
        if self.mode == "pause" and self.project is not None:
            await self.do_scan(self.period_ms)

    # ------------------------------------------------------------------ 一个扫描周期
    async def do_scan(self, vdt_ms: int) -> None:
        async with self._lock:
            assert self.project is not None
            self.cycle += 1
            self.vts_ms += vdt_ms

            # ① 采样输入：pending 缓冲 → I 区（非采样时刻的变化此刻才生效）
            for addr, val in self.pending_inputs.items():
                self.mem.write(addr, val)
            self.pending_inputs.clear()
            # 故障注入（强制类）：I 区在采样后强制，Q 区在程序执行后强制
            for f in self._force_faults():
                if f["addr"].startswith("I"):
                    self.mem.write(f["addr"], f["value"])

            # ② 执行 OB1（含 FB 调用链）
            ctx = EvalContext(
                mem=self.mem, dbs=self.dbs, fb_defs=self.project.get("fbs", {}),
                dt_ms=vdt_ms, scope_db=None, scope_key="OB1",
                elem_states=self.elem_states, flow={},
                breakpoints=self.breakpoints, drop=self._variant_drop(),
            )
            eval_networks(self.project.get("networks", []), ctx)

            for f in self._force_faults():
                if f["addr"].startswith("Q"):
                    self.mem.write(f["addr"], f["value"])

            # ③ 写 Q 映像：虚拟内核线圈直接写 Q 区，无独立物理层
            # 断点命中：全局暂停 + 事件（prompt 六.4）
            for hit in ctx.hit_breakpoints:
                self.mode = "pause"
                self.bus.publish({
                    "type": "event", "kind": "breakpoint_hit", "cycle": self.cycle,
                    "uid": hit["uid"], "elem_kind": hit["kind"], "addr": hit["addr"],
                    "value": hit["value"], "label": hit["label"],
                })

            # ④ 广播状态事件：所有视图只准订阅此事件驱动渲染
            msg = self._build_scan_msg(ctx)
            self.last_scan = msg  # 断线重连/新客户端 hello 时作全量快照
            self.bus.publish(msg)

    # ------------------------------------------------------------------ 下行消息组装
    def _read_ref(self, ref):
        """阶段判定用：读一个地址或 DB 字段。"""
        head, _, rest = ref.partition(".")
        if head in self.dbs:
            return self.dbs[head].get(rest)
        return self.mem.read(ref)

    def _current_stage(self) -> tuple[str, int, int]:
        """按项目 stages 声明首匹配当前阶段，返回 (阶段名, 序号, 定时器剩余ms)。

        stage 的 timer 字段指向 TON 实例路径（如 "DB_SD.T1"），剩余 = PT - ET。
        """
        stages = (self.project or {}).get("stages", [])
        for idx, st in enumerate(stages):
            when = st.get("when", [])
            if all(self._read_ref(a) == v for a, v in when):
                remain = -1
                timer = st.get("timer")
                if timer:
                    try:
                        head, _, rest = timer.partition(".")
                        db = self.dbs[head]
                        remain = int(db.get(f"{rest}.PT")) - int(db.get(f"{rest}.ET"))
                    except (KeyError, AttributeError, TypeError):
                        remain = -1
                return st["name"], idx, remain
        return "待机", -1, -1

    def _timers_snapshot(self) -> tuple[dict, dict]:
        """收集全部 TON/CTU 背景数据块的实时值（顶层与 FB 实例内嵌套）。"""
        timers: dict[str, dict] = {}
        counters: dict[str, dict] = {}

        def scan_db(path: str, db: DataBlock) -> None:
            f = db.fields
            if "ET" in f and "PT" in f:
                timers[path] = {"ET": f["ET"], "PT": f["PT"], "Q": f["Q"]}
            if "CV" in f and "PV" in f:
                counters[path] = {"CV": f["CV"], "PV": f["PV"], "Q": f["Q"]}
            for name, sub in db.subs.items():
                scan_db(f"{path}.{name}", sub)

        for name, db in self.dbs.items():
            scan_db(name, db)
        return timers, counters

    def _build_scan_msg(self, ctx: EvalContext) -> dict:
        i, q, m = self.mem.split_snapshot(self.mem.snapshot(self.m_watch))
        stage_name, stage_idx, stage_remain = self._current_stage()
        timers, counters = self._timers_snapshot()
        return {
            "type": "scan",
            "epoch": self.epoch,
            "cycle": self.cycle,
            "ts_ms": int(time.time() * 1000),
            "vts_ms": self.vts_ms,
            "period_ms": self.period_ms,
            "mode": self.mode,
            "stage": stage_name,
            "stage_index": stage_idx,
            "stage_remain_ms": stage_remain,
            "I": i, "Q": q, "M": m,
            "DB": {name: db.snapshot() for name, db in self.dbs.items()},
            "timers": timers,
            "counters": counters,
            "flow": ctx.flow,
            "events": ["sample", "refresh"],
        }

    # ------------------------------------------------------------------ 上行操作
    def set_input(self, addr: str, value: int) -> None:
        """外部信号变化 → 待采样缓冲（下一采样点才锁存进 I 区）。"""
        if not addr.startswith("I"):
            raise KeyError(f"外部输入只能写 I 区: {addr!r}")
        self.mem.read(addr)  # 校验地址合法
        self.pending_inputs[addr] = 1 if value else 0

    def set_period(self, ms: int) -> None:
        self.period_ms = max(PERIOD_MIN, min(PERIOD_MAX, int(ms)))

    def set_mode(self, mode: str) -> None:
        if mode not in ("run", "pause", "slow"):
            raise ValueError(f"非法模式: {mode}")
        self.mode = mode

    def set_breakpoint(self, uid: str, once: bool) -> None:
        self.breakpoints[uid] = {"once": bool(once)}

    def clear_breakpoint(self, uid: str | None = None) -> None:
        if uid is None:
            self.breakpoints.clear()
        else:
            self.breakpoints.pop(uid, None)

    def set_fault(self, fault_id: str, on: bool) -> None:
        if on:
            self.faults_on.add(fault_id)
        else:
            self.faults_on.discard(fault_id)

    def set_param(self, db: str, field: str, value) -> None:
        """在线修改背景数据块参数（如星三角启动时间 PT 可调）。"""
        if db not in self.dbs:
            raise KeyError(f"DB 不存在: {db}")
        self.dbs[db].set(field, value)

    def _force_faults(self) -> list[dict]:
        out = []
        for f in (self.project or {}).get("faults", []):
            if f["id"] in self.faults_on and f.get("kind") == "force":
                out.append(f)
        return out

    def _variant_drop(self) -> set[str]:
        """故障变体：已激活的程序变体要"拆除"的元件 uid 集合（如漏互锁）。"""
        drop: set[str] = set()
        for f in (self.project or {}).get("faults", []):
            if f["id"] in self.faults_on and f.get("kind") == "variant":
                drop.update(f.get("drop", []))
        return drop
