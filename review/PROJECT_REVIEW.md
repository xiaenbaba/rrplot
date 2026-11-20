# rrplot 项目审查报告

> 本文保留历史审查结论。2026-11-19 起的现行架构见 [架构说明](../docs/ARCHITECTURE.md)，
> 优化状态见 [路线图](../docs/plans/ROADMAP.md)，行为变化见 [CHANGELOG.md](../CHANGELOG.md)；下述规模及测试数字不是当前基线。

> **2026-10-24 复审补充**:当前状态以本节为准;下方 2026-10-16 与 2026-10-12
> 两节中的规模数字(53 例 / 96~97% / 16~22 示例 / 旧行数)已过时,仅作历史记录。

## 2026-10-24 复审

**审查基线**:`29f4516` + 工作区未提交改动(vrf 阀件缩小一号、
`make_four_way_round` 工厂)。

**现状**:64 例测试全绿、**0 代码警告**;`ruff check rrplot tests examples`
全绿;22 个 `examples/*.py` 逐个跑通;包内覆盖率 **97%**
(`core 98 / parts 98 / hvac 94 / svgparts 93 / style 96 / _primitives 100 /
__init__ 100`);Sphinx 构建 0 警告;版本 1.3.0 单一来源(`pyproject` dynamic +
`conf.py release = __version__`)。2026-10-16 轮的整改项(CI 三 job、覆盖率
门槛 90%、ruff 钉版、hvac 工厂自动发现、依赖统一)全部落地且有效;
tutorial 速查表与最新部件(胶囊压缩机、rect_x/rect_shell、chord、新阀件)
同步到位。

**本轮发现并已就地修复**:

1. **P1 回归(未提交改动引入)**:`make_four_way_round` 工厂的 draw 吞掉
   `**kw`,`examples/heat_pump_cycle.py:31` 依赖的 add() 时
   `mark=False` 静默失效,重跑示例后四通阀出现双份 D/S/C/E 字母
   (内置 + 手标)。已修复:draw 以 `**{"r": r, "mark": mark, **kw}`
   透传(与旧实例语义一致,add() 时同名词可覆盖);新增
   `test_four_way_round_add_time_mark_override` 锁行为;重跑后
   `heat_pump_cycle.png` 与入库版逐字节一致。
2. **P2 既有缺陷(同类根因)**:`make_bowtie_valve` 的 docstring 与
   `test_bowtie_valve_actuator_override_render` 都声称 add() 时
   actuator/stem 可覆盖,实际 draw 一直吞掉 kwargs,契约从未生效
   (测试只烟雾渲染、无断言,故从未红过)。已修复:同样透传;测试补
   真断言(裸阀 0 条线,`actuator="dome"` 覆盖后 2 条线)。
3. `examples/vrf_system.py` docstring 超长行(E501,上轮提交遗留;
   CI lint 只查 `rrplot tests` 故未暴露)。

**新发现(复审提出后,已按优先级全部整改)**:

1. ✅ **P2 测试卫生**:`pytest` 原有 1 条 `RuntimeWarning: More than 20
   figures have been opened`(`core.py` 的 `plt.subplots` 从不关闭)。
   整改:`Diagram` 加 `close()`(内部 `plt.close`)与上下文管理器协议,
   `test_diagram_close_and_context_manager` 锁行为;测试侧加 autouse
   fixture 每例 `plt.close("all")`(try/except 守卫,`python
   tests/test_rrplot.py` 直跑不受影响)。pytest 输出现为 56 例 0 警告。
2. ✅ **P3 README 滞后 4 处**:① 用例数 32 → 56;② 压缩机 style 清单补
   `chord`;③ 换热器 shape 清单补 `rect_x` / `rect_shell`;④ 示例表补
   `heat_pump_cycle.py` 与 `separator_utube_demo.py` 两行。顺带:部件
   段落补 `capsule_compressor` / `separator_utube` / `oil_separator`,
   工厂代码块补 `make_four_way_round`。
3. ✅ **P3 examples 6 处 ruff 违规**:5 处 `--fix`(4 个文件导入排序 +
   1 处文件尾换行)、`hvac_system_notank.py` 超长行注释上提手修;
   CI lint job 扩为 `ruff check rrplot tests examples`,
   README / CONTRIBUTING 的检查命令同步。
4. ✅ **P4 注释滞后**:`export_parts_svg.py` docstring "5 种换热面变体"
   改为 7 种。

**遗留项状态(对照 2026-10-16 轮)**:`Diagram` 资源管理已在本轮完成
(见上 ✅);其余维持:`parts.py` 拆包(现 1083 行,仍在增长,建议提上
日程)、`.pre-commit-config.yaml`、`CHANGELOG.md`、CI 矩阵补
Python 3.13、`svgparts` 的 defusedxml 可选防护,按需。

**结论**:结构性与正确性风险仅一处,即未提交改动引入的工厂覆盖回归,
已修复并有测试锁定;其余发现(文档滞后、测试卫生、lint 盲区)已随本轮
按优先级全部整改完毕,工作区相对 `29f4516` 的全部改动已验证
(56 例 0 警告、22 示例跑通、`heat_pump_cycle.png` 重跑逐字节复原)。

---

## 2026-10-16 复审补充

**现状**:53 例测试全绿;`ruff check rrplot tests` 全绿;22 个 `examples/*.py`
逐个跑通。包内覆盖率 **97%**(`core 98 / parts 98 / hvac 94 / svgparts 93 /
style 96 / _primitives 100 / __init__ 100`)。

**本轮整改(按优先级落地)**:

1. CI 加固(`.github/workflows/ci.yml`):`pytest` 加 `--cov-fail-under=90`;
   新增 `examples` 烟雾 job(逐个执行示例);新增 `docs` job(`sphinx-build`);
   ruff 固定 `ruff==0.15.13`(原先装最新版,规则升级会突然弄红构建)。
2. 测试去硬编码:`test_render_every_part_and_hvac_symbol` 的 17 个 hvac 工厂名
   改为按 `__module__` 自动发现 + 数量下限,新增符号不再需要手工登记。
3. 消除重复实现:原 `rrplot/vrfpart.py` 是脱离库约定的第三套 SVG 引擎,
   已**降级为 `references/vrfpart.py` 原型**(不进包、不进覆盖率、不进 API 文档);
   根目录 `draw_gmv.py` 改为调用 `render_gmv()` 的薄封装,同图不再两处维护。
4. 仓库整理:早期原型 `制冷循环示意图.*`、`涡旋压缩机循环示意图.*` 移入
   `references/`;根目录只留元文件。生成物(`*.svg`/`*.png` 于 `references/`、
   `examples/*.svg`)加入 `.gitignore`,不再入库。
5. 依赖来源统一:`requirements.txt` 与 `pyproject.toml` 重复,已删除前者,以
   `pyproject` 为唯一来源;新增 `docs` extra。
6. 文档与协作:新增 `CONTRIBUTING.md`、`references/README.md`、`.readthedocs.yaml`;
   修正 `docs/conf.py` 里 `sys.path` 用 cwd 推断仓库根的问题(改为按 `__file__`)。

**遗留(未处理,按需)**:

- `parts.py`(1014 行)拆成 `parts/` 包。
- `Diagram` 资源管理(加 `close()` / 上下文管理器);`style.py` import 时改全局
  `rcParams` 的副作用写进文档。
- `svgparts.load_svg_part` 加载不受信任 SVG 时的实体展开防护(`defusedxml` 可选)。
- `.pre-commit-config.yaml`、`CHANGELOG.md`、CI 矩阵补 Python 3.13。

---

**审查日期**: 2026-10-12
**项目类型**: 制冷循环与 HVAC 示意图绘制库
**技术栈**: Python 3.9+, Matplotlib 3.7+, NumPy 1.23+
**审查基线**: `e1bde30`(工作区干净)

> 本次为**复审**。2026-10-11 的初版报告中列出的工程化缺口(LICENSE、
> pyproject 打包、GitHub Actions、Sphinx 文档、测试补充、代码风格整改)
> 已在其后 6 个 commit 中全部处理完毕,本报告不再重复,只记录**当前真实状态**
> 与**仍待处理的问题**。

### 本轮修复(复审后立即处理)

复审报告列出的 17 条问题中,已就地修掉 8 条(下方各条已标注):

- **P1.1 版本号单一来源**:`__init__.py` 加 `__version__ = "0.1.0"`,
  `docs/conf.py` 改为 `from rrplot import __version__`,
  `pyproject.toml` 用 `dynamic = ["version"]` + `[tool.setuptools.dynamic]`。
- **P1.2 打包清单**:`packages = ["rrplot"]` 换成
  `[tool.setuptools.packages.find] include = ["rrplot*"]`,将来拆包不会漏装。
- **P1.3 零尺寸画布**:`Diagram(width=0, height=0)` 跳过 `set_xlim`/`set_ylim`,
  不再触发 matplotlib 的 identical-limits 警告,测试输出干净。
- **P2.4/5/6/7 测试盲区**:新增 7 个用例(压缩机 7 style、换热器 5 shape、
  经济器 2 style、label 有/无全件渲染、svgparts 的 `bridge`+`label_dy`、
  `Diagram.sensor`/`text`/`render`、State 全参数、`use_font`)。用例 32→43,
  覆盖率 85%→96%,`parts.py` 77%→98%。
- **P3.15 ruff 配置**:`pyproject.toml` 加 `[tool.ruff]`(line-length 88,
  select `E/F/W/I`),`parts.py` 末尾的 `make_partial` 循环导入上提(已验证不成环),
  并按 isort 重排了 `core`/`hvac`/`parts`/`tests` 的导入块。

`examples/simple_cycle.py` 与 `examples/economizer_cycle.py` 里的
`d.text(..., bg=True)` 在 `684d303`(bg 改名 boxed)之后没有跟着改,两个脚本
直接 `TypeError: txt() got an unexpected keyword argument 'bg'`。已改为
`boxed=True` 并跑通全部 16 个示例。教训:纯文档型 commit(改 docstring、
改参数名)没有配套的示例烟雾测试,CI 里也只跑 `pytest`,不跑 `examples/`。

---

## 一、项目概况

`rrplot` 用坐标式部件拼装 + 走线式连管生成制冷循环 / HVAC 原理图,
输出 PNG / PDF / SVG。核心约定是 **1 画图单位 = 1 画布像素,x 向右、y 向下**,
因此在画图脚本里可以"所见即所得"地摆位。

### 规模

| 指标 | 数值 |
| --- | --- |
| 源码 | 1773 行 / 7 个模块(不含示例与测试) |
| 测试 | 43 个用例,全部通过 |
| 语句覆盖率 | 96% |
| 示例脚本 | 16 个(配套 16 张 PNG) |
| 部件图元 | 44 个可直接渲染的 `Part` 实例 |
| HVAC 符号 | 17 个(hvac 代码图元 + SVG 源双轨) |
| 导出单图 | `SVG/` 37 个(供论文/PPT 直接引用) |

模块与行数:

| 文件 | 行数 | 职责 |
| --- | ---: | --- |
| `rrplot/parts.py` | 1083 | 部件库:绘制函数 + 端口表 + 尺寸工厂 |
| `rrplot/core.py` | 477 | 引擎:`Diagram` / `Pipe` / `Port` / 走线算法 |
| `rrplot/hvac.py` | 305 | 17 个 HVAC 符号(160×100 viewBox 坐标图元) |
| `rrplot/svgparts.py` | 213 | SVG 子集解析器,直接加载外部符号 |
| `rrplot/style.py` | 46 | 字体栈、颜色、线宽、字号常量 |
| `rrplot/_primitives.py` | 25 | 底层原语:`txt` / `line` / `arrow` |
| `rrplot/__init__.py` | 28 | 顶层导出 + `__version__` |

### 覆盖率分布(实测)

```
Name                       Stmts   Miss  Cover
rrplot\__init__.py          7      0   100%
rrplot\_primitives.py      11      0   100%
rrplot\core.py            264      5    98%
rrplot\hvac.py            162     10    94%
rrplot\parts.py           378      8    98%
rrplot\style.py            28      1    96%
rrplot\svgparts.py        149     11    93%
TOTAL                        999     35    96%
```

未覆盖的 35 行集中在:压缩机 `centrifugal`/`axial`/`recip`/`screw`/`scroll`
五个 style 的部分绘制分支、`svgparts` 的 bridge 内部几行、以及
`hvac._hvac` 的 bridge 分支 —— 都是已被"全 style/全 shape 渲染"用例
间接触达的纯几何代码。

---

## 二、优点

### 1. 架构分层干净,扩展点清晰

`core`(引擎) / `parts`(部件) / `hvac`(符号) / `svgparts`(加载器) /
`style`(常量) / `_primitives`(原语)各司其职,依赖方向单一:
`parts → _primitives → style`,`core → parts`,无环。
`svgparts` 与 `hvac` 是同一套形状的**两条并行实现**(解析 SVG / 硬编码图元),
靠测试 `test_hvac_factory_ports_match_svg_part` 锁住端口定义一致性,
让"改造符号"不会两边跑偏——这是个值得推广的做法。

### 2. 端口系统是这个库真正的设计资产

`Part.ports`(相对锚点偏移)+ `Part._dirs`(显式法向)+ `Part.direction()`
三者配合,让"部件怎么画"和"管子从哪进出"彻底解耦。`make_partial()` 可以
只改端口不动图形,派生出一个新部件复用同一绘制函数。

走线算法 `_fit_end` + `_orthogonalize` 解决了示意图最烦人的两类问题:
端口错位吸附(10px 容差)与任意折点的自动直角化,并用 `first_along` /
`last_along` 提示强制管线沿端口法向出入。三者都有精确的单元测试。

### 3. 错误信息是"写给使用者"的

端口名拼错会列出全部可用端口(`parts.py:35`),`via` 令牌非法会指出是
`via[0]` 还是哪个字符(`core.py:231`),`at="middle"` 会提示只能用
`start/mid/end` 或 0~1 数值(`core.py:131`)。这类细节对库的可维护性
影响远大于它的代码行数。

### 4. 测试策略务实

`test_render_every_part_and_hvac_symbol` / `test_render_every_svg_symbol`
做全量上屏烟雾测试,并在 docstring 里**写明了为什么不做像素级回归**
(中文字体跨平台差异会让参考图比对脆到不可用)。这是经过权衡的取舍,
不是遗漏。保存结果还会读回 PNG 校验签名、尺寸与非白像素。

### 5. 工程化基线齐了

- `pyproject.toml`(setuptools,版本区间约束,`[test]` extra)
- `LICENSE`(MIT)
- `.github/workflows/ci.yml`:ubuntu/windows × Python 3.9/3.12 四象限,
  跑 `pytest --cov` + `ruff check`
- `docs/` Sphinx 配置(alabaster,`zh_CN`,autodoc + napoleon + viewcode),
  上一版构建 0 警告
- `.gitignore` 覆盖缓存/打包/文档产物

---

## 三、问题与改进建议

按优先级排列,每条都给出可落地的动作。

### P1 —— 影响正确性或可复现性

#### 1. ✅ 版本号三处硬编码,库内无 `__version__`(已修复)

`pyproject.toml` 的 `version = "0.1.0"`、`docs/conf.py` 的 `release = "0.1.0"`
各自独立,`rrplot/__init__.py` 也没有暴露 `__version__`。升级时容易漏改,
下游也无法 `rrplot.__version__` 做能力判断。

**建议**:在 `__init__.py` 加 `__version__ = "0.1.0"`,`docs/conf.py` 改为
`release = rrplot.__version__`(conf.py 已经把仓库根加进 `sys.path`),
`pyproject.toml` 用 `dynamic = ["version"]` + `[tool.setuptools.dynamic]`
从 `__init__.py` 读取。

#### 2. ✅ `Diagram(width=0, height=0)` 会打出 matplotlib UserWarning(已修复)

`core.py:294-295` 的 `set_xlim(0, 0)` / `set_ylim(0, 0)` 触发
"Attempting to set identical low and high xlims" 警告,`test_degenerate_diagram_and_pipe`
跑测试时能看到两条。库把零尺寸当合法输入(测试断言"允许构造不出错"),
就不该向上抛警告。

**建议**:零尺寸时直接 `return` 跳过 `set_xlim`/`set_ylim`,
或钳到 `max(width, 1)`;同时给该测试加 `filterwarnings` 断言锁住行为。

#### 3. ✅ `pyproject.toml` 的 `packages = ["rrplot"]` 是硬编码清单(已修复)

一旦按建议把 `parts.py` 拆成 `parts/` 包,或新增子模块,这行会**静默漏装**——
`pip install` 成功但 `import` 失败,只在用户环境里暴露。

**建议**:改用 `[tool.setuptools.packages.find] include = ["rrplot*"]`。

### P2 —— 测试覆盖盲区

#### 4. ✅ `parts.py` 77%,是最低的一块(已修复,现 98%)

未覆盖的 88 行原本集中在**变体分支**:

- `_compressor` 的 `axial` / `recip` / `screw` / `scroll` / `centrifugal`
  五种 style 的绘制体(`parts.py:308-348`)
- `make_heat_exchanger` 整个工厂(`parts.py:514-561`),五种 `shape` 一个没测
- 几乎所有部件的 `if label:` 分支(各绘制函数的最后一行)

这些是纯几何代码,改错了不会抛异常、只会画错——恰恰是最需要烟雾测试的地方。

**已修复**:新增 `test_render_all_compressor_styles` /
`test_render_all_heat_exchanger_shapes` / `test_render_all_economizer_styles` /
`test_render_all_labels_on_and_off`(label 有/无各渲染一次全件)四个用例。
`parts.py` 覆盖率 77% → 98%。

#### 5. ✅ `svgparts.py` 87%,`bridge` 分支完全没测(已修复,现 93%)

`svgparts.py:197-208`(bridge 引管)和 `211`(标签)未被任何测试触达,
而 `examples/hvacsvg_demo.py` 正是这两个参数的主要使用者。

**已修复**:新增 `test_svg_part_bridge_and_label_dy`,用 `bridge=20,
label_dy=0` 加载 + 渲染,并断言 bridge 不改变端口偏移。

#### 6. ✅ `core.py` 未覆盖的辅助 API(已修复,现 98%)

`sensor()` / `text()` / `show()` / `Diagram.render()` 返回值
(`core.py:331-334, 337, 359-360`)没测;`State` 走 dict 分支的
`side` / `kind` / `size` 覆盖参数也没测。

**已修复**:新增 `test_render`(校验 `render()` 返回 `fig`)、
`test_sensor_and_text_helpers`、`test_state_instance_and_full_options`
(含 State 实例直接传入、dict 的 side/kind/size、以及 `_fit_end` 的
自由端口与同轴吸附分支)。`core.py` 覆盖率 91% → 98%。

#### 7. ✅ `style.use_font()` 未测(已修复,现 96%)

`style.py:40-46` 只影响 stdout,但它是 README 里排查中文方框字的第一入口。

**已修复**:新增 `test_use_font_prints`,用 `capsys` 断言输出包含"使用字体"
并校验返回值等于当前 `FONT`。

#### 8. 测试直接 import 私有函数

`tests/test_rrplot.py:13` 从 `rrplot.core` 导入 `_fit_end` /
`_orthogonalize` / `_is_sensor` / `_resolve_at`。这些函数名带下划线意味着
"内部 API",测试却深度依赖它们——将来重构内部实现会连带改测试。

**建议**:可接受(被测算法确实是核心且无公开等价物),但建议在
`core.py` 的 `__all__` 之外显式注释"以下模块供测试使用",
让重构者知道改动半径。

#### 9. hvac 工厂名在测试里硬编码列举

`test_rrplot.py:341-346` 显式列出 17 个工厂名(为了避开
`vars(parts)` 把 matplotlib 类也捞进来)。新增符号时忘记加进去,
烟雾测试就少测一个,且不会报错。

**建议**:改为 `for name, obj in vars(hvac).items(): if callable(obj) and
not name.startswith("_")`,并保留一个断言数量下限(如 `>= 17`)兜底。

### P3 —— 工程与协作

#### 10. 缺 `CONTRIBUTING.md` / `CODE_OF_CONDUCT.md`

库已经有清晰的新部件添加路径(写 `_xxx` 绘制函数 + `_part(...)` 端口表,
或用 `make_partial` 派生),但没写下来。上面第 4 条的测试也是新部件的
隐含要求。

**建议**:补一份 `CONTRIBUTING.md`,内容:目录约定、如何加部件、
如何加示例、`pytest`/`ruff` 必须通过、提交信息风格(现有 commit 是
中文单行摘要,很短,照此写即可)。

#### 11. 文档只有 API 自动提取,没有叙事部分

`docs/` 目前是 `index.rst` + `api.rst`,读者仍需回到 README 才能理解
坐标系约定、端口方向规则、走线算法为什么这么设计。新用户读 API 文档
时最大的坎恰恰是"为什么 y 轴向下""为什么 `via` 有三种写法"。

**建议**:本次已补 `docs/design.md`(坐标系/端口/走线算法)与
`docs/tutorial.md`(上手 + 部件速查 + 扩展),后续可再补 FAQ。

#### 12. 文档没有部署

`docs/_build/` 已被 gitignore,但没有任何托管(Read the Docs 配置或
`docs` job 推到 GitHub Pages)。API 文档只能本地构建。

**建议**:加 `.readthedocs.yaml` 或在 `ci.yml` 追加一个仅在
`push` 到主分支时触发的 `sphinx-build -b html docs docs/_build/html`
并上传 artifact。RTD 配置量最小。

#### 13. `examples/*.py` 仍带 `sys.path.insert` 样板

16 个示例全都有这两行(未安装包时的兜底)。README 已经推荐
`pip install -e .`,样板其实可以删;但删了之后"克隆即跑"的能力就没了。

**建议**:二选一,别两边都留。建议保留(本仓库主要用途是本地看图),
但在文件顶部注释里写明"已 `pip install -e .` 可删掉下面两行"。

#### 14. 16 张示例 PNG 入库

每个示例提交一张 PNG(`examples/*.png`,16 个文件)。好处是 README 能直接
引用;坏处是二进制膨胀且每次改图都要重提。

**建议**:若在意仓库体积,改用 git-lfs 或只保留 4~5 张代表图,
其余按需生成。可不采纳——学术项目里图随码走是常见且可接受的。

#### 15. 部分修复 —— ruff 配置已加,`pre-commit` 仍未有

CI 跑 `ruff check rrplot tests`,原本用的是 ruff 默认规则(E/F),
仓库里没有 `[tool.ruff]` 配置段。`parts.py:761` 的 `from .core import
make_partial  # noqa: E402,F401` 说明规则集是"撞上了才豁免"而非主动约定。

**已修复**:`pyproject.toml` 加 `[tool.ruff]`(line-length 88、
select `E/F/W/I`),`parts.py` 末尾的循环导入已上提为
`from .core import make_partial  # noqa: F401`(验证过不成环:
`core.make_partial` 内部是函数内延迟导入 `from .parts import Part`)。
并按 isort 重排了 `core`/`hvac`/`parts`/`tests` 的导入块。`ruff check` 全绿。

**仍待处理**:`.pre-commit-config.yaml` 还没加,本地提交前不会自动跑
lint/format。可选,不影响 CI。

### P4 —— API 一致性(非阻塞)

#### 16. `State` 支持 dict / 元组两种写法,`Node` 只支持位置参数

`pipe(states=...)` 接受 `("1", 0.5)` 元组、`{"text":..., "at":...}` 字典、
或 `State` 实例三种形式(`core.py:312-323`);`add()` 则只有
`add(part, label, loc, **style)` 一种。扩展性上略不对称,但实践中
`add()` 已经能用 `**style` 覆盖绘制参数,够用了。

**建议**:不改。若要改,统一为"元组 + dict 双入口"并给 `Node` 加 dict
初始化,收益小于 API 破坏成本。

#### 17. dict 形式 `states` 的 `at` 默认 `"mid"`,元组形式没有默认

`{"text": "1"}` 等价于 `at="mid"`(=0.5),而 `("1",)` 会 IndexError。
默认值不一致但都不算错误,文档已说明。

**建议**:文档补一句即可。

---

## 四、安全与许可

- 无网络请求,无 `eval`/`exec`,无反序列化不可信输入;唯一解析外部文件的
  路径是 `svgparts.load_svg_part`,用 `xml.etree.ElementTree` 解析
  (Python 3.9+ 的 `ElementTree` 不解析外部实体,无 XXE 风险)。
- MIT 许可证,`LICENSE` 与 `pyproject.toml` 的 `license` 字段一致。

---

## 五、总结评分

| 维度 | 评分 | 上次 | 说明 |
| --- | :---: | :---: | --- |
| 代码质量 | ★★★★☆ | ★★★★☆ | 错误信息与常量提取到位,`parts.py` 体量偏大 |
| 架构设计 | ★★★★★ | ★★★★★ | 分层单一依赖,扩展路径清晰 |
| 测试覆盖 | ★★★★★ | ★★★☆☆ | 43 例 / 96%,变体分支与 bridge 已补 |
| 文档完整 | ★★★★☆ | ★★★★☆ | 本次补 design + tutorial,缺托管部署 |
| 工程化 | ★★★★★ | ★★☆☆☆ | 打包/许可/CI/版本单一来源/ruff 配置已齐,缺 pre-commit |

**整体评价**:初版报告的三块主要短板(工程化配置、文档站、测试盲区)已经
全部补完。当前项目处于"功能完整、可发布、可维护"的状态,剩余问题集中在
文档托管部署、`pre-commit`、`CONTRIBUTING.md` 这类协作辅助,不再有
结构性或正确性风险。

---

## 六、建议的执行顺序

已完成的项见下,未做的按序号排在最后:

1. ✅ 版本号单一来源(`__version__` + `setuptools.dynamic`)
2. ✅ `packages.find` 替代硬编码清单
3. ✅ `Diagram` 零尺寸不再告警
4. ✅ 补全变体渲染测试(压缩机 7 style、换热器 5 shape、svgparts 的
   `bridge`、label 有/无全件、`sensor`/`text`/`State` 全参数、`use_font`)
   —— 覆盖率 85% → 96%
5. ⬜ `CONTRIBUTING.md` + 文档托管(RTD 配置)
6. ✅ `[tool.ruff]` 配置 + `parts.py` 循环导入上提
7. ⬜ 测试里 hvac 工厂改为自动发现,保留数量下限断言
8. ⬜ `.pre-commit-config.yaml`

---

## 附录:关键事实速查

- 测试:`python -m pytest`(也可直接 `python tests/test_rrplot.py`)
- 覆盖率:`python -m pytest --cov=rrplot --cov-report=term-missing`
- 文档:`python -m sphinx -b html docs docs/_build/html`
- 静态检查:`ruff check rrplot tests`
- 导出部件单图:`python export_parts_svg.py` → `SVG/`
- 字体排查:`python -c "from rrplot import use_font; use_font()"`
