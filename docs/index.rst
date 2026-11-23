rrplot 项目文档
==================

制冷循环 / HVAC 示意图绘制库:坐标式部件拼装 + 走线式连管,
输出 PNG / PDF / SVG。

**版本:** |release|

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
                     hvac、svgparts(HVAC)/ registry、scene、scene_renderer(场景)/
                     style(样式)/ _primitives(底层绘制))
   server/        — 本机 Web 服务与启停管理
   web/           — 原生 ES modules SVG 浏览器编辑器
   tools/         — 发布版本校验与基准工具
   examples/      — 每张图一个脚本 + 同名 PNG;scenes/ 存放编辑器 JSON 场景
   tests/         — pytest 回归测试
   references/    — 早期原型脚本与 SVG 符号源文件
   SVG/           — export_parts_svg.py 导出的部件单图
   docs/          — 使用/API 文档与当前架构
   docs/plans/    — 路线图、实施计划与验收记录
   review/        — 历史评审与复审记录

开发与实施文档
--------------

以下 Markdown 文档可在仓库阅读，也可下载原文：

* :download:`文档导航 <README.md>`
* :download:`架构说明 <ARCHITECTURE.md>`
* :download:`计划索引 <plans/README.md>`
* :download:`路线图 <plans/ROADMAP.md>`
* :download:`Web 项目方案与实施计划 <plans/WEB_PROJECT_PLAN.md>`

索引
----

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
