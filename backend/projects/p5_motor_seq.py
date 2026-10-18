# -*- coding: utf-8 -*-
"""项目5：电动机组顺序启停控制。

IO：I0.0 启动、I0.1 停止(NC)、I0.2/I0.3/I0.4 三台电机热继 FR1/FR2/FR3(NC)；
    Q0.0/Q0.1/Q0.2 接触器 KM1/KM2/KM3，Q0.3/Q0.4/Q0.5 运行灯 绿/黄/红。
逻辑（FB）：顺启 KM1→3s→KM2→3s→KM3；逆停 KM3→3s→KM2→3s→KM1；
    任一 FR 动作全组立即断开（故障联锁）。
教学点：顺启逆停、延时链、故障联锁。

状态编码 step：0 待机 / 1 仅KM1·延时中 / 2 KM1+KM2·延时中 / 3 全组运行 /
               4 逆停·KM3已断·延时中 / 5 逆停·KM2已断·延时中
"""

FB_SEQ = {
    "interface": {
        "IN": {"start": 0, "stop": 1, "fr1": 1, "fr2": 1, "fr3": 1, "t_step": 3000},
        "OUT": {"km1": 0, "km2": 0, "km3": 0, "l1": 0, "l2": 0, "l3": 0},
        "STAT": {"step": 0, "run": 0},
    },
    "networks": [
        {"id": "S1", "title": "运行保持与故障联锁", "rungs": [
            {"id": "R1",
             "branches": [[{"k": "NO", "addr": "#start", "label": "启动"}],
                          [{"k": "NO", "addr": "#run", "label": "自锁"}]],
             "series": [{"k": "NO", "addr": "#stop", "label": "停止"},
                        {"k": "NO", "addr": "#fr1", "label": "FR1"},
                        {"k": "NO", "addr": "#fr2", "label": "FR2"},
                        {"k": "NO", "addr": "#fr3", "label": "FR3"}],
             "outputs": [{"k": "COIL", "addr": "#run"}]},
            {"id": "R2",
             "branches": [[{"k": "NC", "addr": "#fr1"}], [{"k": "NC", "addr": "#fr2"}],
                          [{"k": "NC", "addr": "#fr3"}]],
             "outputs": [{"k": "MOVE", "src": 0, "dst": "#step"},
                         {"k": "RST", "addr": "#run"}]},
        ]},
        {"id": "S2", "title": "顺启转换（KM1→3s→KM2→3s→KM3）", "rungs": [
            {"id": "R1", "series": [{"k": "NO", "addr": "#run"},
                                    {"k": "CMP", "op": "==", "a": "#step", "b": 0}],
             "outputs": [{"k": "MOVE", "src": 1, "dst": "#step"}]},
            {"id": "R2", "series": [{"k": "CMP", "op": "==", "a": "#step", "b": 1},
                                    {"k": "NO", "addr": "#T1.Q", "label": "3s到"}],
             "outputs": [{"k": "MOVE", "src": 2, "dst": "#step"}]},
            {"id": "R3", "series": [{"k": "CMP", "op": "==", "a": "#step", "b": 2},
                                    {"k": "NO", "addr": "#T2.Q", "label": "3s到"}],
             "outputs": [{"k": "MOVE", "src": 3, "dst": "#step"}]},
        ]},
        {"id": "S3", "title": "逆停转换（KM3→3s→KM2→3s→KM1）", "rungs": [
            {"id": "R1", "series": [{"k": "NC", "addr": "#run"},
                                    {"k": "CMP", "op": "==", "a": "#step", "b": 3}],
             "outputs": [{"k": "MOVE", "src": 4, "dst": "#step"}]},
            {"id": "R2", "series": [{"k": "NC", "addr": "#run"},
                                    {"k": "CMP", "op": "==", "a": "#step", "b": 1}],
             "outputs": [{"k": "MOVE", "src": 0, "dst": "#step"}]},
            {"id": "R3", "series": [{"k": "NC", "addr": "#run"},
                                    {"k": "CMP", "op": "==", "a": "#step", "b": 2}],
             "outputs": [{"k": "MOVE", "src": 0, "dst": "#step"}]},
            {"id": "R4", "series": [{"k": "CMP", "op": "==", "a": "#step", "b": 4},
                                    {"k": "NO", "addr": "#T1.Q", "label": "3s到"}],
             "outputs": [{"k": "MOVE", "src": 5, "dst": "#step"}]},
            {"id": "R5", "series": [{"k": "CMP", "op": "==", "a": "#step", "b": 5},
                                    {"k": "NO", "addr": "#T2.Q", "label": "3s到"}],
             "outputs": [{"k": "MOVE", "src": 0, "dst": "#step"}]},
        ]},
        {"id": "S4", "title": "延时链（T1/T2 顺启逆停复用）", "rungs": [
            {"id": "R1", "branches": [[{"k": "CMP", "op": "==", "a": "#step", "b": 1}],
                                      [{"k": "CMP", "op": "==", "a": "#step", "b": 4}]],
             "outputs": [{"k": "TON", "inst": "#T1", "pt": "#t_step"}]},
            {"id": "R2", "branches": [[{"k": "CMP", "op": "==", "a": "#step", "b": 2}],
                                      [{"k": "CMP", "op": "==", "a": "#step", "b": 5}]],
             "outputs": [{"k": "TON", "inst": "#T2", "pt": "#t_step"}]},
        ]},
        {"id": "S5", "title": "输出与运行灯", "rungs": [
            {"id": "R1", "series": [{"k": "CMP", "op": ">=", "a": "#step", "b": 1}],
             "outputs": [{"k": "COIL", "addr": "#km1"}]},
            {"id": "R2", "series": [{"k": "CMP", "op": ">=", "a": "#step", "b": 2},
                                    {"k": "CMP", "op": "<=", "a": "#step", "b": 4}],
             "outputs": [{"k": "COIL", "addr": "#km2"}]},
            {"id": "R3", "series": [{"k": "CMP", "op": "==", "a": "#step", "b": 3}],
             "outputs": [{"k": "COIL", "addr": "#km3"}]},
            {"id": "R4", "series": [{"k": "NO", "addr": "#km1"}],
             "outputs": [{"k": "COIL", "addr": "#l1"}]},
            {"id": "R5", "series": [{"k": "NO", "addr": "#km2"}],
             "outputs": [{"k": "COIL", "addr": "#l2"}]},
            {"id": "R6", "series": [{"k": "NO", "addr": "#km3"}],
             "outputs": [{"k": "COIL", "addr": "#l3"}]},
        ]},
    ],
}

CONFIG = {
    "id": "p5_motor_seq",
    "name": "项目5 电机组顺序启停",
    "desc": "顺启 KM1→KM2→KM3（各 3s），逆停 KM3→KM2→KM1（各 3s），任一 FR 全组断开。",
    "fbs": {"FB_SeqStart": FB_SEQ},
    "networks": [
        {"id": "N1", "title": "调用顺启逆停 FB（OB1 只写调用逻辑）", "rungs": [
            {"id": "R1", "series": [{"k": "CMP", "op": "==", "a": 1, "b": 1, "label": "恒通"}],
             "outputs": [{"k": "CALL", "fb": "FB_SeqStart", "inst": "DB_SEQ",
                          "args": {"start": "I0.0", "stop": "I0.1",
                                   "fr1": "I0.2", "fr2": "I0.3", "fr3": "I0.4",
                                   "km1": "Q0.0", "km2": "Q0.1", "km3": "Q0.2",
                                   "l1": "Q0.3", "l2": "Q0.4", "l3": "Q0.5"}}]},
        ]},
    ],
    "io_map": [
        {"addr": "I0.0", "label": "SB1 启动", "device": "button", "kind": "input"},
        {"addr": "I0.1", "label": "SB2 停止(NC)", "device": "button", "kind": "input"},
        {"addr": "I0.2", "label": "FR1 热继(NC)", "device": "switch", "kind": "input"},
        {"addr": "I0.3", "label": "FR2 热继(NC)", "device": "switch", "kind": "input"},
        {"addr": "I0.4", "label": "FR3 热继(NC)", "device": "switch", "kind": "input"},
        {"addr": "Q0.0", "label": "KM1", "device": "contactor", "kind": "output"},
        {"addr": "Q0.1", "label": "KM2", "device": "contactor", "kind": "output"},
        {"addr": "Q0.2", "label": "KM3", "device": "contactor", "kind": "output"},
        {"addr": "Q0.3", "label": "HL1(绿)", "device": "lamp", "kind": "output"},
        {"addr": "Q0.4", "label": "HL2(黄)", "device": "lamp", "kind": "output"},
        {"addr": "Q0.5", "label": "HL3(红)", "device": "lamp", "kind": "output"},
    ],
    "stages": [
        {"name": "待机", "when": [["DB_SEQ.step", 0]]},
        {"name": "KM1 已启动·延时中", "when": [["DB_SEQ.step", 1]], "timer": "DB_SEQ.T1"},
        {"name": "KM2 已启动·延时中", "when": [["DB_SEQ.step", 2]], "timer": "DB_SEQ.T2"},
        {"name": "全组运行", "when": [["DB_SEQ.step", 3]]},
        {"name": "逆停·KM3 已断", "when": [["DB_SEQ.step", 4]], "timer": "DB_SEQ.T1"},
        {"name": "逆停·KM2 已断", "when": [["DB_SEQ.step", 5]], "timer": "DB_SEQ.T2"},
    ],
    "faults": [
        {"id": "FR2_TRIP", "desc": "FR2 动作（2 号电机过载）",
         "kind": "force", "addr": "I0.3", "value": 0,
         "hints": {
             "method": "现象：启动过程中全组突然断电，或运行中全组跳停。",
             "direction": "IO 表看 I0.2/I0.3/I0.4 哪个变成了 0——就是哪台电机过载。",
             "answer": "FR2 动作：2 号电机过载。排除机械卡阻后复位 FR2，再重新启动。"}},
    ],
    "cards": [
        {"title": "为什么要顺启逆停", "rows": [
            ["顺启", "避免多台电机同时启动造成电网冲击电流过大"],
            ["逆停", "后启动的先停：工艺上下游依赖（如先停传送末端）"],
            ["延时链", "T1/T2 两只定时器在顺启/逆停两条链上复用"]],
         "note": "展开 DB_SEQ 看 step 状态值，对照阶段地铁图理解状态机。",
         "live": {"label": "当前 step", "addr": "DB_SEQ.step"}},
    ],
    "scene": {
        "devices": [
            {"type": "button", "addr": "I0.0", "label": "SB1 启动", "color": "green",
             "pos": [-1.6, 0.55, 1.8]},
            {"type": "button", "addr": "I0.1", "label": "SB2 停止", "color": "red", "nc": True,
             "pos": [-0.6, 0.55, 1.8]},
            {"type": "switch", "addr": "I0.2", "label": "FR1", "nc": True, "pos": [0.4, 0.55, 1.8]},
            {"type": "switch", "addr": "I0.3", "label": "FR2", "nc": True, "pos": [1.2, 0.55, 1.8]},
            {"type": "switch", "addr": "I0.4", "label": "FR3", "nc": True, "pos": [2.0, 0.55, 1.8]},
            {"type": "motor", "label": "M1", "fwd": "Q0.0", "pos": [-2.2, 0.75, -0.8],
             "ammeter": True},
            {"type": "motor", "label": "M2", "fwd": "Q0.1", "pos": [0.0, 0.75, -0.8],
             "ammeter": True},
            {"type": "motor", "label": "M3", "fwd": "Q0.2", "pos": [2.2, 0.75, -0.8],
             "ammeter": True},
            {"type": "contactor", "addr": "Q0.0", "label": "KM1", "pos": [-2.2, 0.9, 0.5]},
            {"type": "contactor", "addr": "Q0.1", "label": "KM2", "pos": [0.0, 0.9, 0.5]},
            {"type": "contactor", "addr": "Q0.2", "label": "KM3", "pos": [2.2, 0.9, 0.5]},
            {"type": "lamp", "addr": "Q0.3", "label": "HL1", "color": "green", "pos": [-2.2, 1.9, 0.5]},
            {"type": "lamp", "addr": "Q0.4", "label": "HL2", "color": "yellow", "pos": [0.0, 1.9, 0.5]},
            {"type": "lamp", "addr": "Q0.5", "label": "HL3", "color": "red", "pos": [2.2, 1.9, 0.5]},
        ],
    },
}
