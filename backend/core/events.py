# -*- coding: utf-8 -*-
"""周期事件总线：内核 publish，每个 WebSocket 客户端一个订阅队列。

慢消费者策略（协议决策 D6）：队列满时丢弃队首的 scan 周期消息（保事件类消息），
客户端发现 cycle 跳号后自行拉 /api/snapshot 追平。
"""
from __future__ import annotations

import asyncio


class EventBus:
    def __init__(self, queue_size: int = 64) -> None:
        self._subs: set[asyncio.Queue] = set()
        self._queue_size = queue_size

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._queue_size)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, msg: dict) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                # 只丢周期消息，事件/配置类消息必须送达
                if msg.get("type") == "scan":
                    try:
                        q.get_nowait()
                        q.put_nowait(msg)
                    except (asyncio.QueueEmpty, asyncio.QueueFull):
                        pass
