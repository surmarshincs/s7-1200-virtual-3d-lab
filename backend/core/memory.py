# -*- coding: utf-8 -*-
"""存储区：I（输入映像 IB0-IB3）、Q（输出映像 QB0-QB1）、M（标志位 MB0-MB15）。

寻址规则（S7 习惯）：
    位：  I0.0 / Q1.7 / M15.7      —— 区域字母 + 字节号 + "." + 位号(0-7)
    字节：IB0 / QB1 / MB10
    字：  IW0 / QW0 / MW14         —— 按大端（高字节在前）
非法地址一律抛 KeyError，便于教学调试时立刻暴露写错地址的问题。
"""
from __future__ import annotations

import re

AREA_SIZES = {"I": 4, "Q": 2, "M": 16}  # 各区域字节数

_ADDR_RE = re.compile(r"^([IQM])(B|W)?(\d+)(?:\.([0-7]))?$")


class Memory:
    """I/Q/M 三个存储区，底层各为一个 bytearray。"""

    def __init__(self) -> None:
        self._data = {area: bytearray(size) for area, size in AREA_SIZES.items()}

    def reset(self) -> None:
        for buf in self._data.values():
            buf[:] = b"\x00" * len(buf)

    # ------------------------------------------------------------------ 寻址
    def _parse(self, addr: str):
        """把 'I0.0' / 'MB10' / 'QW0' 解析成 (区域, 类型, 字节号, 位号)。"""
        m = _ADDR_RE.match(addr.strip())
        if not m:
            raise KeyError(f"非法地址: {addr!r}")
        area, bw, num_s, bit_s = m.groups()
        byte = int(num_s)
        if byte >= len(self._data[area]):
            raise KeyError(f"地址越界: {addr!r}")
        if bw is None:
            if bit_s is None:
                raise KeyError(f"位地址缺少位号: {addr!r}")
            return area, "bit", byte, int(bit_s)
        if bit_s is not None:
            raise KeyError(f"字节/字地址不应带位号: {addr!r}")
        if bw == "B":
            return area, "byte", byte, None
        # 字：需要两个字节
        if byte + 1 >= len(self._data[area]):
            raise KeyError(f"字地址越界: {addr!r}")
        return area, "word", byte, None

    # ------------------------------------------------------------------ 读写
    def get_bit(self, addr: str) -> int:
        area, kind, byte, bit = self._parse(addr)
        assert kind == "bit"
        return (self._data[area][byte] >> bit) & 1

    def set_bit(self, addr: str, value: int) -> None:
        area, kind, byte, bit = self._parse(addr)
        assert kind == "bit"
        if value:
            self._data[area][byte] |= 1 << bit
        else:
            self._data[area][byte] &= ~(1 << bit)

    def get_byte(self, addr: str) -> int:
        area, kind, byte, _ = self._parse(addr)
        assert kind == "byte"
        return self._data[area][byte]

    def set_byte(self, addr: str, value: int) -> None:
        area, kind, byte, _ = self._parse(addr)
        assert kind == "byte"
        self._data[area][byte] = int(value) & 0xFF

    def get_word(self, addr: str) -> int:
        area, kind, byte, _ = self._parse(addr)
        assert kind == "word"
        return (self._data[area][byte] << 8) | self._data[area][byte + 1]

    def set_word(self, addr: str, value: int) -> None:
        area, kind, byte, _ = self._parse(addr)
        assert kind == "word"
        v = int(value) & 0xFFFF
        self._data[area][byte] = (v >> 8) & 0xFF
        self._data[area][byte + 1] = v & 0xFF

    def read(self, addr: str) -> int:
        """按地址形式自动选择位/字节/字读取。"""
        _, kind, _, _ = self._parse(addr)
        if kind == "bit":
            return self.get_bit(addr)
        if kind == "byte":
            return self.get_byte(addr)
        return self.get_word(addr)

    def write(self, addr: str, value: int) -> None:
        """按地址形式自动选择位/字节/字写入。"""
        _, kind, _, _ = self._parse(addr)
        if kind == "bit":
            self.set_bit(addr, 1 if value else 0)
        elif kind == "byte":
            self.set_byte(addr, value)
        else:
            self.set_word(addr, value)

    # ------------------------------------------------------------------ 快照
    def snapshot(self, m_watch: set[str] | None = None) -> dict[str, int]:
        """生成广播用快照。

        I/Q 区位数少（32+16），全量给出；M 区 128 位只给出"项目引用过或当前为 1"
        的位（m_watch 为项目加载时收集的引用集合），兼顾教学可见性与消息体积。
        """
        out: dict[str, int] = {}
        for area in ("I", "Q"):
            buf = self._data[area]
            for byte in range(len(buf)):
                for bit in range(8):
                    out[f"{area}{byte}.{bit}"] = (buf[byte] >> bit) & 1
        watch = m_watch or set()
        buf = self._data["M"]
        for byte in range(len(buf)):
            for bit in range(8):
                addr = f"M{byte}.{bit}"
                if addr in watch or (buf[byte] >> bit) & 1:
                    out[addr] = (buf[byte] >> bit) & 1
        return out

    def split_snapshot(self, snap: dict[str, int]) -> tuple[dict, dict, dict]:
        """把扁平快照拆成 I/Q/M 三个字典（组 scan 消息用）。"""
        i = {k: v for k, v in snap.items() if k.startswith("I")}
        q = {k: v for k, v in snap.items() if k.startswith("Q")}
        m = {k: v for k, v in snap.items() if k.startswith("M")}
        return i, q, m
