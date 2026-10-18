# -*- coding: utf-8 -*-
"""WebSocket 消息协议 —— pydantic 模型，协议的单一事实源。

端点：/ws/plc，JSON 文本帧，`type` 字段判别。
上行 = 客户端 → 服务端；下行 = 服务端 → 客户端。
README 的协议文档与本文件逐字段一致。
"""
from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, Field, TypeAdapter

# ================================================================ 上行消息


class HelloMsg(BaseModel):
    """握手：声明客户端角色。课堂模式开启后只有 teacher 能发控制类消息。"""
    type: Literal["hello"]
    client_name: str = ""
    role: Literal["teacher", "student"] = "student"


class InputMsg(BaseModel):
    """外部信号变化（按钮按下/松开、限位触发）。进待采样缓冲，下一采样点锁存。"""
    type: Literal["input"]
    addr: str                  # 仅 I 区，如 "I0.0"
    value: int                 # 0 | 1


class SetPeriodMsg(BaseModel):
    type: Literal["set_period"]
    ms: int                    # 50 - 2000


class SetModeMsg(BaseModel):
    type: Literal["set_mode"]
    mode: Literal["run", "pause", "slow"]   # slow = 虚拟时钟 ×0.1


class StepMsg(BaseModel):
    """单步：pause 模式下推进一个扫描周期。"""
    type: Literal["step"]


class InjectFaultMsg(BaseModel):
    type: Literal["inject_fault"]
    id: str                    # 项目 CONFIG faults 里的故障 id
    on: bool = True


class ProgramLockMsg(BaseModel):
    type: Literal["program_lock"]
    locked: bool


class ClassModeMsg(BaseModel):
    type: Literal["class_mode"]
    on: bool


class SwitchProjectMsg(BaseModel):
    type: Literal["switch_project"]
    id: str                    # 项目 id，如 "p2_star_delta"


class ResetMsg(BaseModel):
    """清空 I/Q/M/DB，模拟重新上电（周期号 cycle 不回退）。"""
    type: Literal["reset"]


class SetParamMsg(BaseModel):
    """在线改背景数据块参数（如星三角启动时间）：db="DB_SD", field="pt_star"。"""
    type: Literal["set_param"]
    db: str
    field: str
    value: int | float


class SetBreakpointMsg(BaseModel):
    """在梯形图元件上设断点：能流下次经过（得电上升沿）时全局暂停。"""
    type: Literal["set_breakpoint"]
    uid: str                   # 元件 uid，如 "OB1:N1.R1.s0" / "DB_SD:SD4.R2.s1"
    once: bool = True          # 一次断点 or 持续断点


class ClearBreakpointMsg(BaseModel):
    type: Literal["clear_breakpoint"]
    uid: str | None = None     # None = 清除全部


class PingMsg(BaseModel):
    type: Literal["ping"]
    t: int = 0


UpstreamMsg = Union[
    HelloMsg, InputMsg, SetPeriodMsg, SetModeMsg, StepMsg, InjectFaultMsg,
    ProgramLockMsg, ClassModeMsg, SwitchProjectMsg, ResetMsg, SetParamMsg,
    SetBreakpointMsg, ClearBreakpointMsg, PingMsg,
]

_upstream_adapter = TypeAdapter(UpstreamMsg)


def parse_upstream(raw: str | bytes) -> UpstreamMsg:
    """解析上行消息，非法消息抛 pydantic ValidationError。"""
    return _upstream_adapter.validate_json(raw)


# ================================================================ 下行消息（文档用模型）
# 实际发送为 dict（scan 消息由内核直接组装以保证性能），字段与本定义一致。

class ScanMsg(BaseModel):
    """每周期广播。cycle 严格递增，是所有视图的对齐锚点（协议决策 D1）。"""
    type: Literal["scan"] = "scan"
    epoch: int                 # 项目加载纪元，(epoch, cycle) 全局唯一
    cycle: int
    ts_ms: int                 # 真实墙钟
    vts_ms: int                # 虚拟时钟（慢速 ×0.1，TON/时间轴/示波器用它）
    period_ms: int
    mode: str                  # run | pause | slow
    stage: str                 # 当前阶段名（教学语言）
    stage_index: int
    stage_remain_ms: int       # 当前阶段 TON 剩余时间，无则 -1
    I: dict[str, int]
    Q: dict[str, int]
    M: dict[str, int]
    DB: dict[str, dict]        # 全部背景数据块快照
    timers: dict[str, dict]    # {"DB_SD.T1": {"ET":..,"PT":..,"Q":..}}
    counters: dict[str, dict]  # {"DB_CAR.C1": {"CV":..,"PV":..,"Q":..}}
    flow: dict[str, int]       # 能流表：元件 uid -> 0/1
    events: list[str] = ["sample", "refresh"]


class HelloAckMsg(BaseModel):
    """握手应答：全量项目 CONFIG（前端渲染梯形图/3D 用）+ 当前快照 + 设置。"""
    type: Literal["hello_ack"] = "hello_ack"
    config: dict
    snapshot: dict | None
    settings: dict
    you: dict                  # {"role": "teacher"}


class EventMsg(BaseModel):
    """按需事件：breakpoint_hit / fault_on / fault_off / stage_change / toast。"""
    type: Literal["event"] = "event"
    kind: str
    cycle: int = 0


class ErrorMsg(BaseModel):
    type: Literal["error"] = "error"
    ref: str = ""              # 被拒绝/出错的上行消息 type
    msg: str = ""
