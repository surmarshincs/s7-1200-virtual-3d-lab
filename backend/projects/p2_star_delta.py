# -*- coding: utf-8 -*-
"""项目2：三相异步电机星三角降压启动。

IO：I0.0 启动(NO)、I0.1 停止(NC)、I0.2 热继电器(NC)；
    Q0.0 主接触器 KM1、Q0.1 星接 KMY、Q0.2 角接 KMΔ、Q0.3 运行指示灯。
逻辑（定时全部在 FB 内）：启动 → KM1+KMY 星形启动，TON 5s（可调）→
      断 KMY，TON 0.5s 换相死区 → KMΔ 角接运行 → 停止/FR 全断。
教学点：双互锁（程序 NC 互锁 + 3D 场景电气互锁说明）、换相死区、降压启动。
"""

FB_STAR_DELTA = {
    "interface": {
        "IN": {"start": 0, "stop": 1, "fr": 1, "pt_star": 5000, "pt_gap": 500},
        "OUT": {"km1": 0, "kmy": 0, "kmd": 0, "lamp": 0},
        "STAT": {"step": 0, "run": 0},
    },
    "networks": [
        {"id": "SD1", "title": "运行保持（启保停）", "rungs": [
            {"id": "R1",
             "branches": [[{"k": "NO", "addr": "#start", "label": "启动"}],
                          [{"k": "NO", "addr": "#run", "label": "自锁"}]],
             "series": [{"k": "NO", "addr": "#stop", "label": "停止"},
                        {"k": "NO", "addr": "#fr", "label": "热继"}],
             "outputs": [{"k": "COIL", "addr": "#run"}]},
        ]},
        {"id": "SD2", "title": "步进转换（状态机）", "rungs": [
            {"id": "R1", "series": [{"k": "NO", "addr": "#run"},
                                    {"k": "CMP", "op": "==", "a": "#step", "b": 0}],
             "outputs": [{"k": "MOVE", "src": 1, "dst": "#step"}]},
            {"id": "R2", "series": [{"k": "CMP", "op": "==", "a": "#step", "b": 1},
                                    {"k": "NO", "addr": "#T1.Q", "label": "星接5s到"}],
             "outputs": [{"k": "MOVE", "src": 2, "dst": "#step"}]},
            {"id": "R3", "series": [{"k": "CMP", "op": "==", "a": "#step", "b": 2},
                                    {"k": "NO", "addr": "#T2.Q", "label": "死区0.5s到"}],
             "outputs": [{"k": "MOVE", "src": 3, "dst": "#step"}]},
            {"id": "R4", "series": [{"k": "NC", "addr": "#run"}],
             "outputs": [{"k": "MOVE", "src": 0, "dst": "#step"}]},
        ]},
        {"id": "SD3", "title": "定时器（星接计时 / 换相死区）", "rungs": [
            {"id": "R1", "series": [{"k": "CMP", "op": "==", "a": "#step", "b": 1}],
             "outputs": [{"k": "TON", "inst": "#T1", "pt": "#pt_star"}]},
            {"id": "R2", "series": [{"k": "CMP", "op": "==", "a": "#step", "b": 2}],
             "outputs": [{"k": "TON", "inst": "#T2", "pt": "#pt_gap"}]},
        ]},
        {"id": "SD4", "title": "输出（KMY/KMΔ 程序互锁）", "rungs": [
            {"id": "R1", "series": [{"k": "NO", "addr": "#run"},
                                    {"k": "CMP", "op": ">=", "a": "#step", "b": 1}],
             "outputs": [{"k": "COIL", "addr": "#km1"}]},
            {"id": "R2", "series": [{"k": "CMP", "op": "==", "a": "#step", "b": 1},
                                    {"k": "NC", "addr": "#kmd", "label": "互锁KMΔ"}],
             "outputs": [{"k": "COIL", "addr": "#kmy"}]},
            {"id": "R3", "series": [{"k": "CMP", "op": "==", "a": "#step", "b": 3},
                                    {"k": "NC", "addr": "#kmy", "label": "互锁KMY"}],
             "outputs": [{"k": "COIL", "addr": "#kmd"}]},
            {"id": "R4", "series": [{"k": "NO", "addr": "#run"}],
             "outputs": [{"k": "COIL", "addr": "#lamp"}]},
        ]},
    ],
}

CONFIG = {
    "id": "p2_star_delta",
    "name": "项目2 星三角降压启动",
    "desc": "星接降压启动 5 秒 → 0.5 秒换相死区 → 角接全压运行；KMY/KMΔ 程序+电气双互锁。",
    "fbs": {"FB_StarDelta": FB_STAR_DELTA},
    "networks": [
        {"id": "N1", "title": "调用星三角 FB（OB1 只写调用逻辑）", "rungs": [
            {"id": "R1", "series": [{"k": "CMP", "op": "==", "a": 1, "b": 1, "label": "恒通"}],
             "outputs": [{"k": "CALL", "fb": "FB_StarDelta", "inst": "DB_SD",
                          "args": {"start": "I0.0", "stop": "I0.1", "fr": "I0.2",
                                   "km1": "Q0.0", "kmy": "Q0.1", "kmd": "Q0.2",
                                   "lamp": "Q0.3"}}]},
        ]},
    ],
    "io_map": [
        {"addr": "I0.0", "label": "SB1 启动(NO)", "device": "button", "kind": "input"},
        {"addr": "I0.1", "label": "SB2 停止(NC)", "device": "button", "kind": "input"},
        {"addr": "I0.2", "label": "FR 热继电器(NC)", "device": "switch", "kind": "input"},
        {"addr": "Q0.0", "label": "KM1 主接触器", "device": "contactor", "kind": "output"},
        {"addr": "Q0.1", "label": "KMY 星接接触器", "device": "contactor", "kind": "output"},
        {"addr": "Q0.2", "label": "KMΔ 角接接触器", "device": "contactor", "kind": "output"},
        {"addr": "Q0.3", "label": "HL 运行灯(绿)", "device": "lamp", "kind": "output"},
    ],
    "stages": [
        {"name": "待机", "when": [["DB_SD.step", 0]]},
        {"name": "星形启动中", "when": [["DB_SD.step", 1]], "timer": "DB_SD.T1"},
        {"name": "换相死区", "when": [["DB_SD.step", 2]], "timer": "DB_SD.T2"},
        {"name": "角接运行", "when": [["DB_SD.step", 3]]},
    ],
    "faults": [
        {"id": "FR_TRIP", "desc": "热继电器 FR 动作（过载跳闸）",
         "kind": "force", "addr": "I0.2", "value": 0,
         "hints": {
             "method": "现象：运行中全部接触器突然释放，再按启动也起不来。",
             "direction": "看 IO 表 I0.2：正常应为 1（常闭），动作后为 0。",
             "answer": "FR 动作说明电机过载或整定电流过小，排除过载后手动复位热继电器。"}},
        {"id": "NO_INTERLOCK", "desc": "程序漏互锁（KMY/KMΔ 可能同时吸合）",
         "kind": "variant", "drop": ["SD4.R2.s1", "SD4.R3.s1"],
         "hints": {
             "method": "现象：换相瞬间 KMY 与 KMΔ 有同时吸合的风险，主回路短路。",
             "direction": "检查 SD4 网络 KMY/KMΔ 线圈前是否串了对方的常闭触点。",
             "answer": "KMY 线圈前串 NC(KMΔ)、KMΔ 线圈前串 NC(KMY)，且电气上两接触器也要互锁。"}},
        {"id": "KMY_WELD", "desc": "KMY 触点粘连（释放不断）",
         "kind": "force", "addr": "Q0.1", "value": 1,
         "hints": {
             "method": "现象：进入角接后星接接触器仍未释放，接线盒内连接片状态异常。",
             "direction": "程序映像 Q0.1=0 而实际接触器仍吸合——程序之外的问题。",
             "answer": "KMY 主触点电弧烧蚀粘连，需更换接触器；这就是双互锁存在的意义。"}},
    ],
    "cards": [
        {"title": "星接 vs 角接", "rows": [
            ["绕组电压", "星接 220V / 角接 380V"],
            ["启动电流", "星接 = 角接直接启动的 1/3"],
            ["转矩", "星接 = 角接的 1/3（故只用于轻载启动）"]],
         "note": "降压启动的本质：先星接限制启动电流，转速起来后切角接全压运行。",
         "live": {"label": "当前实测电流", "addr": "Q0.0"}},
        {"title": "为什么要换相死区", "rows": [
            ["无死区", "KMY 未释放 KMΔ 就吸合 → 电源经两接触器短路"],
            ["0.5s 死区", "确保电弧熄灭、触点可靠释放后再投角接"]],
         "note": "死区时间过短拉弧，过长则电机掉速——0.3~1s 为工程常用值。"},
    ],
    "scene": {
        "devices": [
            {"type": "button", "addr": "I0.0", "label": "SB1 启动", "color": "green",
             "pos": [-3.0, 0.55, 1.6]},
            {"type": "button", "addr": "I0.1", "label": "SB2 停止", "color": "red", "nc": True,
             "pos": [-2.0, 0.55, 1.6]},
            {"type": "switch", "addr": "I0.2", "label": "FR", "nc": True,
             "pos": [-1.0, 0.55, 1.6]},
            {"type": "lamp", "addr": "Q0.3", "label": "HL", "color": "green",
             "pos": [0.2, 0.55, 1.6]},
            {"type": "contactor", "addr": "Q0.0", "label": "KM1", "pos": [-2.4, 0.9, -1.2]},
            {"type": "contactor", "addr": "Q0.1", "label": "KMY", "pos": [-1.2, 0.9, -1.2]},
            {"type": "contactor", "addr": "Q0.2", "label": "KMΔ", "pos": [0.0, 0.9, -1.2]},
            {"type": "motor", "label": "M 3~",
             "fwd": {"and": [["Q0.0", 1], {"or": ["Q0.1", "Q0.2"]}]},
             "pos": [2.4, 0.75, -0.6], "star_delta": True},
        ],
    },
}
