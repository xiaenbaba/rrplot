core — 走线引擎
===============

:class:`rrplot.core.Diagram` 是画布:``add()`` 放部件、``pipe()`` 连线、
``save()`` 出图;``Node`` / ``Port`` / ``Pipe`` / ``State`` 是其数据模型。
``make_partial`` 语义上属于部件库,在 core 中定义并由 parts 重新导出
(见 parts 一节);顶层入口 ``rrplot.Diagram`` 等亦由 core 导出。

.. automodule:: rrplot.core
   :members:
