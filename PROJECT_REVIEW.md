# cycleplot 项目审查报告

**审查日期**: 2026-10-11  
**项目类型**: 制冷循环与 HVAC 示意图绘制库  
**技术栈**: Python, Matplotlib, NumPy

---

## 项目概况

**cycleplot** 是一个制冷循环与 HVAC 示意图绘制库，基于 Matplotlib 实现坐标式部件拼装和走线式连管，支持 PNG/PDF/SVG 输出。代码总体质量较高，架构清晰，测试覆盖良好。

---

## 优点

### 1. 架构设计优秀

分层清晰，职责分明：
- `core.py`（引擎）：画布管理、走线算法
- `parts.py`（部件库）：制冷部件定义
- `hvac.py`（HVAC 符号）：暖通空调符号族
- `_primitives.py`（底层绘制）：文本、折线、箭头原语

端口系统设计优雅，`Port` 携带绝对坐标与外法向，连线自动正交化（`_orthogonalize`）与端口吸附（`_fit_end`）解决了手工对齐的痛点。

### 2. 测试覆盖良好

- **24 个测试全部通过**，耗时 3.80s
- 覆盖端口定义、走线算法、SVG 加载、部件工厂等核心路径
- 测试用例设计合理，如 `test_fit_end_snap_small_tangent_offset` 精确验证吸附容差（10px）

### 3. 文档质量高

- README.md 结构完整，快速上手代码简洁
- 核心概念解释到位（`via` 三种写法、`states` 标注语法）
- 示例丰富：15 个 `.py` 配套图片，覆盖单级循环、经济器、四通阀等场景

### 4. 代码风格规范

- docstring 详尽（如 `_compressor` 的 7 种 `style` 说明）
- 变量命名语义化（`SNAP_TOL`、`ARROW_HALF`）
- 注释点到为止不冗余

---

## 问题与改进建议

### 1. 依赖管理缺失

**问题**：
- `requirements.txt` 仅列出 numpy/matplotlib/pytest，无版本锁定文件
- 缺少 `setup.py` 或 `pyproject.toml` 打包配置
- README 明确写了"无打包依赖管理"，但这对分发和复现环境不利

**建议**：
- 添加 `setup.py` 或 `pyproject.toml`，使项目可通过 `pip install -e .` 本地安装
- 考虑使用 Poetry 或 pip-tools 生成锁定文件
- 在 README 补充安装说明（目前只有"克隆后直接 import"）

### 2. Git 状态混乱

**当前状态**：
- master 分支有 14 个已修改文件（M 标记）
- 12 个未跟踪文件（?? 标记），包括新增的 README.md、4 个新示例、evi_cycle.py 等
- 处在 master 而非 main 分支（README 显示主分支是 main）

**建议**：
- 立即提交当前修改，创建有意义的 commit message（如"新增截止阀/电磁阀/低压罐部件与示例"）
- 将 master 合并到 main 或统一主分支名
- 检查 `.workbuddy/`、`SVG/`、`evi_cycle.*` 是否应加入版本控制

### 3. 字体回退机制脆弱

**问题**：
- `style.py` 的 `FONT_CANDIDATES` 列表依赖系统已安装字体
- 未安装时回落到 DejaVu Serif（不支持中文），用户可能遇到方框字

**建议**：
- 在 README 补充字体依赖说明（Windows 建议安装宋体，macOS 建议 Songti SC）
- 考虑内嵌开源中文字体（如思源宋体）或提供字体安装脚本
- `use_font()` 函数可增强：打印实际渲染的字体族，方便排查缺字

### 4. 测试覆盖盲区

**问题**：
- 测试主要集中在端口定义和走线算法
- 缺少完整渲染测试（当前只有 `d.render()` 但未校验输出图像）
- 缺少边界条件测试（如 `Diagram(width=0, height=0)` 或空管线）
- 缺少错误处理测试（如端口名拼错、无效 `via` 令牌）

**建议**：
- 增加图像回归测试（用 `matplotlib.testing.compare.compare_images` 对比参考图）
- 添加异常路径测试，确保错误信息清晰
- 使用测试覆盖率工具（pytest-cov）量化当前覆盖度

### 5. 示例代码重复

**问题**：
每个 `examples/*.py` 都有相同的样板代码：
```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cycleplot import ...
```
这在正式打包后会失效。

**建议**：
- 打包后用户通过 `pip install cycleplot` 安装，示例直接 `from cycleplot import ...` 即可
- 示例移到独立的 `examples/` 包，添加 `__init__.py`

### 6. API 一致性问题

**问题**：
- `d.add()` 返回 `Node`，`d.pipe()` 返回 `Pipe`，但用户更常需要 `Diagram` 链式调用
- `make_partial()` 在 `core.py`，但语义上属于 `parts` 模块
- `State` 类支持 dict 初始化，但 `Node` 不支持

**建议**：
- `add()` 和 `pipe()` 返回 `self`（Diagram），方便链式调用；需要 `Node/Pipe` 时通过 `_nodes[-1]` 访问
- 将 `make_partial()` 移到 `parts.py`，或在 `parts/__init__.py` 中重新导出
- 统一初始化风格（要么都支持 dict，要么都用关键字参数）

### 7. 性能优化空间

**问题**：
- `Pipe.points()` 缓存了路径点（`_pts`），但 `_orthogonalize` 每次都重新计算
- 对复杂图（>50 条管线）可能有性能瓶颈

**建议**：
- 在 `Diagram.render()` 前批量计算所有管线路径
- 考虑用 numpy vectorize 加速折线计算

### 8. 文档缺口

**问题**：
- 缺少 API 参考文档（目前只有 README + docstring）
- 没有设计文档解释坐标系、端口方向约定、管线算法原理
- 缺少贡献指南（如何添加新部件、如何提交 PR）

**建议**：
- 用 Sphinx 生成 API 文档，发布到 Read the Docs
- 补充 `docs/design.md` 解释核心算法
- 添加 `CONTRIBUTING.md` 与 `CODE_OF_CONDUCT.md`

### 9. 代码风格微调

**观察**：
- `_primitives.py` 中 `txt()` 的 `bg` 参数命名不清晰（应为 `background` 或 `bbox`）
- 部分魔术数字未提取为常量（如 `core.py:256` 的 `18`、`22` 是传感器圆圈相关尺寸）
- `parts.py` 超过 1000 行，可拆分为子模块（`parts/compressor.py`、`parts/valves.py` 等）

**建议**：
- 重命名 `bg` → `bbox` 并更新调用处
- 提取魔术数字到 `style.py`（如 `SENSOR_CIRCLE_RADIUS = 18`）
- 重构 `parts.py` 为包结构

---

## 安全与许可

### 安全性
- 未发现明显安全问题（无外部网络请求、无 eval/exec）

### 许可证
- **缺少 LICENSE 文件**：建议添加开源协议（MIT/Apache-2.0/GPL 根据使用场景选择）

### CI/CD
- 无 `.github/workflows/` CI 配置，建议添加 GitHub Actions 自动跑测试

---

## 总结评分

| 维度 | 评分 | 说明 |
|------|:----:|------|
| 代码质量 | ★★★★☆ | 逻辑清晰，命名规范，有改进空间 |
| 架构设计 | ★★★★★ | 分层合理，扩展性强 |
| 测试覆盖 | ★★★☆☆ | 核心路径覆盖好，缺少渲染测试 |
| 文档完整 | ★★★★☆ | README 优秀，缺 API 文档 |
| 工程化 | ★★☆☆☆ | 缺打包配置、CI、许可证 |

**整体评价**：这是一个设计优秀、实用性强的专业领域库，核心功能扎实。当前主要短板在工程化配置（打包、CI、文档站）和 Git 管理。

---

## 优先级建议

### 高优先级（立即处理）
1. ✅ **提交当前修改**：整理 Git 状态，提交 14 个已修改文件
2. ✅ **添加 LICENSE**：选择合适的开源协议
3. ✅ **添加 setup.py**：实现标准打包

### 中优先级（近期完成）
4. 补充测试覆盖（图像回归测试、边界条件）
5. 统一 master/main 分支
6. 添加 GitHub Actions CI

### 低优先级（逐步优化）
7. 重构 `parts.py` 为包结构
8. 用 Sphinx 生成 API 文档
9. 性能优化（批量计算、numpy 加速）

---

## 附录：关键文件清单

### 核心模块
- `cycleplot/core.py` (371 行)：引擎、Diagram、Pipe、端口系统
- `cycleplot/parts.py` (>1000 行)：制冷部件库
- `cycleplot/hvac.py` (>150 行)：HVAC 符号族
- `cycleplot/style.py` (41 行)：全局样式常量
- `cycleplot/_primitives.py` (25 行)：底层绘制原语
- `cycleplot/svgparts.py` (>100 行)：SVG 加载器

### 测试与示例
- `tests/test_cycleplot.py` (249 行)：24 个测试用例
- `examples/` (15 个脚本)：示例代码与配图

### 配置文件
- `requirements.txt`：依赖声明
- `.gitignore`：版本控制排除规则
- `README.md`：项目文档

---

**报告生成时间**: 2026-10-11  
**审查工具**: Claude Code (Sonnet 4.5)
