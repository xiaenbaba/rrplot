API 参考
========

按名字取实例的部件、HVAC 符号与参数取值,见 :doc:`tutorial` 的速查表;
坐标系、端口方向规则与走线算法的原理,见 :doc:`design`。

顶层入口
--------

.. automodule:: cycleplot
   :members:
   :imported-members:

引擎(core)
----------

.. automodule:: cycleplot.core
   :members:

部件库(parts)
-------------

``make_partial`` 语义上属于部件库,在 core 中定义并由 parts 重新导出
(见下方 core 一节)。

.. automodule:: cycleplot.parts
   :members:

HVAC 符号(hvac)
----------------

.. automodule:: cycleplot.hvac
   :members:

SVG 加载(svgparts)
-------------------

.. automodule:: cycleplot.svgparts
   :members:

样式(style)
-----------

.. automodule:: cycleplot.style
   :members:

底层原语(_primitives)
----------------------

.. automodule:: cycleplot._primitives
   :members:
