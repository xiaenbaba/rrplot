设计说明
========

这一页解释 rrplot **为什么这样设计**。读完你应该能回答三个问题:
坐标系是怎么定的、端口方向从哪来、管线为什么总是直角且贴着端口出入。

API 逐项说明见 :doc:`api`,动手画图见 :doc:`tutorial`。

.. contents:: 本页内容
   :local:
   :depth: 2


1. 坐标系:1 单位 = 1 像素,y 向下
----------------------------------------

整张图只有一个坐标系,定义在 :class:`rrplot.core.Diagram.__init__`:

.. code-block:: python

   self.fig, self.ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
   self.fig.subplots_adjust(0, 0, 1, 1)   # 画布 1 像素 = 1 画图单位
   self.ax.set_xlim(0, width)
   self.ax.set_ylim(height, 0)           # 注意:y 上限在前,轴被翻转
   self.ax.set_aspect("equal")
   self.ax.axis("off")

由此得到三条贯穿全库的约定:

**x 向右,y 向下。** 和 SVG、图像处理、PFD 图纸一致,和数学课本相反。
好处是画图时"往下挪一点"就是 ``y += 50``,不用在脑子里做一次翻转;
部件内部画对称图形时镜像也只需要改一个符号。

**1 画图单位 = 1 输出像素。** ``figsize = width/100`` 英寸配 ``dpi=100``,
再把子图边距压成 0,于是 ``Diagram(width=1491, height=1055)`` 出的 PNG
就是 1491×1055。写脚本时可以直接拿截图工具的像素坐标往里填,
所见即所得,不需要"图上量一下再换算"。

**等比纵横比。** ``set_aspect("equal")`` 保证圆是圆、方是方。
代价是画布上放不下内容时不会自动扩展,需要自己放大 ``width``/``height``。

.. note::

   ``Diagram`` 允许 ``width=0``/``height=0`` 这种退化输入(此时 matplotlib
   会发一条 ``xlim`` 警告),主要用于测试;画图请给正常尺寸。


2. 端口:相对偏移 + 外法向
----------------------------------------

每个部件是一个 :class:`rrplot.part.Part` 数据类,只有四个字段:

.. code-block:: python

   @dataclass
   class Part:
       name: str                 # 中文名,同时是默认标签
       draw: object              # f(ax, x, y, label=None, **kw) 绘制函数
       ports: dict               # {端口名: (dx, dy)} 相对锚点偏移
       _dirs: dict               # {端口名: "n"/"s"/"e"/"w"} 显式法向(可选)

``ports`` 用**相对锚点的偏移**而不是绝对坐标,是为了让同一个部件实例
能被放到画布任意位置。:meth:`Part.port` 返回偏移,:meth:`Part.direction`
返回单位外法向,两者组合成 :class:`rrplot.core.Port`:

.. code-block:: python

   node = d.add(parts.compressor, "压缩机", loc=(330, 140))
   node["suction"].point   # (330, 140) + (0, -95) = (330, 45)
   node["suction"].dir     # (0, -1) 朝上

### 法向怎么定

:meth:`Part.direction` 的判定顺序:

1. 端口名在 ``_dirs`` 里 → 直接用显式声明;
2. 否则按偏移推断 —— ``|dx| >= |dy|`` 取 x 轴符号,否则取 y 轴符号;
3. ``dx == dy == 0`` → 返回 ``(0, 0)``,表示"自由端",走线不做法向约束。

显式声明存在的唯一原因是**对角端口**。例如
``compressor`` 的补气口 ``vapor_inj = (95, 0)`` 按偏移推断是 ``(1, 0)``,
没问题;但若某个口开在右上角 ``(40, -40)``,按偏移推断会得到东向,
而画线上真正需要的是先向北离开壳体。这种情况显式写 ``dirs={"x": "n"}``。

.. important::

   覆盖某个端口的**位置**时,它在 ``_dirs`` 里的**旧方向声明会一并作废**,
   回落到按偏移推断;:func:`rrplot.core.make_partial` 实现了这个规则
   (见 ``new_dirs.pop(k, None)``)。需要固定方向就在 ``dirs=`` 里显式补回来。

### 命名约定

库内两类端口命名,不要混:

- **贯通式两口元件** (阀、过滤器、毛细管)用 ``in`` / ``out``,
  惯例是 **in 在东、out 在西**,即图内主流向自东向西;
- **多口/换热类部件** (蒸发器、冷凝器、容器)用
  ``left`` / ``right`` / ``top`` / ``bottom`` 表示边中点;
- **有专门热力学含义的** 用领域名:``suction`` / ``discharge`` / ``inj`` /
  ``vapor`` / ``exhaust``,读者不看文档也知道接的是什么。

端口名拼错时错误信息会列出全部可用端口:

.. code-block:: text

   KeyError: 部件 '蒸发器' 没有端口 'outt',可用端口:in, out


3. 走线:三个阶段
----------------------------------------

:func:`rrplot.core.Pipe.points` 是纯几何的,分三步,结果缓存在
``_pts`` 里(同一条管线重复 ``render()`` 不会重算):

.. code-block:: text

   端口 A ──▶ 展开 via ──▶ 端口 B  →  _fit_end(两端)  →  _orthogonalize(全部)

### 3.1 展开 via

``via`` 是一个序列,元素支持三种写法,可在同一条管线里混用:

.. list-table::
   :header-rows: 1
   :widths: 22 34 44

   * - 写法
     - 含义
     - 例子
   * - ``("e", 200)``
     - 沿某方向走到该轴的绝对坐标(东走到 x=200)
     - ``("n", 105)`` 一路向北到 y=105
   * - 裸字符串 ``"e"``
     - 同方向走一个 ``Diagram.default_step`` (默认 100)的步长
     - ``via=["e", "s"]`` = 先东后南
   * - 坐标 ``(x, y)``
     - 显式折点
     - ``[(120, 300)]`` 折向指定点

方向令牌:``e/w/n/s``、``right/left/up/down``、``右/左/上/下``。

非法令牌会指出具体是第几个 ``via`` 和哪个字符:

.. code-block:: text

   ValueError: via[0] 方向令牌 'q' 无效,可用:down,e,left,n,right,s,up,w,左,上,右,下

### 3.2 端口吸附(_fit_end)

部件是按坐标摆的,端口旁的第一段很容易和端口差几像素,画出来就是一根
**接缝碎块**。:func:`rrplot.core._fit_end` 处理两种情况:

**斜接**(邻段与端口既不同轴也不同轴)。错位在 ``SNAP_TOL = 10`` 以内 →
优先吸附**切向**坐标,让管线沿法向笔直切入;其次吸附法向坐标。错位
超过容差但来点在**法向正确一侧** → 不动坐标,返回一个走线提示
(``"h"`` 或 ``"v"``)交给下一步。

**切向已对齐**。若邻段从端口法向的**背面**接入且距离在容差内,把整段
(或终点侧连同 feeder 竖段一起)吸附到端口平面。

10px 这个容差是权衡出来的:小于它大概率是笔误,大于它就是用户真的想
画一条偏离的引管,不该被改写。

### 3.3 正交化(_orthogonalize)

展开后的折点里可能有斜线段,直接画出来是斜的示意图,不好看也不符合
PFD 惯例。:func:`rrplot.core._orthogonalize` 遍历相邻点,发现方向
突变就插入一个拐点,并用两条规则决定拐点位置:

- 进入段水平 → 先横后竖,拐点在 ``(cur.x, prev.y)``;
- 进入段竖直 → 先竖后横,拐点在 ``(prev.x, cur.y)``。

首/末段若带 ``first_along`` / ``last_along`` 提示,则无视上述规则,
强制先/后走提示的方向 —— 这正是"管线沿端口法向出入"的实现方式。
提示由 ``_fit_end`` 产出。

.. code-block:: python

   >>> from rrplot.core import _orthogonalize
   >>> _orthogonalize([(0, 0), (108, 30)])
   [(0.0, 0.0), (0.0, 30.0), (108.0, 30.0)]          # 进入段竖直 → 先竖后横
   >>> _orthogonalize([(0, 0), (108, 30)], "h")
   [(0.0, 0.0), (108.0, 0.0), (108.0, 30.0)]          # 起点东向端口 → 先东后北


4. 标注:按弧长定位,不是按折点序号
----------------------------------------

``states`` 里的 ``at`` 是**折线总弧长的比例**(0~1),不是"第几个折点"。
按弧长定位的好处是:改了 ``via``,标注仍然贴在管线的中点/末端,不会跑位。

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - 写法
     - 含义
   * - ``("1", 0.5)``
     - 状态点"1"贴在管线 50% 处
   * - ``{"text": "$T_1$", "at": 0.3}``
     - T 传感器圆圈,贴在 30% 处
   * - ``{"text": "2", "at": "end"}``
     - ``start`` / ``mid`` / ``end`` 等价于 0.0 / 0.5 / 1.0(大小写不敏感)
   * - ``{"text": "3", "at": 0.8, "side": 1}``
     - ``side`` = ±1,标注画在线的哪一侧(默认 -1)

**状态点 vs 传感器** 由文本自动判定:首字母是字母就画成 T/P 传感器圆圈
(:func:`rrplot.core._is_sensor` 会剥掉 ``$`` 再判断,所以
``r"$T_0$"`` 也认)。圆圈半径 ``SENSOR_R``、内文 ``SENSOR_SIZE`` 都在
:mod:`rrplot.style` 里,改一处即可全局调大调小。

**随线箭头** 由 ``head_at`` 控制,默认 ``(0.55,)``,即每条线在 55% 处放
一个流向箭头;:func:`rrplot.core._draw_head` 会把箭头整体夹在所在段内
(``ARROW_HALF`` 半长),段太短就自动缩短,不会骑到拐角上。``head=False``
关闭,``head_size`` 控制大小(论文粗箭头可用 16~20)。

**标注避让** 靠 ``side`` 参数手动指定。库不做自动避让 —— 自动布局在这个
"坐标即一切"的模型里反而不可预测,手动一个符号更可控。


5. 渲染与出图
----------------------------------------

:meth:`rrplot.core.Diagram.render` 先画所有部件、再画所有管线,返回
``fig``。部件的 ``**style`` 参数透传给绘制函数,所以
``d.add(parts.compressor, "压缩机", loc=..., style="scroll")`` 里
``style`` 是绘制函数的参数名,不是 :class:`rrplot.core.Pipe` 的线型。

:meth:`rrplot.core.Diagram.save` 默认 ``tight=True``,会用
``bbox_inches="tight"`` 裁掉四周空白 —— 也就是**输出尺寸会略小于**
``Diagram(width, height)``。需要严格尺寸时传 ``tight=False``。

``label`` 传 ``None`` 或 ``""`` 一律不画标签,且**不会**回落到部件绘制
函数的默认中文名(见 ``Diagram.render`` 的注释)。想画默认名就传
部件的 ``name``。


6. 扩展:三条路
----------------------------------------

**路线一:改端口不动图形。** :func:`rrplot.core.make_partial` 从现有
部件派生,只覆盖端口表(复用同一个 ``draw`` 函数):

.. code-block:: python

   from rrplot import make_partial, parts

   rect = parts.make_rect(260, 110)
   evap2 = make_partial(rect, {"vapor_out": (-65, -55)}, dirs={"vapor_out": "n"})

**路线二:新写一个绘制函数 + 端口表。** 在 :mod:`rrplot.parts` 里加
``def _xxx(ax, x, y, label="新部件", **kw): ...``,再 ``xxx = _part("新部件",
{"in": (-40, 0), "out": (40, 0)}, _xxx)``。尺寸要可调就写成工厂函数
``make_xxx(w=..., h=...)``,返回一个闭包包住尺寸的 ``Part``。

**路线三:直接加载 SVG。** :func:`rrplot.svgparts.load_svg_part` 解析
hvacsvg 风格的 SVG 子集(``path`` 的 M/m/L/l/H/h/V/v/C/c/Z/z,以及
circle / ellipse / rect / g),连接点读根属性 ``data-connection-points``,
锚点取 viewBox 中心。

``bridge`` 参数专门解决"连接点在 viewBox 边缘、但符号图形没画到边"的
情况:给一个正数,就从每个连接点沿边缘法向朝内补一段引管,让管路接得上。

.. note::

   :mod:`rrplot.hvac` 里的 17 个符号是 ``load_svg_part`` 的**代码版**,
   形状与 SVG 原件逐像素一致,但不依赖文件存在、可直接改参数。两条路线
   互为验证:``tests/test_rrplot.py`` 里的
   ``test_hvac_factory_ports_match_svg_part`` 会比对两者端口定义是否一致。
