# -*- coding: utf-8 -*-
"""rrplot —— 通用制冷循环示意图库。

用法示例::

    from rrplot import Diagram, parts
    from rrplot.parts import make_heat_exchanger

    d = Diagram(width=1491, height=1055)
    comp = d.add(parts.compressor, "压缩机", loc=(330, 140))
    cond = d.add(make_heat_exchanger(180, 90, shape="rect_zigzag7"),
                 "冷凝器", loc=(945, 140))

    d.pipe(cond["bottom"], comp["suction"], via=[("e", 200), ("n", 105)],
           states=[("1", 0.5)])
    d.save("out.png")     # 也支持 .pdf / .svg 矢量输出
"""
from . import hvac, parts, style
from .core import Diagram, Node, Pipe, Port, State, make_partial, use_font
from .parts import COMPRESSOR_STYLES, HEX_SHAPES
from .style import FONT, FONT_STACK, LINE, apply_style, context
from .svgparts import load_svg_part

__version__ = "1.3.1"

__all__ = ["__version__", "Diagram", "Node", "Pipe", "Port", "State",
           "make_partial", "use_font", "parts", "hvac", "style", "FONT",
           "FONT_STACK", "LINE", "apply_style", "context", "HEX_SHAPES",
           "COMPRESSOR_STYLES", "load_svg_part"]
