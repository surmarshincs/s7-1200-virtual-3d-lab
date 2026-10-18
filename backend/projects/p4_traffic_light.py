# -*- coding: utf-8 -*-
"""项目4：十字路口交通灯（FB/OB 模块化强制项目）。

IO（仅为演示外设，逻辑全部在 FB 内）：
    Q0.0 南北红、Q0.1 南北黄、Q0.2 南北绿、Q0.3 东西红、Q0.4 东西黄、Q0.5 东西绿。
强制结构：OB1 中仅含一次 CALL FB_TrafficLight（实例 DB_Traffic），
    由 core/blocks.py 的 validate_ob1_structure 强制校验。
时序：南北绿 25s → 南北黄 3s → 全红 1s → 东西绿 25s → 东西黄 3s → 全红 1s。
实现：T1 自复位相位主定时器（PT=#dur 按相位查表），T2 级联在 T1 之后做
    节拍寄存（pt=1 个虚拟毫秒，不引入附加延时）——这就是“2 个 TON 嵌套”。
教学点：FB 复用性、背景数据块、STAT 静态变量跨周期保持。
"""

FB_TRAFFIC = {
    "interface": {
        "IN": {"t_ns_green": 25000, "t_yellow": 3000, "t_red_all": 1000,
               "t_ew_green": 25000},
        "OUT": {"ns_r": 0, "ns_y": 0, "ns_g": 0, "ew_r": 0, "ew_y": 0, "ew_g": 0},
        "STAT": {"phase": 0, "dur": 25000},
    },
    "networks": [
        {"id": "T1", "title": "相位时长表（按相位查表装入 #dur）", "rungs": [
            {"id": "R1", "series": [{"k": "CMP", "op": "==", "a": "#phase", "b": 0}],
             "outputs": [{"k": "MOVE", "src": "#t_ns_green", "dst": "#dur"}]},
            {"id": "R2", "series": [{"k": "CMP", "op": "==", "a": "#phase", "b": 1}],
             "outputs": [{"k": "MOVE", "src": "#t_yellow", "dst": "#dur"}]},
            {"id": "R3", "series": [{"k": "CMP", "op": "==", "a": "#phase", "b": 2}],
             "outputs": [{"k": "MOVE", "src": "#t_red_all", "dst": "#dur"}]},
            {"id": "R4", "series": [{"k": "CMP", "op": "==", "a": "#phase", "b": 3}],
             "outputs": [{"k": "MOVE", "src": "#t_ew_green", "dst": "#dur"}]},
            {"id": "R5", "series": [{"k": "CMP", "op": "==", "a": "#phase", "b": 4}],
             "outputs": [{"k": "MOVE", "src": "#t_yellow", "dst": "#dur"}]},
            {"id": "R6", "series": [{"k": "CMP", "op": "==", "a": "#phase", "b": 5}],
             "outputs": [{"k": "MOVE", "src": "#t_red_all", "dst": "#dur"}]},
        ]},
        {"id": "T2", "title": "主定时器（自复位：到时下周期 ET 清零重计）", "rungs": [
            {"id": "R1", "series": [{"k": "NC", "addr": "#T1.Q", "label": "自复位"}],
             "outputs": [{"k": "TON", "inst": "#T1", "pt": "#dur"}]},
        ]},
        {"id": "T3", "title": "嵌套定时器（级联节拍寄存，pt=1 不引入附加延时）", "rungs": [
            {"id": "R1", "series": [{"k": "NO", "addr": "#T1.Q", "label": "相位到点"}],
             "outputs": [{"k": "TON", "inst": "#T2", "pt": 1}]},
        ]},
        {"id": "T4", "title": "相位推进（0→1→2→3→4→5→0 循环）", "rungs": [
            # 梯级按“高相位在前”逆序排列：同一周期内前面的梯级改了相位，
            # 后面的梯级不会再命中——这是梯形图防止单周期级联跳转的经典手法。
            *[{"id": f"R{6 - p}",
               "series": [{"k": "NO", "addr": "#T2.Q", "label": "节拍"},
                          {"k": "CMP", "op": "==", "a": "#phase", "b": p}],
               "outputs": [{"k": "MOVE", "src": (p + 1) % 6, "dst": "#phase"}]}
              for p in (5, 4, 3, 2, 1, 0)],
        ]},
        {"id": "T5", "title": "灯组译码（相位 → 六路灯）", "rungs": [
            {"id": "R1", "series": [{"k": "CMP", "op": "==", "a": "#phase", "b": 0}],
             "outputs": [{"k": "COIL", "addr": "#ns_g"}]},
            {"id": "R2", "series": [{"k": "CMP", "op": "==", "a": "#phase", "b": 1}],
             "outputs": [{"k": "COIL", "addr": "#ns_y"}]},
            {"id": "R3", "branches": [[{"k": "CMP", "op": "==", "a": "#phase", "b": p}]
                                      for p in (2, 3, 4, 5)],
             "outputs": [{"k": "COIL", "addr": "#ns_r"}]},
            {"id": "R4", "series": [{"k": "CMP", "op": "==", "a": "#phase", "b": 3}],
             "outputs": [{"k": "COIL", "addr": "#ew_g"}]},
            {"id": "R5", "series": [{"k": "CMP", "op": "==", "a": "#phase", "b": 4}],
             "outputs": [{"k": "COIL", "addr": "#ew_y"}]},
            {"id": "R6", "branches": [[{"k": "CMP", "op": "==", "a": "#phase", "b": p}]
                                      for p in (0, 1, 2, 5)],
             "outputs": [{"k": "COIL", "addr": "#ew_r"}]},
        ]},
    ],
}

CONFIG = {
    "id": "p4_traffic_light",
    "name": "项目4 十字路口交通灯",
    "desc": "OB1 仅一次 FB 调用；STAT 存相位，背景数据块 DB_Traffic 逐周期可见。",
    "require_single_call": True,
    "fbs": {"FB_TrafficLight": FB_TRAFFIC},
    "networks": [
        {"id": "N1", "title": "OB1：仅一次 FB_TrafficLight 调用", "rungs": [
            {"id": "R1", "series": [{"k": "CMP", "op": "==", "a": 1, "b": 1, "label": "恒通"}],
             "outputs": [{"k": "CALL", "fb": "FB_TrafficLight", "inst": "DB_Traffic",
                          "args": {"ns_r": "Q0.0", "ns_y": "Q0.1", "ns_g": "Q0.2",
                                   "ew_r": "Q0.3", "ew_y": "Q0.4", "ew_g": "Q0.5"}}]},
        ]},
    ],
    "io_map": [
        {"addr": "Q0.0", "label": "南北红", "device": "traffic", "kind": "output"},
        {"addr": "Q0.1", "label": "南北黄", "device": "traffic", "kind": "output"},
        {"addr": "Q0.2", "label": "南北绿", "device": "traffic", "kind": "output"},
        {"addr": "Q0.3", "label": "东西红", "device": "traffic", "kind": "output"},
        {"addr": "Q0.4", "label": "东西黄", "device": "traffic", "kind": "output"},
        {"addr": "Q0.5", "label": "东西绿", "device": "traffic", "kind": "output"},
    ],
    "stages": [
        {"name": "南北通行（绿）", "when": [["DB_Traffic.phase", 0]], "timer": "DB_Traffic.T1"},
        {"name": "南北黄灯", "when": [["DB_Traffic.phase", 1]], "timer": "DB_Traffic.T1"},
        {"name": "全红清空", "when": [["DB_Traffic.phase", 2]], "timer": "DB_Traffic.T1"},
        {"name": "东西通行（绿）", "when": [["DB_Traffic.phase", 3]], "timer": "DB_Traffic.T1"},
        {"name": "东西黄灯", "when": [["DB_Traffic.phase", 4]], "timer": "DB_Traffic.T1"},
        {"name": "全红清空", "when": [["DB_Traffic.phase", 5]], "timer": "DB_Traffic.T1"},
    ],
    "faults": [
        {"id": "NS_RED_STUCK", "desc": "南北红灯常亮（灯控回路故障）",
         "kind": "force", "addr": "Q0.0", "value": 1,
         "hints": {
             "method": "现象：南北该绿时红灯仍亮，红黄同亮。",
             "direction": "看 DB_Traffic 的 ns_r 形参是 0 而现场红灯亮——程序之外的问题。",
             "answer": "红灯回路被短接/驱动继电器粘连，Q0.0 输出点被强制导通，需检修线路。"}},
        {"id": "NO_YELLOW", "desc": "程序漏黄灯（绿直接跳红）",
         "kind": "variant", "drop": ["T5.R2.s0", "T5.R5.s0"],
         "hints": {
             "method": "现象：绿灯结束直接变红，没有黄灯过渡。",
             "direction": "看 T5 灯组译码网络：黄灯线圈前面的触点还在吗？",
             "answer": "恢复相位 1/4 到 #ns_y、#ew_y 线圈的译码支路即可。"}},
    ],
    "cards": [
        {"title": "相位循环图", "rows": [
            ["相位0", "南北绿 25s"], ["相位1", "南北黄 3s"], ["相位2", "全红 1s"],
            ["相位3", "东西绿 25s"], ["相位4", "东西黄 3s"], ["相位5", "全红 1s"]],
         "note": "全红 1s 是安全清空时间：放行方向切断后，给路口留出清空余量。",
         "live": {"label": "当前相位 phase", "addr": "DB_Traffic.phase"}},
        {"title": "为什么用 FB", "rows": [
            ["复用", "两个路口就调两次 FB_TrafficLight，各自独立背景数据块"],
            ["跨周期保持", "phase/dur/T1 存在 STAT 与背景 DB 里，断电前一直有效"],
            ["OB1 干净", "OB1 只有一次调用，逻辑全部封装在 FB 内部"]],
         "note": "梯形图视图里点开 DB_Traffic 实例，看 STAT 值随周期变化。"},
    ],
    "scene": {
        "devices": [
            {"type": "traffic", "r": "Q0.0", "y": "Q0.1", "g": "Q0.2", "axis": "ns",
             "label": "南北灯组A", "pos": [1.6, 0, 1.6]},
            {"type": "traffic", "r": "Q0.0", "y": "Q0.1", "g": "Q0.2", "axis": "ns",
             "label": "南北灯组B", "pos": [-1.6, 0, -1.6]},
            {"type": "traffic", "r": "Q0.3", "y": "Q0.4", "g": "Q0.5", "axis": "ew",
             "label": "东西灯组A", "pos": [1.6, 0, -1.6]},
            {"type": "traffic", "r": "Q0.3", "y": "Q0.4", "g": "Q0.5", "axis": "ew",
             "label": "东西灯组B", "pos": [-1.6, 0, 1.6]},
            {"type": "crossroad"},
        ],
    },
}
