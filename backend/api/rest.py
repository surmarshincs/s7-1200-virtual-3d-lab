# -*- coding: utf-8 -*-
"""REST 辅助接口：项目清单与全量快照（断线重连/慢消费者跳号后追平用）。"""
from __future__ import annotations

from fastapi import APIRouter

from ..app_state import state
from ..projects.registry import list_projects

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict:
    return {"ok": True, "cycle": state.engine.cycle, "project": state.project_id}


@router.get("/projects")
def projects() -> list[dict]:
    return list_projects()


@router.get("/snapshot")
def snapshot() -> dict:
    """全量快照：项目 CONFIG + 最近一帧 scan + 设置。"""
    return {
        "config": state.config,
        "snapshot": state.engine.last_scan,
        "settings": state.settings_snapshot(),
    }
