# -*- coding: utf-8 -*-
"""示例:双系统制冷循环 + 共用冷却水路 —— 用 rrplot 库组装。

与旧脚本的区别:部件只需声明 loc,管路用「端口 + 走点」描述,
拐角与传感器标注由库自动编译。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rrplot import Diagram, make_partial, parts, use_font

use_font()

# 端口微调:蒸发器进出口都落在下缘
evap_part = make_partial(parts.evaporator,
                         {"in": (-24, 48), "out": (24, 48)})

d = Diagram(width=1491, height=1055)


def build_system(y0):
    evap = d.add(evap_part, "蒸发器", loc=(100, y0))
    comp = d.add(parts.compressor, "压缩机", loc=(330, y0 + 55),
                 label_offset=(0, -95 - 28))
    sep = d.add(parts.separator, "气液分离器", loc=(445, y0 + 140))
    fw = d.add(parts.four_way_valve, "四通阀", loc=(535, y0 - 5))
    cond = d.add(parts.condenser, "冷凝器", loc=(945, y0 + 35))
    recv = d.add(parts.receiver, "储液器", loc=(820, y0 + 190))
    hex_ = d.add(parts.plate_hex, "板式换热器", loc=(560, y0 + 265))
    eev = d.add(parts.expansion_valve, "电子膨胀阀", loc=(700, y0 + 265))
    filt = d.add(parts.filter_drier, "干燥过滤器", loc=(270, y0 + 265))

    # 吸气管:蒸发器 -> 压缩机
    d.pipe(evap["out"], comp["suction"],
           via=[(200, y0 + 48), (200, y0 - 40)], head_at=(0.4,))
    # 压缩机 -> 气液分离器
    d.pipe(comp["discharge"], sep["left"])
    # 分离器 -> 四通阀
    d.pipe(sep["right"], fw["left"], via=[(520, y0 + 140), (520, y0 - 5)])
    # 四通阀 -> 冷凝器
    d.pipe(fw["right"], cond["left"],
           via=[(610, y0 - 5), (610, y0 + 35)])
    # 冷凝器 -> 储液器
    d.pipe(cond["bottom"], recv["right"], via=[(945, y0 + 190)])
    # 储液器 -> 电子膨胀阀
    d.pipe(recv["left"], eev["in"],
           via=[(770, y0 + 190), (770, y0 + 265)])
    # 电子膨胀阀 -> 板式换热器 -> 干燥过滤器
    d.pipe(eev["out"], hex_["in"])
    d.pipe(hex_["out"], filt["in"])
    # 干燥过滤器 -> 蒸发器
    d.pipe(filt["out"], evap["in"], via=[(48, y0 + 265), (48, y0 + 48)])
    # 四通阀旁路:并入吸气管,端点落在吸气口(总线式接法)
    d.pipe(fw["top"], (330, y0 - 40), via=[(535, y0 - 40)], head=False)

    # 温压测点(不落在管线上,直接用绝对坐标)
    for x, y, t in [
        (105, y0 - 65, r"$T_0$"), (170, y0 + 105, r"$T_2$"),
        (170, y0 + 145, r"$T_3$"), (315, y0 - 5, r"$T_1$"),
        (270, y0 + 115, r"$P_2$"), (270, y0 + 155, r"$P_3$"),
        (390, y0 + 95, r"$T_1$"), (430, y0 + 95, r"$P_1$"),
        (415, y0 + 235, r"$T_6$"), (635, y0 + 245, r"$T_8$"),
        (830, y0 + 105, r"$T_5$"), (875, y0 + 105, r"$P_5$"),
    ]:
        d.sensor(x, y, t)
    return cond


cond1 = build_system(105)
cond2 = build_system(585)

# ---------- 右侧共用冷却水路 ----------
d.add(parts.water_tank, loc=(1320, 520))
fm = d.add(parts.flow_meter, loc=(1165, 585))

# 回水:水箱 -> 上系统冷凝器
d.pipe((1230, 455), (945, 140), via=[(1080, 455), (1080, 140)])
# 上系统冷凝器出口 -> 水路汇合
d.pipe((945, 185), fm["left"], via=[(1035, 185), (1035, 585)])
# 下系统冷凝器与水路
d.pipe((945, 665), (1035, 585), via=[(1035, 665)], head_at=(0.8,))
d.pipe((945, 585), (1080, 455), via=[(1080, 585)])
# 水路到水箱
d.pipe(fm["right"], (1230, 585))

d.text(1185, 465, "回水口", ha="right")
d.text(1185, 600, "出水口", ha="right")
d.text(1215, 220, "←", size=42)
d.text(1265, 220, "系统1", size=20, ha="left")
d.text(1215, 735, "←", size=42)
d.text(1265, 735, "系统2", size=20, ha="left")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "split_cycle.png")
d.save(out)
print("已生成:", out)
