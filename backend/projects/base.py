# -*- coding: utf-8 -*-
"""项目 CONFIG 基类与校验。

每个项目就是一份纯声明字典（可 JSON 序列化），字段：
    id / name / desc        基本信息
    networks                OB1 梯形图网络（后端执行 + 前端渲染共用）
    fbs                     FB 定义表 {名: {"interface":..., "networks":...}}
    io_map                  IO 表 [{addr,label,device,kind}]（IO 状态表 + 3D 绑定）
    stages                  阶段地铁图 [{name, when:[[addr,val]...], timer?}]（首匹配生效）
    faults                  故障注入 [{id,desc,kind:force|variant, addr?,value?,drop?,hints}]
    cards                   原理卡 [{title, rows:[[k,v]...], note, live?}]
    scene                   3D 场景参数 {devices:[...], wires:[...]}（前端场景构建器消费）
    require_single_call     True 时强制 OB1 仅含一次 FB 调用（项目4）
"""
from __future__ import annotations

from pydantic import BaseModel


class IOEntry(BaseModel):
    addr: str
    label: str
    device: str = ""
    kind: str = "input"          # input | output


class Fault(BaseModel):
    id: str
    desc: str
    kind: str                    # force（强制地址）| variant（程序变体，拆元件）
    addr: str | None = None
    value: int | None = None
    drop: list[str] = []
    hints: dict[str, str] = {}   # 分级排故提示 {"method","direction","answer"}


class Stage(BaseModel):
    name: str
    when: list[list] = []        # [[addr, val], ...] 全部满足即命中
    timer: str | None = None     # 关联 TON 路径（如 "DB_SD.T1"）用于剩余时间倒数


class ProjectConfig(BaseModel):
    id: str
    name: str
    desc: str = ""
    networks: list[dict] = []
    fbs: dict[str, dict] = {}
    io_map: list[IOEntry] = []
    stages: list[Stage] = []
    faults: list[Fault] = []
    cards: list[dict] = []
    scene: dict = {}
    m_watch_extra: list[str] = []
    require_single_call: bool = False


def validate_project(cfg: dict) -> dict:
    """加载时校验结构，不合法立刻抛错（教学项目配置错了要尽早暴露）。"""
    ProjectConfig(**cfg)
    return cfg
