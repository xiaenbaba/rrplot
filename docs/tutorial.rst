上手教程
========

从零画出一张制冷循环图。读完能覆盖 90% 的日常用法;引擎为什么这么设计
见 :doc:`design`,参数逐项说明见 :doc:`/api/index`。

.. contents:: 本页内容
   :local:
   :depth: 2


1. 安装
----------------------------------------

.. code-block:: powershell

   pip install -e .              # 库本体
   pip install -e ".[test]"      # 连 pytest 一起装
   python -m pytest              # 跑回归测试

只依赖 numpy 与 matplotlib,Python ≥ 3.9。不装包也能在仓库根目录直接
``import rrplot``。

先确认字体(中文渲染成方框时必看):

.. code-block:: powershell

   python -c "from rrplot import use_font; use_font()"

会打印当前生效的字体和回退栈。Windows 装宋体,macOS 装 Songti SC,
Linux 装 ``fonts-noto-cjk``。详见 README 的"字体"一节。


2. 五行画出一条管线
----------------------------------------

整张图是 :class:`rrplot.core.Diagram`。三个动作:``add()`` 放部件、
``pipe()`` 连线、``save()`` 出图。

.. code-block:: python

   from rrplot import Diagram, parts
   from rrplot.parts import make_heat_exchanger

   d = Diagram(width=780, height=500)          # 画布 780×500 像素

   comp = d.add(parts.compressor, "压缩机", loc=(640, 245))
   cond = d.add(make_heat_exchanger(180, 80, shape="rect_zigzag7"),
                "冷凝器", loc=(360, 40))
   cap  = d.add(parts.capillary,   "毛细管", loc=(90, 250))
   evap = d.add(make_heat_exchanger(180, 80, shape="rect_zigzag7"),
                "蒸发器", loc=(360, 425))

   d.pipe(comp["discharge"], cond["right"], via=[(640, 40)], states=[("2", 0.35)])
   d.pipe(cond["left"], cap["in"],            via=[(90, 40)],  states=[("3", 0.3)])
   d.pipe(cap["out"],    evap["left"],        via=[(90, 425)], states=[("4", 0.3)])
   d.pipe(evap["right"], comp["suction"],     via=[(640, 425)], states=[("1", 0.35)])

   d.save("my_cycle.png")                     # 也支持 .pdf / .svg

三个要点:

``loc=(x, y)`` 是部件**中心**在画布上的位置,单位是像素,x 向右、y 向下。
``node["端口名"]`` 取端口,端口名是部件的一部分(见下方速查表)。
``via=[(640, 40)]`` 是显式折点,这里表示"先走到 x=640 y=40 再拐弯"。


3. 摆位:先用眼睛量,再用代码填
----------------------------------------

因为 1 单位 = 1 像素,最舒服的画图方式是:

1. 先 ``d.save("draft.png")`` 出一张草图;
2. 用任意看图/截图工具量出目标位置;
3. 把量到的像素直接抄进 ``loc=``。

想先看部件长什么样、该用哪些端口名,直接跑现成的速观示例:

.. code-block:: powershell

   python examples/compressor_symbols.py      # 7 种压缩机画法
   python examples/heat_exchanger_shapes.py   # 换热器 7 种画法对照

或者看 ``SVG/`` 目录下 37 张导出的部件单图,挑好之后 ``from rrplot.svgparts`` 之外,
用 ``python export_parts_svg.py`` 重新导出。


4. 连线:via 的三种写法
----------------------------------------

``via`` 就是一个"拐弯指令表",三种写法可混用:

.. code-block:: python

   # (a) 方向 + 绝对坐标:沿某轴走到指定值
   d.pipe(a, b, via=[("e", 200), ("n", 105)])   # 先东到 x=200,再北到 y=105

   # (b) 裸字符串:走一个默认步长(Diagram(default_step=100))
   d.pipe(a, b, via=["e", "s"])                 # 先东 100,再南 100

   # (c) 显式坐标折点
   d.pipe(a, b, via=[(120, 300)])

方向令牌:``e/w/n/s``、``right/left/up/down``、``右/左/上/下``。

**不用 ``via`` 也行**:两个端口在同一条水平线或竖直线上时,直连即可,
引擎会自己接:

.. code-block:: python

   d.pipe(host["water_out"], valve["in"])      # hvacsvg_demo.py 里就是这么连的

**管路自动正交化**:折点之间的斜线会被自动补成直角,并且首/末段默认
沿端口法向出入。末端吸附容差 10px,端口旁几像素的错位会自动抹平。


5. 标注:状态点与 T/P 传感器
----------------------------------------

``states`` 里的 ``at`` 是**沿管线弧长的比例**(0~1),不是第几个折点,
所以改了 ``via`` 标注也不会跑位。

.. code-block:: python

   d.pipe(a, b,
          states=[
              ("2", 0.35),                                  # 状态点 2
              {"text": r"$T_1$", "at": 0.3},                 # T 传感器圆圈
              {"text": "$P_2$", "at": "end"},                 # end = 1.0
              {"text": "3", "at": 0.8, "side": 1},            # 画在线的另一侧
          ])

- 首字母是字母 → 画成 T/P 传感器圆圈;是数字 → 画成状态点编号。
- ``side`` = ±1 控制标注在线的哪一侧(默认 ``-1``),手动避让最可靠。
- ``"start"`` / ``"mid"`` / ``"end"`` 等价于 ``0.0`` / ``0.5`` / ``1.0``。

**流向箭头** 默认在每条线 55% 处,可调可关:

.. code-block:: python

   d.pipe(a, b, head_at=(0.6, 0.85))    # 放两个
   d.pipe(a, b, head=False)             # 关闭
   d.pipe(a, b, head_size=16)           # 论文粗箭头

**自由标注** 用 ``d.text(x, y, "回水", ha="left")``;
文字压在管线上时加 ``boxed=True`` 垫一层白底:

.. code-block:: python

   d.text(530, 262, "压缩机", size=20, ha="right", boxed=True)


6. 部件速查
----------------------------------------

按名字直接取实例(``from rrplot import parts``):

.. list-table::
   :header-rows: 1
   :widths: 18 26 56

   * - 实例
     - 端口
     - 说明
   * - ``compressor``(工厂 ``make_compressor``)
     - ``left`` ``right`` ``top`` ``bottom``
     - 两种机身同一套四口: ``圆形`` (圆体双弦)/ ``方形`` (胶囊壳体,
       宽 r、高 2r,与圆形等高)
   * - ``make_heat_exchanger(w, h, shape=...)``
     - ``left`` ``right`` ``top`` ``bottom``
     - 换热器/蒸发器/冷凝器通用:3 种换热面(``HEX_SHAPES``),标签自定
   * - ``capillary``
     - ``in`` ``out``
     - 弹簧形细管,竖放
   * - ``intermediate_hex``
     - ``main_in`` ``main_out`` ``sub_in`` ``sub_out``
     - 中间换热器(过冷器/经济器同体):矩形 + 上下两条通道线,
       默认主路下侧、副路上侧,逆流。工厂传 ``orient="v"`` 可改为
       竖直通道:主路右侧上进下出、副路左侧下进上出; ``w/h`` 始终为外壳宽/高
   * - ``four_way_round``
     - ``exhaust`` ``condenser`` ``evaporator`` ``suction``
     - 圆体 + 内菱形,自带 D/S/C/E 口别标注
   * - ``globe_valve``
     - ``in`` ``out``
     - 截止阀:沙漏 + 阀杆(止于中点) + 手轮
   * - ``solenoid_valve``
     - ``in`` ``out``
     - 电磁阀:圆体 + 圆内 X + 电磁横杠
   * - ``expansion_valve_eng``
     - ``in`` ``out``
     - 电子膨胀阀工程画法:圆体 + 圆内 X(无执行机构)
   * - ``expansion_valve_x``
     - ``in`` ``out``
     - 膨胀阀圆 + 内接 X,端口在圆周,``orient="h"/"v"`` 水平/竖直通用
   * - ``bowtie_valve`` 系
     - ``in`` ``out``
     - 对顶三角阀;``bowtie_valve_dome`` 穹顶 / ``bowtie_valve_solenoid``
       电磁 / ``tee`` T 形截止阀
   * - ``check_valve`` / ``check_valve_w``
     - ``in`` ``out``
     - 单向阀:实心三角 + 尖端挡条,``_w`` 为反向实例
   * - ``filter``
     - ``in`` ``out``
     - 过滤器:矩形 + 菱形网格
   * - ``vessel``
     - ``top`` ``bottom`` ``left`` ``right`` ``vapor``
     - 闪发罐:胶囊形上下封头 + 液位线

**尺寸不合适就用工厂生成** (端口偏移会跟着尺寸走):

.. code-block:: python

   from rrplot.parts import (make_compressor, make_heat_exchanger,
                                make_vessel,
                                make_globe_valve, make_solenoid_valve,
                                make_expansion_valve_eng,
                                make_expansion_valve_x, make_check_valve,
                                make_filter)

   comp = make_compressor(r=80, style="圆形")               # 半径 80
   cond = make_heat_exchanger(240, 62, shape="rect_zigzag7")  # 宽 240 高 62
   tank = make_vessel(w=66, h=150, liquid=0.42)

``make_compressor`` 的 ``style``: ``圆形`` (圆体双弦)/
``方形`` (胶囊壳体);
``make_heat_exchanger`` 的 ``shape``:``rect_diag`` / ``rect_x`` /
``rect_zigzag7``。

**只想改端口、不想重画图形**,用 ``make_partial``:

.. code-block:: python

   from rrplot import make_partial, parts

   comp_part = make_partial(parts.make_compressor(80, style="圆形"),
                            {"discharge": (0, -80), "suction": (0, 80)})

``examples/vrf_multisplit.py`` 里多处用 ``make_partial`` 派生端口(如
四通阀换向、电子膨胀阀流向东→西的 in/out 对调)。

**只想改画法、不想改端口**,在 ``add()`` 的 ``**style`` 里按绘制函数的
参数名传:

.. code-block:: python

   d.add(parts.four_way_round, "四通阀", loc=(60, 70), mark=False)


7. HVAC 符号族
----------------------------------------

:mod:`rrplot.hvac` 里是 17 个暖通符号,工厂参数与 SVG 加载器一致:

.. code-block:: python

   from rrplot import hvac

   tank = hvac.thermal_tank(scale=1.5, bridge=44,
                           moves={"right": (160, 72)}, label_dy=-97)
   node = d.add(tank, "蓄热水箱", loc=(770, 375))

.. list-table::
   :header-rows: 1
   :widths: 24 76

   * - 参数
     - 含义
   * - ``scale``
     - 整体缩放(端口偏移、线宽、标签位置一并缩放)
   * - ``moves``
     - ``{连接点名: (x, y)}`` 覆盖连接点在 viewBox 里的坐标(改接管位置)
   * - ``bridge``
     - 从每个连接点沿边缘法向朝内补一段引管(符号单位),补上图形没画到的边
   * - ``label_dy``
     - 标签相对锚点的竖直偏移;``None`` 画在符号下方,``0`` 压在符号中心

符号清单:``heat_pump`` ``water_pump`` ``anti_freeze_valve``
``thermal_tank`` ``electric_heater`` ``safety_valve`` ``drain_valve``
``makeup_valve`` ``auto_vent`` ``fan_coil`` ``corrugated_pipe``
``floor_heating`` ``supply_manifold`` ``return_manifold`` ``supply_pipe``
``return_pipe`` ``ball_valve``。

整张空气能供暖系统的画法见 ``examples/hvac_system.py`` (带水箱)和
``examples/hvac_system_notank.py`` (无水箱)。

**有自己的 SVG?** 用 ``load_svg_part`` 直接加载:

.. code-block:: python

   from rrplot import load_svg_part

   host = d.add(load_svg_part("symbols/01_空气能主机.svg", bridge=24),
                "空气能主机", loc=(130, 180))

支持 hvacsvg 风格的 SVG 子集:``path`` 的 M/m/L/l/H/h/V/v/C/c/Z/z,以及
``circle`` / ``ellipse`` / ``rect`` / ``g``;连接点读根属性
``data-connection-points``。完整例子见 ``examples/hvacsvg_demo.py``。


8. 出图:论文 / PPT 尺寸
----------------------------------------

.. code-block:: python

   d.save("fig.pdf")                       # 矢量,论文首选
   d.save("fig.svg")                       # 矢量,可再编辑
   d.save("fig.png", dpi=300)              # 位图,300 dpi 够印刷
   d.save("fig.png", tight=False)          # 不裁边,严格 width×height

字号全部是绝对值(状态点 24、标签 17~18),与画布尺寸无关。想让整张图
在论文里占同样宽度,按比例放大 ``Diagram(width, height)`` 和各部件的
尺寸参数即可,不用改字号。

``save`` 默认 ``tight=True`` 会裁掉四周空白,**输出尺寸略小于**
``Diagram`` 声明的尺寸;需要严格 1:1 时传 ``tight=False``。一次想出
多种格式,把多个路径一起传进来::

   d.save("out.png", "out.svg", "out.pdf")

在 Jupyter 里,把 ``Diagram`` 实例放在单元格最后一行即内嵌显示(SVG
矢量,可无限放大)。


9. 排错
----------------------------------------

**中文显示成方框**
   跑 ``use_font()``。只匹配到 DejaVu Serif 说明系统没装中文字体,
   按 README"字体"一节装宋体 / Songti SC / Noto CJK,或用
   ``matplotlib.font_manager.fontManager.addfont()`` 注册自备字体,
   再把族名加进 ``rrplot.style.FONT_CANDIDATES`` 头部。

**端口名报错**
   错误信息会列出全部可用端口,照抄即可。

**管线有奇怪的短碎块 / 接缝**
   端口旁 10px 内的错位会自动吸附。若仍有碎块,通常是 ``via`` 里给了
   一个和端口几乎重合的折点 —— 删掉它,让管线直连。

**斜线没被正交化**
   正交化会把任意折点补成直角,但**只在方向突变处**补。若你给的是
   一条只有两点的斜线(端口 A 直接连到坐标折点),它会按进入段方向补
   一个拐点;想让整条线沿某方向先走,在端口旁加一个 ``("e", 200)``
   这样的方向令牌。

**文字被管线压住看不清**
   ``d.text(..., boxed=True)`` 垫白底,或把标注的 ``side`` 翻到另一侧。

**画布太小 / 内容被裁**
   放大 ``Diagram(width, height)``;``aspect="equal"`` 不会自动扩展。

**管线出入方向不对 / 想看端口在哪**
   在 ``save()`` 之前调一次 :meth:`~rrplot.core.Diagram.debug`,叠加层
   会画出每个端口的红点、沿外法向的红色短箭头和每根管线的蓝色拐点
   方块,端口在哪、管线怎么拐一目了然:

   .. code-block:: python

      d.pipe(evap["out"], comp["suction"], via=[("e", 200)])
      d.debug(names=True)      # names=True 连端口名一起标
      d.save("out.png")        # 调试层会随图输出,正式出图前删掉这行

如果在出图后修改了节点位置或样式,先清空旧图层再重新绘制::

   node.loc = (420, 180)
   d.clear_render().render()

``clear_render()`` 会保留节点和管线定义,同时清除之前的 Matplotlib 图元;
通过 ``sensor()``、``text()`` 和 ``debug()`` 添加的临时图层也会随之清除。


10. 现成示例
----------------------------------------

``examples/`` 下 13 个脚本,每个都配一张同名 PNG,建议对照着改:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - 脚本
     - 内容
   * - ``vrf_multisplit.py``
     - 多联机(VRF)系统图(室外机 + 室内机 1…n,综合布线范例,建议从这个开始读)
   * - ``ftvi_cycle.py``
     - FTVI 闪发罐喷气增焓系统图(电子膨胀阀节流)
   * - ``evi_ftvi_layout.py``
     - 按 FTVI 版式重排的 EVI 过冷器喷气增焓(过冷器替代闪蒸罐)
   * - ``evi_cycle.py``
     - 多联机 / VRF 常见的 EVI 经济器喷气增焓(主路双级节流)
   * - ``evi_subcooler_cycle.py``
     - 普通热泵常见的 EVI 过冷器式喷气增焓(带电磁阀)
   * - ``evi_economizer_cycle.py``
     - 普通热泵 EVI 经济器竖直排布(主路上下贯通,喷气支路左右贯通)
   * - ``compressor_symbols.py``
     - 7 种压缩机画法速观
   * - ``heat_exchanger_shapes.py``
     - 7 种换热器画法速观
   * - ``hvac_system.py`` / ``hvac_system_notank.py``
     - 空气能供暖系统(带 / 无水箱)
   * - ``hvacsvg_demo.py``
     - ``load_svg_part`` 直接加载 SVG 符号
   * - ``four_way_round_demo.py``
     - 四通阀圆体回路
   * - ``globe_valve_demo.py``
     - 截止阀图元(沙漏 + 手轮)
   * - ``solenoid_valve_demo.py``
     - 电磁阀图元(圆体 + 圆内 X)
   * - ``expansion_valve_eng_demo.py``
     - 电子膨胀阀图元(工程画法)
   * - ``check_valve_demo.py``
     - 单向阀图元(实心三角,方向可选)
   * - ``filter_demo.py``
     - 过滤器图元(矩形 + 菱形网格)


下一步
----------------------------------------

- 想加新部件:见 :doc:`design` 的"扩展:三条路"
- 想知道 ``via`` / ``states`` / ``bridge`` 的完整参数:见 :doc:`/api/index`
- 想加测试:``tests/test_rrplot.py`` 里有端口定义、走线算法、
  错误提示、全件渲染四类现成范式,照着写即可
- 改了代码先跑 ``python -m pytest`` 和 ``ruff check rrplot tests``
