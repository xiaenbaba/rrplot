# -*- coding: utf-8 -*-
"""GMV 制冷剂系统原理图(入口薄封装)。

真正的绘制逻辑在 references/vrfpart.py 的 ``render_gmv()``(同坐标、同风格),
本文件只保留 ``python references/draw_gmv.py`` 这个入口,避免同一张图两处维护。

产物:references/GMV制冷剂系统原理图.svg
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vrfpart import render_gmv

if __name__ == "__main__":
    render_gmv()
