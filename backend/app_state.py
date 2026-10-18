# -*- coding: utf-8 -*-
"""应用全局状态：当前项目、内核实例、课堂模式、程序锁、客户端角色表。"""
from __future__ import annotations

from .core.events import EventBus
from .core.scan import ScanEngine
from .projects.registry import get_project, list_projects

DEFAULT_PROJECT = "p1_quiz_buzzer"  # 初始默认加载项目1


class AppState:
    def __init__(self) -> None:
        self.bus = EventBus()
        self.engine = ScanEngine(self.bus)
        self.project_id = DEFAULT_PROJECT
        self.class_mode = False      # 课堂模式：开启后只有 teacher 能控制
        self.program_lock = False    # 程序锁
        self.clients: dict[int, dict] = {}   # ws 连接 id -> {"role","name"}

    # ------------------------------------------------------------------ 项目
    def load(self, pid: str) -> dict:
        cfg = get_project(pid)
        self.engine.load_project(cfg)
        self.project_id = pid
        return cfg

    @property
    def config(self) -> dict:
        return get_project(self.project_id)

    # ------------------------------------------------------------------ 客户端角色
    def client_join(self, client_id: int, role: str, name: str) -> str:
        # 第一个声明 teacher 的连接获得 teacher；没有 teacher 时自动提拔
        if role == "teacher" and any(c["role"] == "teacher" for c in self.clients.values()):
            role = "student"
        if not any(c["role"] == "teacher" for c in self.clients.values()):
            role = "teacher"
        self.clients[client_id] = {"role": role, "name": name}
        return role

    def client_leave(self, client_id: int) -> None:
        self.clients.pop(client_id, None)

    def control_allowed(self, client_id: int) -> bool:
        """课堂模式开启后，控制类消息只受理 teacher（协议决策 D5）。"""
        if not self.class_mode:
            return True
        c = self.clients.get(client_id)
        return bool(c and c["role"] == "teacher")

    # ------------------------------------------------------------------ 快照
    def settings_snapshot(self) -> dict:
        return {
            "project_id": self.project_id,
            "period_ms": self.engine.period_ms,
            "mode": self.engine.mode,
            "class_mode": self.class_mode,
            "program_lock": self.program_lock,
            "faults_on": sorted(self.engine.faults_on),
            "clients": sum(1 for _ in self.clients),
        }

    def hello_payload(self, role: str) -> dict:
        return {
            "type": "hello_ack",
            "config": self.config,
            "snapshot": self.engine.last_scan,
            "settings": self.settings_snapshot(),
            "you": {"role": role},
            "projects": list_projects(),
        }


state = AppState()
