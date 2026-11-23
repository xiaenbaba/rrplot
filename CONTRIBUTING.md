# 贡献指南

感谢参与 `rrplot`。本项目是"坐标式部件拼装 + 走线式连管"的制冷循环 / HVAC
示意图库,输出 PNG / PDF / SVG。

## 环境

```powershell
pip install -e ".[test]"     # 开发:装包 + pytest
python -m pytest             # 全部用例
ruff check rrplot tests examples server tools export_parts_svg.py   # 静态检查(CI 同款)
```

提交前这两条必须通过。CI 还会:跑 `pytest --cov`(覆盖率下限 90%)、逐个执行
`examples/*.py`、构建 Sphinx 文档。

## 目录约定

```
rrplot/     库本体:core(引擎)/ parts(部件)/ hvac、svgparts(HVAC)/
               style(样式)/ _primitives(底层绘制)
examples/      每张图一个脚本 + 同名 PNG(入库)
tests/         pytest 回归测试
docs/          使用/API 文档与架构说明，入口 docs/README.md
docs/plans/    路线图、专项实施计划与验收记录
review/        项目评审与复审记录，新报告按 review-YYYYMMDD.md 命名
references/    早期原型与参考脚本(不入库的生成物见 .gitignore)
SVG/           export_parts_svg.py 导出的部件单图
```

`references/` 下的东西不是库的一部分,改动它不受 CI 约束。

路线优先级与完成状态维护在 `docs/plans/ROADMAP.md`；详细方案和验收记录
放在同目录的专项计划中。当前架构维护在 `docs/ARCHITECTURE.md`，历史评审
放在 `review/`；已替代的计划可移入 `docs/plans/archive/` 并更新索引和链接。

## 加一个部件

1. 在 `rrplot/parts.py` 里写绘制函数 `_xxx(ax, x, y, label=None, **kw)`,
   以 `(x, y)` 为中心锚点,只用 `_primitives` 的 `line` / `txt` 和 matplotlib
   patch;线宽/颜色取 `style.py` 的常量。
2. 用 `_part("名字", {"端口名": (dx, dy)}, _xxx, dirs={...})` 登记端口表。
   端口偏移 `(dx, dy)` 隐含接管方向;双轴非零的端口用 `dirs` 显式声明法向。
3. 尺寸可变的部件写成工厂 `make_xxx(...)`,返回 `Part`,并在文件底部给出默认
   实例;特殊端口用 `make_partial(part, ports=..., dirs=...)` 派生。
4. 在 `tests/test_rrplot.py` 补端口断言(偏移 + `direction`)。
5. 在 `examples/` 加一个同名演示脚本(见下)。
6. 跑 `python export_parts_svg.py` 刷新 `SVG/` 单图(可选)。

命名约定:贯通式两口元件(阀、过滤器、毛细管)用 `in`/`out`;多口 / 换热类
用 `left`/`right`/`top`/`bottom` 表示边中点。

## 加一个示例

`examples/<name>.py` 从仓库根直接可跑,输出同名 PNG:

```python
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rrplot import Diagram, parts

d = Diagram(width=..., height=...)
# d.add(...) / d.pipe(...)
d.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "<name>.png"))
```

坐标系:1 单位 = 1 像素,x 向右、y 向下;`via` 支持方向令牌 / 坐标 / 裸字符串
三种写法(详见 `docs/tutorial.rst`)。示例脚本必须能被 CI 无界面跑通,不要调用
`plt.show()`。

## 测试

- 端口、走线算法、错误提示等行为用精确断言。
- 纯几何的绘制分支(新增 style / shape / label 有无)用"全量上屏烟雾测试"覆盖
  (`test_render_*`),不做像素级回归(中文字体跨平台差异太大)。
- 新增 `parts` / `hvac` 图元会被 `test_render_every_part_and_hvac_symbol`
  自动发现,无需改测试;但端口语义仍要单独断言。

## 提交信息

沿用现有风格:中文单行摘要,前缀标明模块,冒号分隔。例如:

```
parts: 加过冷器图元(矩形 + 中央竖线四口,支路逆流错开)
examples: 加多联机(VRF)系统图,补 separator 镜像与虚线管路支持
docs: 补 design/tutorial,版本单一来源
```

一次提交只做一件事;改公共 API 时同步更新 `README.md` / `docs/` 与测试。
