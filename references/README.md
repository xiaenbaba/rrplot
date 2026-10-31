# references —— 原型与参考脚本

本目录存放**早期原型、符号源与一次性验证脚本**,不属于 `rrplot` 库本体,
不受 CI 的 lint/覆盖率约束。库的正式能力见 `rrplot/` 与 `examples/`。

生成物(`*.svg` / `*.png`)默认就地写在脚本旁边,已被 `.gitignore` 忽略。

## PFD 符号原型(依赖 `schemdraw`)

| 文件 | 用途 |
| --- | --- |
| `pfd_symbols.py` | 标准 PFD 符号库(ISA-5.1 / ISO 10628,基于 schemdraw);`rrplot.parts` 部分图元由此移植 |
| `compressor_symbols.py` | 压缩机 6 种型式符号对照图 |
| `pfd_symbol_palette.py` | PFD 符号总览 |
| `refcycle_schematic.py` | 制冷循环系统流程图生成器(标准 PFD 符号版) |
| `refcycle_flashtank.py` | 闪发罐制冷循环流程图(标准 PFD 符号版) |
| `verify_econ.py` | 经济器 `rect_diag` 符号几何自检 |

## 纯 SVG 原型(不依赖 matplotlib)

| 文件 | 用途 |
| --- | --- |
| `vrfpart.py` | VRF / GMV 系统图生成原型:`Builder` 拼 SVG 字符串,含 `render_vrf_system()` / `render_gmv()` |
| `draw_gmv.py` | GMV 系统图入口(薄封装,调用 `vrfpart.render_gmv`) |

## 部件对照图(用 `rrplot` 库渲染)

| 文件 | 用途 |
| --- | --- |
| `render_separators.py` | 气液分离器 / 油分离器对比图 |
| `render_valves.py` | 制冷侧 9 种阀体图元对比图 |

## 早期手绘原型

| 文件 | 用途 |
| --- | --- |
| `制冷循环示意图.py` | 双系统制冷循环 + 冷却水路示意图 |
| `涡旋压缩机循环示意图.py` | 涡旋压缩机 + 过冷器(经济器)循环,带状态点编号 |

## 小工具

| 文件 | 用途 |
| --- | --- |
| `fontcheck.py` | 排查系统中文字体文件与 matplotlib 字体族 |
| `showindent.py` | 打印指定文件每行的缩进量 |

## 运行

```powershell
# 依赖 rrplot 的脚本(库已安装或从仓库根运行):
pip install -e .
python references/render_valves.py

# 纯 SVG 原型(无第三方依赖):
python references/vrfpart.py      # 生成 VRF + GMV 两张 SVG
```

`schemdraw` 系原型需额外 `pip install schemdraw`;`fontcheck.py` / `showindent.py`
仅用标准库。
