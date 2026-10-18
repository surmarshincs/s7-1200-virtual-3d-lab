# -*- coding: utf-8 -*-
"""/ws/plc WebSocket 端点：连接管理、角色仲裁、上行消息路由、多客户端广播。

断线即冻结（协议决策 D7）是前端行为；本模块只保证：连接断开时干净地
摘除订阅，重连后走 hello 拿全量快照追平。
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from ..app_state import state
from .schemas import parse_upstream

router = APIRouter()

# 控制类消息（课堂模式下仅 teacher 可发）
CONTROL_TYPES = {
    "input", "set_period", "set_mode", "step", "inject_fault", "program_lock",
    "class_mode", "switch_project", "reset", "set_param",
    "set_breakpoint", "clear_breakpoint",
}


def _dumps(msg: dict) -> str:
    return json.dumps(msg, ensure_ascii=False)


def _broadcast_settings() -> None:
    state.bus.publish({"type": "settings", **state.settings_snapshot()})


@router.websocket("/ws/plc")
async def ws_plc(ws: WebSocket) -> None:
    await ws.accept()
    client_id = id(ws)
    queue = state.bus.subscribe()

    async def pump() -> None:
        """订阅队列 → 客户端。慢消费者由 EventBus 丢旧 scan（latest-wins）。"""
        try:
            while True:
                msg = await queue.get()
                await ws.send_text(_dumps(msg))
        except Exception:
            pass

    sender = asyncio.create_task(pump())

    async def reply(msg: dict) -> None:
        await ws.send_text(_dumps(msg))

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = parse_upstream(raw)
            except ValidationError as e:
                await reply({"type": "error", "ref": "", "msg": f"消息格式错误: {e.errors()[0]['msg']}"})
                continue

            try:
                if msg.type == "hello":
                    role = state.client_join(client_id, msg.role, msg.client_name)
                    await reply(state.hello_payload(role))
                    continue

                if msg.type == "ping":
                    await reply({"type": "pong", "t": msg.t})
                    continue

                # 课堂模式权限仲裁（协议决策 D5）
                if msg.type in CONTROL_TYPES and not state.control_allowed(client_id):
                    await reply({"type": "error", "ref": msg.type,
                                 "msg": "课堂模式下仅教师端可控制"})
                    continue

                eng = state.engine
                if msg.type == "input":
                    eng.set_input(msg.addr, msg.value)
                elif msg.type == "set_period":
                    eng.set_period(msg.ms)
                    _broadcast_settings()
                elif msg.type == "set_mode":
                    eng.set_mode(msg.mode)
                    _broadcast_settings()
                elif msg.type == "step":
                    await eng.step()
                elif msg.type == "inject_fault":
                    eng.set_fault(msg.id, msg.on)
                    state.bus.publish({"type": "event",
                                       "kind": "fault_on" if msg.on else "fault_off",
                                       "id": msg.id, "cycle": eng.cycle})
                    _broadcast_settings()
                elif msg.type == "program_lock":
                    state.program_lock = msg.locked
                    _broadcast_settings()
                elif msg.type == "class_mode":
                    state.class_mode = msg.on
                    _broadcast_settings()
                elif msg.type == "switch_project":
                    cfg = state.load(msg.id)
                    state.bus.publish({"type": "project_config", "config": cfg,
                                       "snapshot": None,
                                       "settings": state.settings_snapshot()})
                    state.bus.publish({"type": "event", "kind": "stage_change",
                                       "cycle": eng.cycle})
                elif msg.type == "reset":
                    state.load(state.project_id)  # 重新装载 = 清 I/Q/M/DB 重新上电
                    state.bus.publish({"type": "event", "kind": "reset",
                                       "cycle": eng.cycle})
                    _broadcast_settings()
                elif msg.type == "set_param":
                    eng.set_param(msg.db, msg.field, msg.value)
                    await reply({"type": "ack", "ref": "set_param", "ok": True})
                elif msg.type == "set_breakpoint":
                    eng.set_breakpoint(msg.uid, msg.once)
                    await reply({"type": "ack", "ref": "set_breakpoint", "ok": True})
                elif msg.type == "clear_breakpoint":
                    eng.clear_breakpoint(msg.uid)
                    await reply({"type": "ack", "ref": "clear_breakpoint", "ok": True})
            except (KeyError, ValueError) as e:
                await reply({"type": "error", "ref": msg.type, "msg": str(e)})
    except WebSocketDisconnect:
        pass
    finally:
        state.client_leave(client_id)
        state.bus.unsubscribe(queue)
        sender.cancel()
