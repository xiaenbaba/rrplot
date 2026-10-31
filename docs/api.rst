API 参考
========

按名字取实例的部件、HVAC 符号与参数取值,见 :doc:`tutorial` 的速查表;
坐标系、端口方向规则与走线算法的原理,见 :doc:`design`。

顶层入口
--------

.. automodule:: rrplot
   :members:
   :imported-members:

引擎(core)
----------

.. automodule:: rrplot.core
   :members:

部件库(parts)
-------------

``make_partial`` 语义上属于部件库,在 core 中定义并由 parts 重新导出
(见下方 core 一节)。

.. automodule:: rrplot.parts
   :members:

部件模型(part)
--------------

.. automodule:: rrplot.part
   :members:

HVAC 符号(hvac)
----------------

.. automodule:: rrplot.hvac
   :members:

SVG 加载(svgparts)
-------------------

.. automodule:: rrplot.svgparts
   :members:

样式(style)
-----------

.. automodule:: rrplot.style
   :members:

样式隔离可使用 ``rrplot.context()``;需要恢复旧版全局行为时调用
``rrplot.apply_style()``。

底层原语(_primitives)
----------------------

.. automodule:: rrplot._primitives
   :members:
