# cycleplot —— 通用制冷循环/HVAC 示意图库

[![CI](https://github.com/xiaenbaba/cycle-plot/actions/workflows/ci.yml/badge.svg)](https://github.com/xiaenbaba/cycle-plot/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

用 Matplotlib 按坐标拼装原理图:放置部件、走线式连管、随线标注状态点与
T/P 传感器圆圈,一键输出 PNG / PDF / SVG。坐标 1:1 对应画布像素(x 向右,
y 向下),所见即所得。

![单级制冷循环](examples/simple_cycle.png)

更多示例见 [`examples/`](#示例)。

## 安装

仅依赖 numpy + matplotlib。克隆仓库后本地安装(推荐,可省去示例脚本里的
`sys.path` 样板):

```powershell
pip install -e .
```

不安装也可用:在仓库根目录下直接 `import cycleplot`。

跑回归测试(32 个用例,CI 覆盖 ubuntu/windows × Python 3.9/3.12):

```powershell
pip install -e ".[test]"
python -m pytest
```

`tests/test_cycleplot.py` 也可以直接 `python tests/test_cycleplot.py` 跑,
不带 pytest 环境也能用。

静态检查(CI 里跑同一条):

```powershell
ruff check cycleplot tests
```

## 快速上手

```python
from cycleplot import Diagram, parts

d = Diagram(width=1491, height=1055)
comp = d.add(parts.compressor, "压缩机", loc=(330, 140))
evap = d.add(parts.evaporator, "蒸发器", loc=(100, 105))

d.pipe(evap["out"], comp["suction"], via=[("e", 200), ("n", 105)],
       states=[("1", 0.5)])
d.save("out.png")     # 也支持 .pdf / .svg 矢量输出
```

完整教程(含部件速查表、标注语法、排错)见 `docs/tutorial.rst`;
坐标系与走线算法的原理见 `docs/design.rst`。

## 核心概念

**Diagram** 是画布。`add(part, label, loc, **style)` 放置部件返回 Node;
`node["端口名"]` 取得带绝对坐标与外法向的端口;`pipe(a, b, via, states,
head_at, color)` 连线。

- 坐标 1 单位 = 1 像素,x 向右、y 向下;`loc` 是部件中心,`save()` 默认裁边,
  需要严格 `width × height` 传 `tight=False`。
- `via` 三种写法混用:`("e", 200)` 走到 x=200;直接给 `(x, y)` 折点;裸
  字符串 `"e"` 走一个默认步长。方向令牌支持 e/w/n/s/right/left/up/down
  与中文名。
- 任意折点自动直角正交化(`_orthogonalize`);端口邻段 ≤10px 的错位视为
  笔误自动吸附,消除接缝碎块(`_fit_end`)。
- `states` 指定随线标注:`("1", 0.5)` 状态点编号;`{"text": "T_1", "at":
  0.3}` 局部处 T/P 传感器(自动识别字母开头文本,画成圆圈);随线箭头由
  `head_at` 控制位置,默认 `(0.55,)`,`head=False` 关闭。
- 两个端口平面不在一个水平/竖直线时,管线默认从端口法向出入。

## 部件库(`cycleplot.parts`)

按名字取直接实例:`compressor`、`evaporator`、`condenser`、`separator`
(气液分离器)、`receiver`(储液器)、`expansion_valve`、`capillary`(毛
细管)、`filter_drier`、`plate_hex`、`economizer`、`subcooler`(过冷器,矩形
+ 中央竖线四口,主路 top/bottom、支路 left/right 逆流错开)、`four_way_valve`、
`four_way_round`(圆体菱形四通阀,端口 exhaust/condenser/evaporator/
suction,自带 D/S/C/E 口别标注)、`vessel`(闪发罐,
胶囊形)、`low_pressure_tank`(低压罐,顶平底圆 + 液位计/视镜,端口
top/bottom/left/right/vapor)、`globe_valve`(截止阀,左右对顶沙漏 + 阀杆
(止于中点) + 手轮横杆,端口 in/out)、`solenoid_valve`(电磁阀,圆体 + 圆内 X +
顶部电磁引线与横杠,端口 in/out)、`expansion_valve_eng`(电子膨胀阀工程
画法,电磁阀体去掉引线与横杠,端口 in/out)、`check_valve`(单向阀,实心
三角指向流通方向 + 尖端挡条,`check_valve_w` 为反向实例,端口 in/out)、
`filter`(过滤器,矩形 + 菱形网格,端口 in/out)等。

尺寸不合适时用工厂生成:

```python
from cycleplot.parts import make_compressor, make_vessel, make_heat_exchanger
from cycleplot.parts import (make_low_pressure_tank, make_globe_valve,
                             make_solenoid_valve)
```

压缩机 `style` 支持 centrifugal/rotor/axial/recip/screw/scroll,换热器
`shape` 支持 circle/rect/rect_diag/rect_zigzag/rect_zigzag7,详见各自
docstring。特殊端口定义可用 `make_partial(part, ports=..., dirs=...)`
从现有部件派生。

## HVAC 符号族(`cycleplot.hvac`)

`references/hvacsvg/symbols` 全部 17 个 SVG 已转成代码图元,与 SVG 原件
逐像素一致:`heat_pump`、`water_pump`、`thermal_tank`、`fan_coil`、
`floor_heating`、`supply_manifold`/`return_manifold`(分水器)、球阀/排
水阀/补水阀/安全阀/自动排气阀/电加热/波纹管等。

工厂参数:`scale` 整体缩放、`moves` 覆盖连接点坐标、`bridge` 在边缘连
接点内侧补引管、`label_dy` 调标签位置。也可用
`cycleplot.svgparts.load_svg_part(path, ...)` 直接加载新 SVG。

<details>
<summary>看图:空气能供暖系统(带水箱)/ 四通阀圆体回路 / SVG 符号直接加载 / 多联机(VRF)</summary>

![空气能供暖系统](examples/hvac_system.png)
![四通阀圆体回路](examples/four_way_round_demo.png)
![SVG 符号直接加载](examples/hvacsvg_demo.png)
![多联机(VRF)系统](examples/vrf_system.png)

</details>

## 示例

`examples/` 各图配套同名 `.py` 与同名 `.png`,可对照学习连管与标注技巧:

| 文件 | 内容 |
| --- | --- |
| simple_cycle.py | 单级压缩基本循环 |
| superheat_cycle.py | 带过热度标注 |
| economizer_cycle.py | 经济器补气 |
| evi_cycle.py | EVI 涡旋压缩热泵(喷气增焓,制热模式) |
| flash_tank_cycle.py | 闪发罐中间补气 |
| split_cycle.py | 涡旋压缩机 + 过冷器 |
| subcooler_cycle.py | 过冷器循环(主路 + 旁通过冷) |
| compressor_symbols.py / heat_exchanger_shapes.py | 符号速观 |
| hvac_system.py / hvac_system_notank.py | 空气能供暖系统(带/无水箱) |
| hvacsvg_demo.py | `load_svg_part` 直接加载 SVG 符号 |
| four_way_round_demo.py | 四通阀圆体回路演示 |
| low_pressure_tank_demo.py | 低压罐图元演示(顶平底圆 + 液位计) |
| globe_valve_demo.py | 截止阀图元演示(左右对顶沙漏 + 手轮) |
| solenoid_valve_demo.py | 电磁阀图元演示(圆体 + 圆内 X + 电磁杠) |
| expansion_valve_eng_demo.py | 电子膨胀阀图元演示(工程画法,无执行机构) |
| check_valve_demo.py | 单向阀图元演示(实心三角,方向可选) |
| filter_demo.py | 过滤器图元演示(矩形 + 菱形网格) |
| vrf_system.py | 多联机(VRF)系统流程(室外机 + 双室内机) |

改完脚本直接重跑即覆盖同名 PNG:

```powershell
python examples/simple_cycle.py
python examples/hvac_system.py
```

## 字体

`cycleplot.style` 依安装列表自动选 Times New Roman + 宋体栈
(`fontfamily` 交给 matplotlib 逐字回退),`use_font()` 打印当前生效字体。

中文渲染成方框时按下面排查:

1. 调用 `use_font()` 看实际生效的字体族,确认栈里没有一个已安装;
2. Windows 装宋体/新宋体,macOS 装 Songti SC,Linux 装
   `fonts-noto-cjk` 或思源宋体,装完重启 Python 进程;
3. 自备字体文件时用 `matplotlib.font_manager.fontManager.addfont()`
   注册,再把族名加进 `cycleplot.style.FONT_CANDIDATES` 头部。

## 目录结构

```
cycleplot/     库本体:core(引擎)/ parts(部件)/ hvac、svgparts(HVAC)/
               style(样式)/ _primitives(底层绘制)
examples/      每张图一个脚本 + 同名 PNG
tests/         pytest 回归测试(端口/走线/错误提示/全件渲染)
references/    早期原型脚本与 SVG 符号源文件
SVG/           export_parts_svg.py 导出的部件单图(可直接进论文/PPT)
docs/          Sphinx 文档:tutorial(上手)/ design(原理)/ api(自动提取)
```

## 文档

| 页面 | 内容 |
| --- | --- |
| `docs/tutorial.rst` | 上手教程:最小例子、via 三种写法、标注语法、部件速查表、排错 |
| `docs/design.rst` | 设计说明:坐标系约定、端口法向规则、走线三阶段算法、扩展部件的三条路 |
| `docs/api.rst` | 全部模块与函数的 API 参考(autodoc 自动提取) |

本地构建(0 警告):

```powershell
pip install sphinx
python -m sphinx -b html docs docs/_build/html
```

生成的 `docs/_build/html/index.html` 即为可浏览的文档站点。

## 贡献

新增部件请在 `cycleplot/parts.py` 里写绘制函数 + 端口表(或用
`make_partial` 派生),并在 `tests/test_cycleplot.py` 补端口断言、
在 `examples/` 加一个演示脚本;提交前跑通 `python -m pytest` 与
`ruff check cycleplot tests`。

## 许可

MIT,见 [LICENSE](LICENSE)。
