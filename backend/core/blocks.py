# -*- coding: utf-8 -*-
"""FB（功能块）定义与 OB1 结构校验。

FB 定义是项目 CONFIG 里的声明式字典：
    {
      "interface": {"IN": {"start": 0}, "OUT": {"km1": 0}, "STAT": {"step": 0}},
      "networks":  [ ... 与 OB1 相同的梯形图网络，内部变量用 #name 访问 ... ]
    }

教学硬性要求（prompt 一.4）：所有定时与状态机放 FB 中，OB1 只写调用逻辑。
项目 4 更进一步：OB1 中仅允许一次 FB_TrafficLight 调用，由本模块强制校验。
"""
from __future__ import annotations


def make_fb(interface: dict, networks: list[dict]) -> dict:
    """构造一份 FB 定义（项目 CONFIG 用，纯声明、可 JSON 序列化）。"""
    return {"interface": interface, "networks": networks}


def validate_ob1_structure(project: dict) -> None:
    """OB1 结构强制校验。

    项目 CONFIG 里 require_single_call=True 时（项目4）：
    OB1 必须只有 1 个网络、1 个 rung、且输出恰好是一次 CALL。
    """
    if not project.get("require_single_call"):
        return
    nets = project.get("networks", [])
    if len(nets) != 1 or len(nets[0].get("rungs", [])) != 1:
        raise ValueError(f"{project['id']}: 教学要求 OB1 仅含一个网络一个梯级（仅一次 FB 调用）")
    rung = nets[0]["rungs"][0]
    calls = [o for o in rung.get("outputs", []) if o.get("k") == "CALL"]
    if len(calls) != 1 or len(rung.get("outputs", [])) != 1:
        raise ValueError(f"{project['id']}: OB1 中只允许一次 FB 调用")
