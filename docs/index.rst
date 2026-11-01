rrplot 项目文档
==================

制冷循环 / HVAC 示意图绘制库:坐标式部件拼装 + 走线式连管,
输出 PNG / PDF / SVG。

**版本:** 1.3.0

.. toctree::
   :maxdepth: 2
   :caption: 入门

   tutorial

.. toctree::
   :maxdepth: 2
   :caption: 设计说明

   design

.. toctree::
   :maxdepth: 2
   :caption: API 参考

   api/index

.. toctree::
   :maxdepth: 1
   :caption: 内部模块

   api/internal

快速上手
--------

.. code-block:: python

   from rrplot import Diagram, parts

   d = Diagram(width=760, height=580)
   comp = d.add(parts.compressor, "压缩机", loc=(200, 140))

   d.pipe(comp["top"], ...)      # 走线式连管,详见 tutorial

完整示例见 ``examples/`` 目录(vrf_multisplit / ftvi_cycle / evi_* 等)。

项目结构
--------

::

   rrplot/        — 核心库代码(core 引擎 / part 模型 / parts 部件 /
                     hvac、svgparts(HVAC)/ style(样式)/ _primitives(底层绘制))
   examples/      — 每张图一个脚本 + 同名 PNG
   tests/         — pytest 回归测试
   references/    — 早期原型脚本与 SVG 符号源文件
   SVG/           — export_parts_svg.py 导出的部件单图
   docs/          — Sphinx 文档

索引
----

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
