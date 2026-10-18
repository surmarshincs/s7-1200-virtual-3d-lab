# -*- coding: utf-8 -*-
"""WS 冒烟测试：hello → 收 scan → 上行 input → 验证滞后一拍 → 切项目 → 复位。"""
import asyncio
import json

import websockets


async def main() -> None:
    async with websockets.connect("ws://127.0.0.1:8000/ws/plc") as ws:
        await ws.send(json.dumps({"type": "hello", "role": "teacher",
                                  "client_name": "smoke"}))
        ack = json.loads(await ws.recv())
        assert ack["type"] == "hello_ack", ack["type"]
        assert ack["config"]["id"] == "p1_quiz_buzzer"
        assert ack["you"]["role"] == "teacher"
        print("✔ hello_ack，默认项目1，角色 teacher")

        # 收一帧 scan
        scan = json.loads(await ws.recv())
        assert scan["type"] == "scan" and scan["cycle"] >= 1
        assert {"I", "Q", "M", "DB", "flow", "timers"} <= scan.keys()
        print(f"✔ scan 帧 cycle={scan['cycle']}，字段齐全")

        # 上行 input：I0.0 按下 → 后续 scan 中应出现 I0.0=1（滞后一拍）
        await ws.send(json.dumps({"type": "input", "addr": "I0.0", "value": 1}))
        seen = False
        for _ in range(20):
            m = json.loads(await ws.recv())
            if m["type"] == "scan" and m["I"].get("I0.0") == 1:
                seen = True
                lag_cycle = m["cycle"]
                break
        assert seen, "输入未在后续周期锁存"
        print(f"✔ 上行 input 在 cycle={lag_cycle} 锁存（滞后一拍可见）")

        # 暂停 + 单步
        await ws.send(json.dumps({"type": "set_mode", "mode": "pause"}))
        await asyncio.sleep(0.3)
        await ws.send(json.dumps({"type": "step"}))
        got_step = False
        for _ in range(20):
            m = json.loads(await ws.recv())
            if m["type"] == "scan" and m["mode"] == "pause":
                got_step = True
                break
        assert got_step
        print("✔ 暂停/单步生效")

        # 切项目 → 应收 project_config
        await ws.send(json.dumps({"type": "switch_project", "id": "p2_star_delta"}))
        got_cfg = False
        for _ in range(30):
            m = json.loads(await ws.recv())
            if m["type"] == "project_config":
                assert m["config"]["id"] == "p2_star_delta"
                got_cfg = True
                break
        assert got_cfg
        print("✔ 切换项目2，project_config 下发")

        # 故障注入 → settings 回播
        await ws.send(json.dumps({"type": "inject_fault", "id": "FR_TRIP", "on": True}))
        got = False
        for _ in range(30):
            m = json.loads(await ws.recv())
            if m["type"] == "settings" and "FR_TRIP" in m.get("faults_on", []):
                got = True
                break
        assert got
        print("✔ 故障注入并回播 settings")

        print("\nWS 冒烟测试全部通过 ✔")


asyncio.run(main())
