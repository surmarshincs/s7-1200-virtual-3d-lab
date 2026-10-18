# -*- coding: utf-8 -*-
"""指令原语：TON / CTU 系统功能块的状态更新，SEG 七段译码表。

位逻辑类原语（常开/常闭/线圈/置位/复位/SR/上升沿/CMP/MOVE）在 networks.py
的梯形图求值器中实现——它们是"能流"概念，必须依附网络求值；这里的三个是
带内部状态、跨周期保持的功能块/译码表，因此单独成模块。

TON / CTU 的状态字典就是各自背景数据块的 fields（IN/PT/Q/ET、CU/R/PV/CV/Q），
直接就地读写，保证 DB 快照里能看到实时值。
"""
from __future__ import annotations

# 共阴七段数码管译码表：位0-6 = a-g，位7 = 小数点dp（本译码器不点亮dp）
SEG_TABLE = {
    0: 0x3F, 1: 0x06, 2: 0x5B, 3: 0x4F, 4: 0x66,
    5: 0x6D, 6: 0x7D, 7: 0x07, 8: 0x7F, 9: 0x6F,
}
SEG_BLANK = 0x00  # 输入超出 0-9 时熄灭（用于复位后清屏）


def seg_decode(value: int) -> int:
    """SEG 指令：输入 0-9 输出七段码，其余输入输出灭灯码。"""
    return SEG_TABLE.get(int(value), SEG_BLANK)


# TON 背景数据块的默认字段（IEC：IN 输入、PT 预设、Q 输出、ET 当前值）
TON_INTERFACE = {"IN": {"IN": 0, "PT": 1000}, "OUT": {"Q": 0, "ET": 0}, "STAT": {}}
# CTU 加计数器：CU 计数输入（上升沿）、R 复位、PV 预设、CV 当前值、Q 到达输出
CTU_INTERFACE = {"IN": {"CU": 0, "R": 0, "PV": 10}, "OUT": {"CV": 0, "Q": 0},
                 "STAT": {"_last_cu": 0}}


def ton_update(fields: dict, dt_ms: int) -> None:
    """TON 通电延时：IN=1 时 ET 累计，ET>=PT 后 Q=1；IN=0 时 ET 清零、Q=0。

    dt_ms 用虚拟时钟步长（慢速模式下为周期×0.1），保证慢放时定时同步拉伸。
    """
    if fields["IN"]:
        fields["ET"] = min(int(fields["ET"]) + int(dt_ms), int(fields["PT"]))
        fields["Q"] = 1 if fields["ET"] >= int(fields["PT"]) else 0
    else:
        fields["ET"] = 0
        fields["Q"] = 0


def ctu_update(fields: dict) -> None:
    """CTU 加计数：CU 上升沿 CV+1；CV>=PV 时 Q=1；R=1 时 CV 清零、Q=0。"""
    cu = 1 if fields["CU"] else 0
    if fields["R"]:
        fields["CV"] = 0
        fields["Q"] = 0
    elif cu and not fields["_last_cu"]:
        fields["CV"] = int(fields["CV"]) + 1
        if fields["CV"] >= int(fields["PV"]):
            fields["Q"] = 1
    fields["_last_cu"] = cu
