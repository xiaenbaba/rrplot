import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, FancyBboxPatch, Polygon, Ellipse
import numpy as np
import os

# =========================
# 基本参数
# =========================
W, H = 1491, 1055
fig, ax = plt.subplots(figsize=(W/100, H/100), dpi=100)
ax.set_xlim(0, W)
ax.set_ylim(H, 0)
ax.axis("off")
fig.patch.set_facecolor("white")
ax.set_facecolor("white")

# 自动寻找常见中文字体（Windows 字体优先）
import matplotlib
from matplotlib import font_manager as fm

font_candidates = [
    "Microsoft YaHei", "SimHei", "DengXian", "SimSun",
    "Microsoft JhengHei", "Noto Sans CJK SC",
    "Source Han Sans SC", "WenQuanYi Zen Hei", "Arial Unicode MS",
]
installed = {f.name for f in fm.fontManager.ttflist}
FONT = next((f for f in font_candidates if f in installed), "DejaVu Sans")
matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["font.sans-serif"] = [FONT, "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False
print("使用字体：", FONT)

LINE = "#111111"
BLUE = "#8ecae6"
LIGHT_BLUE = "#eaf7ff"

def txt(x, y, s, size=18, ha="center", va="center", weight="normal"):
    ax.text(x, y, s, fontsize=size, fontfamily=FONT,
            ha=ha, va=va, color=LINE, fontweight=weight)

def pipe(points, lw=3):
    xs, ys = zip(*points)
    ax.plot(xs, ys, color=LINE, lw=lw, solid_capstyle="round",
            solid_joinstyle="round")

def arrow(x1, y1, x2, y2, size=12, lw=2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", lw=lw, color=LINE,
                                mutation_scale=size))

def sensor(x, y, label, r=18):
    ax.add_patch(Circle((x, y), r, facecolor="white", edgecolor=LINE, lw=2))
    txt(x, y, label, size=15)

def evaporator(x, y):
    # x,y 为中心
    ax.add_patch(Rectangle((x-24, y-48), 48, 96,
                           facecolor=BLUE, edgecolor=LINE, lw=2))
    for yy in np.linspace(y-38, y+38, 5):
        ax.plot([x-20, x+20], [yy, yy], color=LINE, lw=1.5)
    for xx in [-12, 0, 12]:
        ax.plot([x+xx, x+xx], [y-46, y+46], color=LINE, lw=1)
    # 简化风机
    ax.plot([x-62, x-38], [y, y], color=LINE, lw=3)
    ax.add_patch(Ellipse((x-70, y), 11, 44, angle=20,
                         facecolor=LIGHT_BLUE, edgecolor=LINE, lw=1.5))
    ax.add_patch(Ellipse((x-70, y), 11, 44, angle=-20,
                         facecolor=LIGHT_BLUE, edgecolor=LINE, lw=1.5))
    txt(x, y+72, "蒸发器", size=18)

def compressor(x, y):
    ax.add_patch(Ellipse((x, y), 70, 92, facecolor="white", edgecolor=LINE, lw=2))
    # 顶部/底部管口
    pipe([(x, y-46), (x, y-72)], lw=3)
    pipe([(x, y+46), (x, y+72)], lw=3)
    txt(x+62, y, "压缩机", size=18, ha="left")

def separator(x, y):
    ax.add_patch(FancyBboxPatch((x-17, y-32), 34, 64,
                                boxstyle="round,pad=0.02,rounding_size=8",
                                facecolor=LIGHT_BLUE, edgecolor=LINE, lw=2))
    for yy in np.linspace(y-24, y+24, 4):
        ax.plot([x-13, x+13], [yy, yy], color=LINE, lw=1)
    txt(x-30, y+62, "气液分离器", size=17, ha="right")

def receiver(x, y):
    ax.add_patch(FancyBboxPatch((x-17, y-35), 34, 70,
                                boxstyle="round,pad=0.02,rounding_size=8",
                                facecolor=LIGHT_BLUE, edgecolor=LINE, lw=2))
    for yy in np.linspace(y-25, y+25, 5):
        ax.plot([x-13, x+13], [yy, yy], color=LINE, lw=1)
    txt(x, y-54, "储液器", size=17)

def condenser(x, y):
    ax.add_patch(Rectangle((x-32, y-80), 64, 160,
                           facecolor=LIGHT_BLUE, edgecolor=LINE, lw=2))
    for xx in [-20, -7, 7, 20]:
        ax.plot([x+xx, x+xx], [y-67, y+67], color="#3f7ea0", lw=3)
    ax.plot([x-32, x+32], [y-80, y-80], color=LINE, lw=3)
    ax.plot([x-32, x+32], [y+80, y+80], color=LINE, lw=3)
    txt(x, y+105, "冷凝器", size=18)

def four_way_valve(x, y):
    # 四通阀简化符号
    ax.add_patch(Rectangle((x-20, y-14), 40, 28,
                           facecolor=LIGHT_BLUE, edgecolor=LINE, lw=2))
    for xx in [x-12, x, x+12]:
        ax.plot([xx, xx], [y-14, y-25], color=LINE, lw=2)
    txt(x+36, y-2, "四通阀", size=17, ha="left")

def expansion_valve(x, y):
    # 电子膨胀阀
    ax.add_patch(Polygon([[x-16,y-10],[x,y+10],[x+16,y-10]],
                         closed=True, facecolor="white", edgecolor=LINE, lw=2))
    ax.add_patch(Rectangle((x-7, y-25), 14, 15,
                           facecolor=LIGHT_BLUE, edgecolor=LINE, lw=2))
    txt(x, y+38, "电子膨胀阀", size=17)

def filter_drier(x, y):
    ax.add_patch(Rectangle((x-35, y-18), 70, 36,
                           facecolor=LIGHT_BLUE, edgecolor=LINE, lw=2))
    ax.add_patch(Circle((x, y), 17, facecolor=BLUE, edgecolor=LINE, lw=2))
    txt(x, y+48, "干燥过滤器", size=17)

def plate_hex(x, y):
    ax.add_patch(Rectangle((x-55, y-28), 110, 56,
                           facecolor=LIGHT_BLUE, edgecolor=LINE, lw=2))
    for xx in np.linspace(x-45, x+45, 9):
        ax.plot([xx, xx], [y-25, y+25], color="#4c89aa", lw=2)
    txt(x, y+58, "板式换热器", size=17)

def water_tank(x, y):
    ax.add_patch(Rectangle((x-90, y-125), 180, 250,
                           facecolor=LIGHT_BLUE, edgecolor=LINE, lw=3))
    # 水位线
    for yy in [y-40, y-20, y, y+20, y+40, y+60]:
        ax.plot([x-87, x+87], [yy, yy], color="#70a9c5", lw=1)
    txt(x, y-155, "水箱", size=18)

def flow_meter(x, y):
    ax.add_patch(Rectangle((x-28, y-18), 56, 36,
                           facecolor=LIGHT_BLUE, edgecolor=LINE, lw=2))
    ax.add_patch(Circle((x-10, y), 8, facecolor="white", edgecolor=LINE, lw=1.5))
    ax.add_patch(Circle((x+10, y), 8, facecolor="white", edgecolor=LINE, lw=1.5))
    txt(x, y+48, "流量计", size=17)

# =========================
# 系统布局
# =========================
def draw_refrigeration_system(y0, label_offset=0):
    # 主要坐标
    evap = (100, y0)
    comp = (330, y0+55)
    sep = (445, y0+140)
    cond = (945, y0+35)
    recv = (820, y0+190)
    hex_ = (560, y0+265)
    eev = (700, y0+265)
    filt = (270, y0+265)

    evaporator(*evap)
    compressor(*comp)
    separator(*sep)
    condenser(*cond)
    receiver(*recv)
    plate_hex(*hex_)
    expansion_valve(*eev)
    filter_drier(*filt)
    four_way_valve(535, y0-5)

    # 吸气管：蒸发器 -> 压缩机
    pipe([(124,y0+48),(200,y0+48),(200,y0-35),(330,y0-35)])
    # 压缩机 -> 分离器
    pipe([(330,y0+101),(330,y0+128),(445,y0+128)])
    # 分离器 -> 四通阀
    pipe([(462,y0+140),(520,y0+140),(520,y0-5),(535,y0-5)])
    # 四通阀 -> 冷凝器
    pipe([(555,y0-5),(610,y0-5),(610,y0+35),(913,y0+35)])
    # 冷凝器 -> 储液器
    pipe([(945,y0+115),(945,y0+190),(837,y0+190)])
    # 储液器 -> EEV
    pipe([(803,y0+190),(770,y0+190),(770,y0+265),(716,y0+265)])
    # EEV -> 板换
    pipe([(684,y0+265),(615,y0+265)])
    # 板换 -> 过滤器
    pipe([(505,y0+265),(305,y0+265)])
    # 过滤器 -> 蒸发器
    pipe([(235,y0+265),(48,y0+265),(48,y0+48),(76,y0+48)])
    # 四通阀旁路
    pipe([(535,y0-19),(535,y0-45),(455,y0-45),(455,y0-5),(330,y0-5)])

    # 传感器
    sensor(105, y0-65, r"$T_0$")
    sensor(170, y0+105, r"$T_2$")
    sensor(170, y0+145, r"$T_3$")
    sensor(315, y0-5, r"$T_1$")
    sensor(270, y0+115, r"$P_2$")
    sensor(270, y0+155, r"$P_3$")
    sensor(390, y0+95, r"$T_1$")
    sensor(430, y0+95, r"$P_1$")
    sensor(415, y0+235, r"$T_6$")
    sensor(635, y0+245, r"$T_8$")
    sensor(830, y0+105, r"$T_5$")
    sensor(875, y0+105, r"$P_5$")

# 两套系统
draw_refrigeration_system(105)
draw_refrigeration_system(585)

# =========================
# 右侧水路
# =========================
water_tank(1320, 520)
flow_meter(1165, 585)

# 回水：水箱 -> 上系统冷凝器入口
pipe([(1230, 455),(1080,455),(1080,140),(945,140)], lw=3)
# 上系统冷凝器出口 -> 水路汇合
pipe([(945,185),(1035,185),(1035,585),(1137,585)], lw=3)

# 下系统冷凝器与水路
pipe([(945,665),(1035,665),(1035,585)], lw=3)
pipe([(945,585),(1080,585),(1080,455)], lw=3)

# 水路到水箱
pipe([(1193,585),(1230,585)], lw=3)

# 水口文字
txt(1185, 465, "回水口", size=18, ha="right")
txt(1185, 600, "出水口", size=18, ha="right")

# 系统标签
txt(1215, 220, "←", size=42, ha="center")
txt(1265, 220, "系统1", size=20, ha="left")
txt(1215, 735, "←", size=42, ha="center")
txt(1265, 735, "系统2", size=20, ha="left")

# =========================
# 流向箭头（简化）
# =========================
for (x1,y1,x2,y2) in [
    (215,70,245,70),(365,160,410,160),(600,100,650,100),
    (950,220,950,255),(770,370,735,370),(620,370,590,370),
    (250,370,210,370),
    (215,550,245,550),(365,640,410,640),(600,580,650,580),
    (950,700,950,735),(770,850,735,850),(620,850,590,850),
    (250,850,210,850)
]:
    arrow(x1,y1,x2,y2, size=12, lw=2)

# 标题（如不需要可删除）
# txt(W/2, 25, "双系统制冷循环与冷却水路示意图", size=22, weight="bold")

plt.tight_layout(pad=0)
_basedir = os.path.dirname(os.path.abspath(__file__))
PNG = os.path.join(_basedir, "制冷循环示意图.png")
plt.savefig(PNG, dpi=100, bbox_inches="tight", pad_inches=0.05)
plt.show()
