# -*- coding: utf-8 -*-
"""示例:电子膨胀阀图元(工程画法) —— 圆体 + 圆内 X,无顶部引线与横杠。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cycleplot import Diagram, parts, use_font

use_font()

d = Diagram(width=640, height=480)
d.add(parts.expansion_valve_eng, "电子膨胀阀", loc=(320, 260))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "expansion_valve_eng_demo.png")
d.save(out)
print("已生成:", out)
