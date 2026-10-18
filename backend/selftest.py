# -*- coding: utf-8 -*-
"""后端内核自测：绕过网络层，直接驱动扫描引擎逐周期断言五个项目的关键行为。

运行（在 PLC_1 目录下）：
    python -m backend.selftest
"""
from __future__ import annotations

import asyncio

from .core.events import EventBus
from .core.primitives import SEG_TABLE
from .core.scan import ScanEngine
from .projects.registry import get_project

PERIOD = 100  # 测试用 100ms 虚拟周期


def make_engine(pid: str) -> ScanEngine:
    eng = ScanEngine(EventBus())
    eng.load_project(get_project(pid))
    return eng


async def scan(eng: ScanEngine, n: int = 1) -> None:
    for _ in range(n):
        await eng.do_scan(PERIOD)


async def hold(eng: ScanEngine, seconds: float) -> None:
    """按虚拟时间推进 seconds 秒。"""
    await scan(eng, max(1, round(seconds * 1000 / PERIOD)))


# ---------------------------------------------------------------- 项目1 抢答器
async def test_p1() -> None:
    eng = make_engine("p1_quiz_buzzer")

    # 滞后一拍：按下 4 号按钮（I0.3），未扫描前 I 区不生效
    eng.set_input("I0.3", 1)
    assert eng.mem.get_bit("I0.3") == 0, "非采样时刻输入不得生效"
    await scan(eng)
    assert eng.mem.get_bit("I0.3") == 1, "采样后输入应锁存进 I 区"
    await scan(eng)
    assert eng.mem.get_bit("M0.3") == 1 and eng.mem.get_bit("M1.0") == 1, "4 路应锁存且忙标志置位"
    assert eng.mem.get_byte("MB10") == 4, "号码应译码为 4"
    assert eng.mem.get_byte("QB0") == SEG_TABLE[4], "QB0 应为数字 4 的七段码"
    assert eng.mem.get_bit("Q1.0") == 1, "蜂鸣器应响"
    eng.set_input("I0.3", 0)  # 松开按钮

    # 互锁：忙时再按 1 号无效
    eng.set_input("I0.0", 1)
    await scan(eng, 2)
    assert eng.mem.get_bit("M0.0") == 0, "忙标志应互锁屏蔽后来按钮"
    eng.set_input("I0.0", 0)

    # 蜂鸣器 1 秒后自停
    await hold(eng, 1.2)
    assert eng.mem.get_bit("Q1.0") == 0, "蜂鸣器 1 秒后应自停"

    # 复位解锁 + 清屏
    eng.set_input("I1.0", 1)
    await scan(eng, 2)
    assert eng.mem.get_byte("MB10") == 255, "复位后译码输入应为灭灯码"
    assert eng.mem.get_byte("QB0") == 0, "复位后数码管应熄灭"
    assert eng.mem.get_bit("M1.0") == 0, "复位后忙标志应清除"

    # 故障变体：漏互锁 → 后按覆盖先按
    eng2 = make_engine("p1_quiz_buzzer")
    eng2.set_fault("NO_INTERLOCK", True)
    eng2.set_input("I0.0", 1)
    await scan(eng2, 2)
    eng2.set_input("I0.0", 0)
    eng2.set_input("I0.5", 1)
    await scan(eng2, 2)
    assert eng2.mem.get_byte("MB10") == 6, "漏互锁时后按应覆盖先按"
    print("✔ 项目1 八路抢答器")


# ---------------------------------------------------------------- 项目2 星三角
async def test_p2() -> None:
    eng = make_engine("p2_star_delta")
    # NC 输入的正常态：停止/热继 = 1（前端连接时按器件 nc 标记下发）
    eng.set_input("I0.1", 1)
    eng.set_input("I0.2", 1)
    eng.set_input("I0.0", 1)  # 启动
    await scan(eng, 2)
    eng.set_input("I0.0", 0)
    db = eng.dbs["DB_SD"]
    assert eng.mem.get_bit("Q0.0") == 1 and eng.mem.get_bit("Q0.1") == 1, "应星形启动 KM1+KMY"
    assert eng.mem.get_bit("Q0.2") == 0, "星接时 KMΔ 不得吸合"
    assert db.get("step") == 1

    await hold(eng, 5.2)  # 星接计时到
    assert db.get("step") == 2, "应进入换相死区"
    assert eng.mem.get_bit("Q0.1") == 0 and eng.mem.get_bit("Q0.2") == 0, "死区双断"

    await hold(eng, 0.7)  # 死区结束
    assert db.get("step") == 3, "应角接运行"
    assert eng.mem.get_bit("Q0.2") == 1 and eng.mem.get_bit("Q0.1") == 0

    # 停止：NC 按钮按下 = 输入变 0
    eng.set_input("I0.1", 0)
    await scan(eng, 2)
    assert eng.mem.get_bit("Q0.0") == 0 and eng.mem.get_bit("Q0.2") == 0, "停止后全断"
    assert db.get("step") == 0

    # FR 故障注入：启动后立即跳闸
    eng2 = make_engine("p2_star_delta")
    eng2.set_input("I0.1", 1)
    eng2.set_input("I0.0", 1)
    eng2.set_fault("FR_TRIP", True)  # 强制 I0.2=0
    await scan(eng2, 3)
    assert eng2.mem.get_bit("Q0.0") == 0, "FR 动作应全断"
    print("✔ 项目2 星三角降压启动")


# ---------------------------------------------------------------- 项目3 小车
async def test_p3() -> None:
    eng = make_engine("p3_shuttle_car")
    eng.set_input("I0.3", 1)   # 停止 NC 正常态
    eng.set_input("I0.4", 1)   # FR 正常态
    eng.set_input("I0.2", 1)   # 启动
    await scan(eng, 2)
    eng.set_input("I0.2", 0)
    assert eng.mem.get_bit("Q0.0") == 1, "启动后应右行"

    eng.set_input("I0.0", 1)   # 撞右限位
    await scan(eng, 2)
    eng.set_input("I0.0", 0)
    assert eng.mem.get_bit("Q0.0") == 0 and eng.mem.get_bit("Q0.2") == 1, "右限位停+卸料灯"
    await hold(eng, 5.2)
    assert eng.mem.get_bit("Q0.1") == 1, "卸料完应左行"

    eng.set_input("I0.1", 1)   # 撞左限位
    await scan(eng, 2)
    eng.set_input("I0.1", 0)
    assert eng.mem.get_bit("Q0.3") == 1, "左限位停+装料灯"
    await hold(eng, 5.2)
    assert eng.mem.get_bit("Q0.0") == 1, "装料完应再次右行（循环）"
    assert eng.dbs["DB_CAR"].get("trips") == 1, "往返计数应为 1"

    # 停止任意时刻有效
    eng.set_input("I0.3", 0)
    await scan(eng, 2)
    assert eng.mem.get_bit("Q0.0") == 0 and eng.dbs["DB_CAR"].get("state") == 0
    print("✔ 项目3 运料小车自动往返")


# ---------------------------------------------------------------- 项目4 交通灯
async def test_p4() -> None:
    eng = make_engine("p4_traffic_light")
    await scan(eng, 2)
    assert eng.mem.get_bit("Q0.2") == 1 and eng.mem.get_bit("Q0.3") == 1, "初始：南北绿+东西红"
    db = eng.dbs["DB_Traffic"]
    assert db.get("phase") == 0

    await hold(eng, 25.4)  # 含自复位附加节拍余量
    assert db.get("phase") == 1 and eng.mem.get_bit("Q0.1") == 1, "应转南北黄"
    await hold(eng, 3.3)
    assert db.get("phase") == 2 and eng.mem.get_bit("Q0.0") == 1 and eng.mem.get_bit("Q0.3") == 1, "应全红"
    await hold(eng, 1.3)
    assert db.get("phase") == 3 and eng.mem.get_bit("Q0.5") == 1, "应东西绿"
    assert eng.mem.get_bit("Q0.0") == 1, "东西绿时南北应红"
    print("✔ 项目4 十字路口交通灯")


# ---------------------------------------------------------------- 项目5 电机组
async def test_p5() -> None:
    eng = make_engine("p5_motor_seq")
    for a in ("I0.1", "I0.2", "I0.3", "I0.4"):
        eng.set_input(a, 1)
    eng.set_input("I0.0", 1)
    await scan(eng, 2)
    eng.set_input("I0.0", 0)
    assert eng.mem.get_bit("Q0.0") == 1 and eng.mem.get_bit("Q0.1") == 0, "先启 KM1"
    await hold(eng, 3.2)
    assert eng.mem.get_bit("Q0.1") == 1 and eng.mem.get_bit("Q0.2") == 0, "3s 后启 KM2"
    await hold(eng, 3.2)
    assert eng.mem.get_bit("Q0.2") == 1, "再 3s 后启 KM3（全组运行）"

    # 逆停：KM3→KM2→KM1
    eng.set_input("I0.1", 0)
    await scan(eng, 2)
    assert eng.mem.get_bit("Q0.2") == 0 and eng.mem.get_bit("Q0.1") == 1, "先停 KM3"
    await hold(eng, 3.2)
    assert eng.mem.get_bit("Q0.1") == 0 and eng.mem.get_bit("Q0.0") == 1, "再停 KM2"
    await hold(eng, 3.2)
    assert eng.mem.get_bit("Q0.0") == 0, "最后停 KM1"

    # FR 联锁：启动中途 FR2 动作全断
    eng2 = make_engine("p5_motor_seq")
    for a in ("I0.1", "I0.2", "I0.4"):
        eng2.set_input(a, 1)
    eng2.set_input("I0.0", 1)
    await scan(eng2, 2)
    eng2.set_input("I0.0", 0)
    eng2.set_input("I0.3", 0)  # FR2 动作
    await scan(eng2, 2)
    assert eng2.mem.get_bit("Q0.0") == 0, "任一 FR 动作全组立即断开"
    print("✔ 项目5 电机组顺序启停")


async def main() -> None:
    await test_p1()
    await test_p2()
    await test_p3()
    await test_p4()
    await test_p5()
    print("\n全部 5 个项目内核行为断言通过 ✔")


if __name__ == "__main__":
    asyncio.run(main())
