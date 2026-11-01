# -*- coding: utf-8 -*-
"""示例:截止阀图元 —— 左右对顶沙漏 + 阀杆(止于中点) + 手轮横杆。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rrplot import Diagram, parts, use_font

use_font()

d = Diagram(width=640, height=420)
v = d.add(parts.globe_valve, "截止阀", loc=(320, 210))
d.text(*v["in"].point, "in", size=12)
d.text(*v["out"].point, "out", size=12)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "globe_valve_demo.png")
d.save(out)
print("已生成:", out)
