# -*- coding: utf-8 -*-
"""项目3：运料小车自动往返。

IO：I0.0 右限位、I0.1 左限位、I0.2 启动、I0.3 停止(NC)、I0.4 热继电器(NC)；
    Q0.0 右行、Q0.1 左行（正反转互锁）、Q0.2 卸料灯(黄)、Q0.3 装料灯(红)。
逻辑（FB 状态机）：启动 → 右行 → 右限位停 → TON 卸料 5s → 左行 →
      左限位停 → TON 装料 5s → 循环；停止任意时刻有效；CTU 计往返次数。
教学点：行程开关、往返自动、正反转互锁、状态机。
"""

FB_CAR = {
    "interface": {
        "IN": {"sq_r": 0, "sq_l": 0, "start": 0, "stop": 1, "fr": 1,
               "t_unload": 5000, "t_load": 5000},
        "OUT": {"mtr_r": 0, "mtr_l": 0, "lamp_u": 0, "lamp_l": 0},
        "STAT": {"state": 0, "run": 0, "trips": 0},
    },
    "networks": [
        {"id": "C1", "title": "运行保持", "rungs": [
            {"id": "R1",
             "branches": [[{"k": "NO", "addr": "#start", "label": "启动"}],
                          [{"k": "NO", "addr": "#run", "label": "自锁"}]],
             "series": [{"k": "NO", "addr": "#stop", "label": "停止"},
                        {"k": "NO", "addr": "#fr", "label": "热继"}],
             "outputs": [{"k": "COIL", "addr": "#run"}]},
        ]},
        {"id": "C2", "title": "状态机转换（0待机 1右行 2卸料 3左行 4装料）", "rungs": [
            {"id": "R1", "series": [{"k": "NO", "addr": "#run"},
                                    {"k": "CMP", "op": "==", "a": "#state", "b": 0}],
             "outputs": [{"k": "MOVE", "src": 1, "dst": "#state"}]},
            {"id": "R2", "series": [{"k": "CMP", "op": "==", "a": "#state", "b": 1},
                                    {"k": "NO", "addr": "#sq_r", "label": "右限位"}],
             "outputs": [{"k": "MOVE", "src": 2, "dst": "#state"}]},
            {"id": "R3", "series": [{"k": "CMP", "op": "==", "a": "#state", "b": 2},
                                    {"k": "NO", "addr": "#T_u.Q", "label": "卸料5s到"}],
             "outputs": [{"k": "MOVE", "src": 3, "dst": "#state"}]},
            {"id": "R4", "series": [{"k": "CMP", "op": "==", "a": "#state", "b": 3},
                                    {"k": "NO", "addr": "#sq_l", "label": "左限位"}],
             "outputs": [{"k": "MOVE", "src": 4, "dst": "#state"}]},
            {"id": "R5", "series": [{"k": "CMP", "op": "==", "a": "#state", "b": 4},
                                    {"k": "NO", "addr": "#T_l.Q", "label": "装料5s到"}],
             "outputs": [{"k": "MOVE", "src": 1, "dst": "#state"}]},
            {"id": "R6", "series": [{"k": "NC", "addr": "#run"}],
             "outputs": [{"k": "MOVE", "src": 0, "dst": "#state"}]},
        ]},
        {"id": "C3", "title": "装卸料定时", "rungs": [
            {"id": "R1", "series": [{"k": "CMP", "op": "==", "a": "#state", "b": 2}],
             "outputs": [{"k": "TON", "inst": "#T_u", "pt": "#t_unload"}]},
            {"id": "R2", "series": [{"k": "CMP", "op": "==", "a": "#state", "b": 4}],
             "outputs": [{"k": "TON", "inst": "#T_l", "pt": "#t_load"}]},
        ]},
        {"id": "C4", "title": "往返计数（CTU）", "rungs": [
            {"id": "R1", "series": [{"k": "CMP", "op": "==", "a": "#state", "b": 4}],
             "outputs": [{"k": "CTU", "inst": "#C1", "pv": 9999}]},
            {"id": "R2", "series": [{"k": "CMP", "op": "==", "a": 1, "b": 1, "label": "恒通"}],
             "outputs": [{"k": "MOVE", "src": "#C1.CV", "dst": "#trips"}]},
        ]},
        {"id": "C5", "title": "输出（正反转互锁 + 装卸料灯）", "rungs": [
            {"id": "R1", "series": [{"k": "CMP", "op": "==", "a": "#state", "b": 1},
                                    {"k": "NC", "addr": "#mtr_l", "label": "互锁"}],
             "outputs": [{"k": "COIL", "addr": "#mtr_r"}]},
            {"id": "R2", "series": [{"k": "CMP", "op": "==", "a": "#state", "b": 3},
                                    {"k": "NC", "addr": "#mtr_r", "label": "互锁"}],
             "outputs": [{"k": "COIL", "addr": "#mtr_l"}]},
            {"id": "R3", "series": [{"k": "CMP", "op": "==", "a": "#state", "b": 2}],
             "outputs": [{"k": "COIL", "addr": "#lamp_u"}]},
            {"id": "R4", "series": [{"k": "CMP", "op": "==", "a": "#state", "b": 4}],
             "outputs": [{"k": "COIL", "addr": "#lamp_l"}]},
        ]},
    ],
}

CONFIG = {
    "id": "p3_shuttle_car",
    "name": "项目3 运料小车自动往返",
    "desc": "右行→右限位→卸料5s→左行→左限位→装料5s→循环；CTU 计往返次数。",
    "fbs": {"FB_CarShuttle": FB_CAR},
    "networks": [
        {"id": "N1", "title": "调用小车 FB（OB1 只写调用逻辑）", "rungs": [
            {"id": "R1", "series": [{"k": "CMP", "op": "==", "a": 1, "b": 1, "label": "恒通"}],
             "outputs": [{"k": "CALL", "fb": "FB_CarShuttle", "inst": "DB_CAR",
                          "args": {"sq_r": "I0.0", "sq_l": "I0.1", "start": "I0.2",
                                   "stop": "I0.3", "fr": "I0.4",
                                   "mtr_r": "Q0.0", "mtr_l": "Q0.1",
                                   "lamp_u": "Q0.2", "lamp_l": "Q0.3"}}]},
        ]},
    ],
    "io_map": [
        {"addr": "I0.0", "label": "SQ1 右限位", "device": "limit", "kind": "input"},
        {"addr": "I0.1", "label": "SQ2 左限位", "device": "limit", "kind": "input"},
        {"addr": "I0.2", "label": "SB1 启动", "device": "button", "kind": "input"},
        {"addr": "I0.3", "label": "SB2 停止(NC)", "device": "button", "kind": "input"},
        {"addr": "I0.4", "label": "FR 热继电器(NC)", "device": "switch", "kind": "input"},
        {"addr": "Q0.0", "label": "KM1 右行", "device": "contactor", "kind": "output"},
        {"addr": "Q0.1", "label": "KM2 左行", "device": "contactor", "kind": "output"},
        {"addr": "Q0.2", "label": "HL1 卸料灯(黄)", "device": "lamp", "kind": "output"},
        {"addr": "Q0.3", "label": "HL2 装料灯(红)", "device": "lamp", "kind": "output"},
    ],
    "stages": [
        {"name": "待机", "when": [["DB_CAR.state", 0]]},
        {"name": "右行中", "when": [["DB_CAR.state", 1]]},
        {"name": "卸料中", "when": [["DB_CAR.state", 2]], "timer": "DB_CAR.T_u"},
        {"name": "左行中", "when": [["DB_CAR.state", 3]]},
        {"name": "装料中", "when": [["DB_CAR.state", 4]], "timer": "DB_CAR.T_l"},
    ],
    "faults": [
        {"id": "SQ_L_FAIL", "desc": "左限位开关失效（撞块撞了也不动作）",
         "kind": "force", "addr": "I0.1", "value": 0,
         "hints": {
             "method": "现象：小车到左端不停，一直顶着限位（3D 里可见撞块已压下限位）。",
             "direction": "对比 3D 里限位开关的机械状态与 IO 表 I0.1 的电平是否一致。",
             "answer": "限位开关触点损坏或接线断开，机械压下但 I0.1 仍为 0，需更换 SQ2。"}},
        {"id": "FR_TRIP", "desc": "热继电器 FR 动作",
         "kind": "force", "addr": "I0.4", "value": 0,
         "hints": {
             "method": "现象：小车立刻停车，按启动无反应。",
             "direction": "IO 表里 I0.4 应为 1，动作后为 0。",
             "answer": "电机过载导致 FR 动作，检查轨道是否卡阻后复位热继电器。"}},
        {"id": "NO_INTERLOCK", "desc": "程序漏互锁（正反转可能同时输出）",
         "kind": "variant", "drop": ["C5.R1.s1", "C5.R2.s1"],
         "hints": {
             "method": "现象：状态切换瞬间右行/左行接触器可能同时吸合。",
             "direction": "检查 C5 网络两个方向线圈前是否串了对方的常闭触点。",
             "answer": "右行线圈前串 NC(左行)、左行线圈前串 NC(右行)，正反转必须互锁。"}},
    ],
    "cards": [
        {"title": "状态机思维", "rows": [
            ["0 待机", "等待启动"], ["1 右行", "Q0.0=1，直到右限位"],
            ["2 卸料", "TON 5s"], ["3 左行", "Q0.1=1，直到左限位"], ["4 装料", "TON 5s"]],
         "note": "每个状态只关心“转到下一个状态的条件”，状态机是顺序控制的通用解法。",
         "live": {"label": "当前状态 state", "addr": "DB_CAR.state"}},
        {"title": "行程开关 = 位置→电信号", "rows": [
            ["撞块压下", "触点闭合，I 映像对应位置 1"],
            ["采样滞后", "压下瞬间到程序看见，最多晚一个扫描周期"]],
         "note": "到示波器观察 I0.0 波形与小车实际位置的对应关系。"},
    ],
    "scene": {
        "devices": [
            {"type": "limit", "addr": "I0.0", "label": "SQ1 右", "pos": [3.4, 0.5, -0.9]},
            {"type": "limit", "addr": "I0.1", "label": "SQ2 左", "pos": [-3.4, 0.5, -0.9]},
            {"type": "button", "addr": "I0.2", "label": "SB1 启动", "color": "green",
             "pos": [-1.2, 0.55, 1.8]},
            {"type": "button", "addr": "I0.3", "label": "SB2 停止", "color": "red", "nc": True,
             "pos": [-0.2, 0.55, 1.8]},
            {"type": "switch", "addr": "I0.4", "label": "FR", "nc": True,
             "pos": [0.8, 0.55, 1.8]},
            {"type": "lamp", "addr": "Q0.2", "label": "卸料", "color": "yellow",
             "pos": [3.4, 1.6, -1.4]},
            {"type": "lamp", "addr": "Q0.3", "label": "装料", "color": "red",
             "pos": [-3.4, 1.6, -1.4]},
            {"type": "car", "fwd": "Q0.0", "rev": "Q0.1", "label": "小车",
             "pos": [0, 0.62, -0.9], "rail": [-3.2, 3.2]},
            {"type": "motor", "label": "M 驱动", "fwd": "Q0.0", "rev": "Q0.1",
             "pos": [0, 0.75, -2.2]},
            {"type": "hopper", "label": "卸料斗", "pos": [3.4, 1.2, -2.0]},
            {"type": "counter", "db": "DB_CAR", "field": "trips", "label": "往返次数",
             "pos": [2.0, 0.55, 1.8]},
        ],
    },
}
