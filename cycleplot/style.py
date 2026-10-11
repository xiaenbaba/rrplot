# -*- coding: utf-8 -*-
"""字体、颜色、线宽等全局样式常量。"""
import matplotlib
from matplotlib import font_manager as fm

FONT_CANDIDATES = [
    "Times New Roman", "SimSun", "FangSong", "KaiTi",
    "Songti SC", "Noto Serif CJK SC", "Source Han Serif SC", "STSong",
    "DejaVu Serif",
]

_installed = {f.name for f in fm.fontManager.ttflist}
FONT = next((c for c in FONT_CANDIDATES if c in _installed), "DejaVu Serif")
# 交给 matplotlib 做逐字回退:西文用 Times,汉字回退到宋体
FONT_STACK = [c for c in FONT_CANDIDATES if c in _installed] or [FONT]

matplotlib.rcParams["font.family"] = "serif"
matplotlib.rcParams["font.serif"] = FONT_CANDIDATES
# 数学文本(如 EEV$_1$ 的下标)用 STIX,与 Times 风格一致
matplotlib.rcParams["mathtext.fontset"] = "stix"
matplotlib.rcParams["axes.unicode_minus"] = False

LINE = "#000000"
FILL = "white"       # 部件填充(论文风格:纯白)
COIL = "#333333"     # 部件内盘管/结构线
GRID = "#555555"     # 部件内格栅/细结构线

LW_PIPE = 1.2        # 管路
LW_OUTLINE = 1.2     # 部件外壳/盘管轮廓
LW_PART = 1.0        # 部件内部结构线
LW_STRONG = 1.5      # 强调线(壳体主轮廓、接管短管)
LW_FINE = 0.6        # 内部细节线(格栅、液位)
NUM_SIZE = 24
SENSOR_SIZE = 15


def use_font():
    """打印当前选用的中文字体,便于排查缺字问题。"""
    print("使用字体：", FONT)
    return FONT
