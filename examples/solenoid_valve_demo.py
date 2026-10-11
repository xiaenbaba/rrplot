# -*- coding: utf-8 -*-
"""示例:电磁阀图元 —— 圆体 + 圆内 X + 顶部电磁引线与横杠。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cycleplot import Diagram, parts, use_font

use_font()

d = Diagram(width=640, height=480)
d.add(parts.solenoid_valve, "电磁阀", loc=(320, 260))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "solenoid_valve_demo.png")
d.save(out)
print("已生成:", out)
