# -*- coding: utf-8 -*-
"""部件数据模型与端口方向基础设施。"""
from dataclasses import dataclass, field

_PORT_DIR = {"n": (0, -1), "s": (0, 1), "e": (1, 0), "w": (-1, 0)}


@dataclass
class Part:
    """一个以中心为锚点的可绘制部件。"""

    name: str
    draw: object
    ports: dict = field(default_factory=dict)
    _dirs: dict = field(default_factory=dict)

    def port(self, key):
        try:
            return self.ports[key]
        except KeyError:
            raise KeyError(
                f"部件 {self.name!r} 没有端口 {key!r},"
                f"可用端口:{', '.join(sorted(self.ports)) or '(无)'}"
            ) from None

    def direction(self, key):
        """端口外法向单位向量,优先取显式声明。"""
        if key in self._dirs:
            return _PORT_DIR[self._dirs[key]]
        dx, dy = self.port(key)
        if dx == 0 and dy == 0:
            return (0, 0)
        if abs(dx) >= abs(dy):
            return (1 if dx > 0 else -1, 0)
        return (0, 1 if dy > 0 else -1)


def make_part(name, ports, draw, dirs=None):
    """创建部件实例,供部件定义模块使用。"""
    return Part(name, draw, ports, dirs or {})
