# -*- coding: utf-8 -*-
"""背景数据块 DB：每个 FB / TON / CTU 实例对应一个 DataBlock。

结构：
    fields —— 接口变量平铺（IN/OUT/STAT 合并在同一命名空间，用 #name 访问）
    subs   —— 嵌套子实例（FB 内部的 TON/CTU/下级 FB），用 #T1.Q 这种路径访问

广播时 snapshot() 生成 {字段: 值, 子实例名: {...}} 的嵌套字典。
"""
from __future__ import annotations


class DataBlock:
    def __init__(self, name: str, interface: dict | None = None) -> None:
        self.name = name
        self.fields: dict[str, object] = {}
        self.subs: dict[str, "DataBlock"] = {}
        # interface 形如 {"IN": {"start": 0}, "OUT": {...}, "STAT": {...}}
        for section in ("IN", "OUT", "STAT"):
            for key, default in (interface or {}).get(section, {}).items():
                self.fields[key] = default

    # ------------------------------------------------------------------ 路径读写
    def _resolve(self, path: str):
        """把 'a' 或 'a.b'（至多两级）解析到 (容器字典, 末级键)。"""
        parts = path.split(".")
        if len(parts) == 1:
            if parts[0] in self.fields:
                return self.fields, parts[0]
            raise KeyError(f"DB {self.name} 中不存在字段 {path!r}")
        if len(parts) == 2:
            sub = self.subs.get(parts[0])
            if sub is None:
                raise KeyError(f"DB {self.name} 中不存在子实例 {parts[0]!r}")
            if parts[1] not in sub.fields:
                raise KeyError(f"DB {self.name}.{parts[0]} 中不存在字段 {parts[1]!r}")
            return sub.fields, parts[1]
        raise KeyError(f"DB 路径最多两级: {path!r}")

    def get(self, path: str):
        container, key = self._resolve(path)
        return container[key]

    def set(self, path: str, value) -> None:
        container, key = self._resolve(path)
        container[key] = value

    def has(self, path: str) -> bool:
        try:
            self._resolve(path)
            return True
        except KeyError:
            return False

    def ensure_sub(self, name: str, interface: dict | None = None) -> "DataBlock":
        """取子实例，不存在则按接口声明自动创建（背景数据块自动生成）。"""
        if name not in self.subs:
            self.subs[name] = DataBlock(f"{self.name}.{name}", interface)
        return self.subs[name]

    # ------------------------------------------------------------------ 快照
    def snapshot(self) -> dict:
        out = dict(self.fields)
        for name, sub in self.subs.items():
            out[name] = sub.snapshot()
        return out
