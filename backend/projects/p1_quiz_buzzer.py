# -*- coding: utf-8 -*-
"""项目1：八路抢答器。

IO：I0.0-I0.7 八路抢答按钮，I1.0 主持人复位；
    Q0.0-Q0.6 数码管段 a-g（裸段模式，程序内 SEG 译码），Q1.0 蜂鸣器。
逻辑：任一按钮按下 → SET 锁存该路 → SEG 译码送数码管 → 蜂鸣器响 1 秒 →
      忙标志互锁屏蔽其余 7 路 → 主持人复位解锁。
教学点：互锁、锁存、译码。定时部分（蜂鸣器 1 秒）放在 FB_Buzzer 中。
"""

# 蜂鸣器 FB：trig=1 期间蜂鸣 1 秒后自动停（TON 在 FB 内，定时不进 OB1）
FB_BUZZER = {
    "interface": {
        "IN": {"trig": 0, "pt": 1000},
        "OUT": {"buzz": 0},
        "STAT": {},
    },
    "networks": [
        {"id": "BZ1", "title": "蜂鸣定时", "rungs": [
            {"id": "R1", "series": [{"k": "NO", "addr": "#trig", "label": "触发"}],
             "outputs": [{"k": "TON", "inst": "#T1", "pt": "#pt"}]},
            {"id": "R2", "series": [{"k": "NO", "addr": "#trig"},
                                    {"k": "NC", "addr": "#T1.Q", "label": "1秒到"}],
             "outputs": [{"k": "COIL", "addr": "#buzz"}]},
        ]},
    ],
}

# N1 抢答锁存：8 路，每路 SET 前串忙标志常闭互锁
_N1_RUNGS = [
    {"id": f"R{x + 1}",
     "series": [{"k": "NO", "addr": f"I0.{x}", "label": f"SB{x + 1}"},
                {"k": "NC", "addr": "M1.0", "label": "互锁"}],
     "outputs": [{"k": "SET", "addr": f"M0.{x}"}]}
    for x in range(8)
]

# N3 号码译码：命中哪路就把路号 MOVE 进 MB10
_N3_RUNGS = [
    {"id": f"R{x + 1}", "series": [{"k": "NO", "addr": f"M0.{x}"}],
     "outputs": [{"k": "MOVE", "src": x + 1, "dst": "MB10"}]}
    for x in range(8)
]

CONFIG = {
    "id": "p1_quiz_buzzer",
    "name": "项目1 八路抢答器",
    "desc": "互锁、锁存、SEG 译码：抢先锁存一路并屏蔽其余，数码管显示路号，蜂鸣器响 1 秒。",
    "fbs": {"FB_Buzzer": FB_BUZZER},
    "networks": [
        {"id": "N1", "title": "抢答锁存（SET + 互锁）", "rungs": _N1_RUNGS},
        {"id": "N2", "title": "忙标志（任一路命中即忙）", "rungs": [
            {"id": "R1",
             "branches": [[{"k": "NO", "addr": f"M0.{x}"}] for x in range(8)],
             "outputs": [{"k": "COIL", "addr": "M1.0"}]},
        ]},
        {"id": "N3", "title": "号码译码", "rungs": _N3_RUNGS},
        {"id": "N4", "title": "数码管驱动（SEG）", "rungs": [
            {"id": "R1", "series": [{"k": "CMP", "op": "==", "a": 1, "b": 1, "label": "恒通"}],
             "outputs": [{"k": "SEG", "src": "MB10", "dst": "QB0"}]},
        ]},
        {"id": "N5", "title": "主持人复位", "rungs": [
            {"id": "R1", "series": [{"k": "NO", "addr": "I1.0", "label": "复位"}],
             "outputs": [{"k": "RST", "addr": f"M0.{x}"} for x in range(8)]
                        + [{"k": "MOVE", "src": 255, "dst": "MB10"}]},
        ]},
        {"id": "N6", "title": "蜂鸣器（FB 调用）", "rungs": [
            {"id": "R1", "series": [{"k": "NO", "addr": "M1.0", "label": "有人抢中"}],
             "outputs": [{"k": "CALL", "fb": "FB_Buzzer", "inst": "DB_BUZ",
                          "args": {"trig": "M1.0", "buzz": "Q1.0"}}]},
        ]},
    ],
    "io_map": [
        *[{"addr": f"I0.{x}", "label": f"SB{x + 1} 抢答按钮", "device": "button",
           "kind": "input"} for x in range(8)],
        {"addr": "I1.0", "label": "SB9 主持人复位", "device": "button", "kind": "input"},
        *[{"addr": f"Q0.{x}", "label": f"数码管段 {chr(ord('a') + x)}", "device": "seg7",
           "kind": "output"} for x in range(7)],
        {"addr": "Q1.0", "label": "HA 蜂鸣器", "device": "buzzer", "kind": "output"},
    ],
    "stages": [
        {"name": "等待抢答", "when": [["M1.0", 0]]},
        {"name": "抢答锁定", "when": [["M1.0", 1]], "timer": "DB_BUZ.T1"},
    ],
    "faults": [
        {"id": "NO_INTERLOCK", "desc": "程序漏互锁（典型错误：后按覆盖先按）",
         "kind": "variant",
         "drop": [f"N1.R{x + 1}.s1" for x in range(8)],
         "hints": {
             "method": "现象：第一人抢中后，后面的人再按，数码管号码被覆盖。",
             "direction": "对比正常程序：每路 SET 之前应该串联一个“忙标志”的常闭触点。",
             "answer": "在每路 SET(M0.x) 前串联 NC(M1.0) 互锁触点，第一人命中后 M1.0=1 屏蔽其余各路。"}},
        {"id": "BTN3_STUCK", "desc": "3 号按钮卡死（输入常 1）",
         "kind": "force", "addr": "I0.2", "value": 1,
         "hints": {
             "method": "现象：复位后数码管立刻显示 3，无法再抢答。",
             "direction": "看 IO 状态表：没有任何操作时哪个输入位恒为 1？",
             "answer": "I0.2 恒 1，3 号按钮机械卡死，需更换按钮。"}},
        {"id": "SEG_A_OPEN", "desc": "数码管 a 段断线",
         "kind": "force", "addr": "Q0.0", "value": 0,
         "hints": {
             "method": "现象：某些数字缺最上面一横（如 7 显示异常）。",
             "direction": "程序里 SEG 输出正常（看 Q0.0 映像为 1），但灯不亮——问题在线路。",
             "answer": "a 段（Q0.0）接线断线，重新压接端子。"}},
    ],
    "cards": [
        {"title": "互锁原理", "rows": [
            ["无互锁", "多路同时置位，号码被后按者覆盖"],
            ["有互锁", "首路命中 → 忙标志 M1.0=1 → 其余 7 路被常闭触点切断"]],
         "note": "互锁是抢答器的灵魂：用“已经有人抢中”这个状态去封锁后来者。"},
        {"title": "SEG 七段译码表", "rows": [
            ["0", "0x3F"], ["1", "0x06"], ["2", "0x5B"], ["3", "0x4F"], ["4", "0x66"],
            ["5", "0x6D"], ["6", "0x7D"], ["7", "0x07"], ["8", "0x7F"], ["9", "0x6F"]],
         "note": "位 0-6 对应段 a-g；本卡数据与程序内 SEG 指令同一张表。",
         "live": {"label": "当前 QB0 输出（十六进制）", "addr": "QB0"}},
        {"title": "扫描周期与“滞后一拍”", "rows": [
            ["① 采样", "输入信号锁存进 I 映像"],
            ["② 执行", "OB1 按网络顺序求解"],
            ["③ 刷新", "Q 映像写到输出"],
            ["滞后一拍", "按钮在两次采样之间按下 → 波形上晚一个周期才看到"]],
         "note": "到示波器视图按一次按钮，亲眼看这一拍滞后。"},
    ],
    "scene": {
        "devices": [
            *[{"type": "button", "addr": f"I0.{x}", "label": f"SB{x + 1}",
               "color": ("red" if x < 4 else "blue"),
               "pos": [-2.6 + (x % 4) * 1.05, 0.55, -0.4 + (x // 4) * 1.0]}
              for x in range(8)],
            {"type": "button", "addr": "I1.0", "label": "复位", "color": "yellow",
             "pos": [3.2, 0.55, 1.2]},
            {"type": "seg7", "mode": "raw", "base": "Q0.0", "label": "DS1",
             "pos": [0, 1.5, -1.6]},
            {"type": "buzzer", "addr": "Q1.0", "label": "HA", "pos": [3.2, 0.55, -0.4]},
        ],
    },
}
