# -*- coding: utf-8 -*-
"""示例:气液分离器(U 形管)图元 —— 端口接法与镜像。

三个端口:
  in    进气(壳顶短管,气液混合物进入,管口悬于壳内上部)
  out   出气(U 形管腿,穿壳顶引出,接压缩机吸气)
  drain 放油/排液(U 形弯底,向南引出)
U 形管兼作液封:液体积于弯底排走,气体绕行上行,不会随吸气带液。
左为默认件(进气短管在西、出气为 U 形管右腿);右为
``make_separator_utube(flip=True)`` 镜像件(进口在右、出口在左)。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cycleplot import Diagram, use_font
from cycleplot.parts import make_separator_utube, separator_utube

use_font()

d = Diagram(width=800, height=400)
sep = d.add(separator_utube, "气液分离器", loc=(230, 185))
sep_f = d.add(make_separator_utube(flip=True), "镜像", loc=(580, 185))

# 三口接管示意:箭头方向即流向
d.pipe((186, 70), sep["in"], head_at=(0.6,))
d.pipe(sep["out"], (282, 70), head_at=(0.6,))
d.pipe(sep["drain"], (230, 330), head_at=(0.6,))
d.pipe((624, 70), sep_f["in"], head_at=(0.6,))    # 镜像:in 在东侧
d.pipe(sep_f["out"], (528, 70), head_at=(0.6,))   # 镜像:out 在西侧
d.pipe(sep_f["drain"], (580, 330), head_at=(0.6,))

d.text(186, 52, "进气", size=17)
d.text(282, 52, "出气", size=17)
d.text(258, 312, "放油", ha="left", size=17)
d.text(624, 52, "进气", size=17)
d.text(528, 52, "出气", size=17)
d.text(608, 312, "放油", ha="left", size=17)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "separator_utube_demo.png")
d.save(out)
print("已生成:", out)
