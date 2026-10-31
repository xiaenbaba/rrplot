# -*- coding: utf-8 -*-
"""示例:单向阀图元 —— 实心三角指向流通方向 + 尖端挡条,方向可选。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rrplot import Diagram, parts, use_font

use_font()

d = Diagram(width=720, height=480)
d.add(parts.check_valve, "单向阀(向东)", loc=(220, 260))
d.add(parts.check_valve_w, "单向阀(向西)", loc=(500, 260))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "check_valve_demo.png")
d.save(out)
print("已生成:", out)
