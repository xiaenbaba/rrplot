# -*- coding: utf-8 -*-
"""字体、颜色、线宽等全局样式常量。"""
from contextlib import contextmanager

import matplotlib
from matplotlib import font_manager as fm

FONT_CANDIDATES = [
    "Times New Roman", "SimSun", "FangSong", "KaiTi",
    "Songti SC", "Noto Serif CJK SC", "Source Han Serif SC", "STSong",
    "DejaVu Serif",
]

FONT = "DejaVu Serif"
# 交给 matplotlib 做逐字回退:西文用 Times,汉字回退到宋体;原地更新便于跨模块共享
FONT_STACK = [FONT]

STYLE_PARAMS = {
    "font.family": "serif",
    "font.serif": list(FONT_CANDIDATES),
    # 数学文本(如 EEV$_1$ 的下标)用 STIX,与 Times 风格一致
    "mathtext.fontset": "stix",
    "axes.unicode_minus": False,
}


def refresh_fonts():
    """重新扫描 Matplotlib 已安装字体并刷新 FONT / FONT_STACK / 全局配置。

    调用 ``matplotlib.font_manager.fontManager.addfont(...)`` 或调整
    ``FONT_CANDIDATES`` 后调用本函数,即可让后续绘图与 ``use_font()`` 生效。
    """
    global FONT
    installed = {f.name for f in fm.fontManager.ttflist}
    FONT = next((c for c in FONT_CANDIDATES if c in installed), "DejaVu Serif")
    FONT_STACK[:] = [c for c in FONT_CANDIDATES if c in installed] or [FONT]
    STYLE_PARAMS["font.serif"] = list(FONT_CANDIDATES)
    matplotlib.rcParams["font.serif"] = list(FONT_CANDIDATES)
    return FONT


def register_font(path, family=None):
    """注册外部字体文件并设为最高优先级候选字体,返回当前生效字体名。"""
    fm.fontManager.addfont(path)
    if family is None:
        family = fm.FontProperties(fname=path).get_name()
    if family in FONT_CANDIDATES:
        FONT_CANDIDATES.remove(family)
    FONT_CANDIDATES.insert(0, family)
    return refresh_fonts()


def apply_style(**overrides):
    """把 rrplot 样式应用到 Matplotlib 全局配置并返回配置副本。

    该函数保留旧版的全局样式行为;嵌入其他绘图库时优先使用
    :func:`context` 让配置在代码块结束后自动恢复。
    """
    params = dict(STYLE_PARAMS)
    params.update(overrides)
    matplotlib.rcParams.update(params)
    return params


@contextmanager
def context(**overrides):
    """在上下文中临时启用 rrplot 样式,退出后恢复调用方配置。"""
    params = dict(STYLE_PARAMS)
    params.update(overrides)
    with matplotlib.rc_context(params):
        yield


refresh_fonts()
apply_style()

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
SENSOR_R = 18         # 随线 T/P 传感器圆圈半径


def use_font():
    """打印实际生效的字体(逐字回退栈),便于排查中文方框字。"""
    print("使用字体：", FONT)
    if len(FONT_STACK) > 1:
        print("回退栈：", " -> ".join(FONT_STACK))
    else:
        print("警告：仅匹配到", FONT,
              "，未安装中文字体时汉字会渲染成方框")
    return FONT
