# -*- coding: utf-8 -*-
"""项目注册表：五项目共用同一内核，懒加载（首次切换才 import 对应模块）。"""
from __future__ import annotations

from ..core.blocks import validate_ob1_structure
from .base import validate_project

_REGISTRY = {
    "p1_quiz_buzzer": "backend.projects.p1_quiz_buzzer",
    "p2_star_delta": "backend.projects.p2_star_delta",
    "p3_shuttle_car": "backend.projects.p3_shuttle_car",
    "p4_traffic_light": "backend.projects.p4_traffic_light",
    "p5_motor_seq": "backend.projects.p5_motor_seq",
}

_cache: dict[str, dict] = {}


def list_projects() -> list[dict]:
    """项目清单（id + 名称），供前端项目切换器。"""
    out = []
    for pid in _REGISTRY:
        cfg = _cache.get(pid)
        out.append({"id": pid, "name": cfg["name"] if cfg else _lazy_name(pid)})
    return out


def _lazy_name(pid: str) -> str:
    """未加载时从模块 import 拿 name（只触发一次）。"""
    return get_project(pid)["name"]


def get_project(pid: str) -> dict:
    """取项目 CONFIG（懒加载 + 校验 + 缓存）。"""
    if pid not in _REGISTRY:
        raise KeyError(f"未知项目: {pid}")
    if pid not in _cache:
        import importlib
        cfg = importlib.import_module(_REGISTRY[pid]).CONFIG
        validate_project(cfg)
        validate_ob1_structure(cfg)
        _cache[pid] = cfg
    return _cache[pid]
