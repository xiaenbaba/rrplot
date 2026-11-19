# rrplot 架构（2026-11-19）

## 运行与数据流

项目为同仓库的 Python 绘图库和本机 Web 编辑器。网页使用原生 ES modules、
HTML / CSS / SVG；服务使用 Python 标准库，只监听 127.0.0.1。
运行时仅依赖 numpy 和 Matplotlib，不要求 Node 或前端构建；Node 用于开发回归。

浏览器编辑 JSON → 本地几何即时反馈 → POST /api/resolve 规范化与获取图元 →
SVG 画布更新；预览及 SVG / PNG / PDF 导出通过同一 Python 场景渲染实现。
schemaVersion 保持 1，设备、端口 ID、管路和挂接关系保留现有格式。

## 模块边界

| 层 | 入口 | 职责 |
|---|---|---|
| 绘图库 | rrplot/core.py、parts.py、part.py | 图元、端口和 Matplotlib 绘制 |
| 元数据 | rrplot/registry.py | 可编辑图元、参数、端口、边界及挂接/执行机构朝向声明 |
| 场景 | rrplot/scene.py、scene_renderer.py | JSON 校验、路由、挂接、缓存图元和正式出图 |
| 浏览器几何 | web/geometry.js | 路由、吸附、布局、挂接与局部反馈 |
| 文档操作 | web/document.js | 复制、删除、移动、重接和文档操作 |
| 交互入口 | web/app.js、editor/index.js | 创建编辑器、组装控制器、绑定事件和启动 |
| 编辑状态与历史 | web/editor/state.js、session.js | 单实例状态、选择、解析更新、编辑事务、撤销/重做 |
| 文件与输出 | web/editor/files.js、export.js | JSON、草稿恢复、异步加载保护、保存确认、预览与导出 |
| 画布与视图 | web/editor/canvas.js、viewport.js | 场景/辅助层绘制、坐标、缩放与定位 |
| 连线与折点 | web/editor/connections.js、coordinates.js | 端口/三通吸附、分支、重接及折点表单历史和预览 |
| 输入与编辑命令 | web/editor/pointer.js、keyboard.js、selection.js | 拖动、键盘、复制粘贴、对齐/分布及精确移动 |
| 编辑界面 | web/editor/inspector.js、sidebar.js、styles.js、events.js | 属性栏、资源库/对象/检查、批量样式及页面动作 |
| 启动与界面基础 | web/editor/startup.js、ui.js、config.js | 目录/模板初始化、基准适配、DOM、接口与通知 |
| 请求调度 | web/requests.js | 包含响应体的截止时间、错误分类，一个运行中请求＋一个最新待处理快照 |
| 图元传输 | web/glyphs.js | 共享图元响应还原、有界内存图像缓存及旧服务兼容 |
| 画布缓存 | web/canvas.js | 按 ID 保留 SVG 分组，按内容签名更新变化子元素与属性 |
| 浏览器测量 | web/performance.html、benchmark.js | 独立合成图纸，真实编辑器绘制/选择/移动/撤销计时 |
| 服务状态 | web/service.js | 健康检查、版本与代码变更提示，不修改图纸 |
| 属性展示 | web/inspector.js | 可折叠分组、缩略图 URL 和 DOM 辅助 |
| 其他 UI | web/checks.js、objects.js、styles.js | 检查、对象搜索与批量样式 |
| HTTP 服务 | server/run.py | API、静态资源、渲染锁与停止接口 |
| 生命周期 | server/manage.py、service.py | 启停、实例身份、代码指纹和后台日志 |

正式 JSON 由用户下载，草稿与偏好保存在浏览器 localStorage，历史保存在内存。
管理凭证位于忽略提交的 .rrplot-web/service-端口.json，不由 HTTP 静态接口公开。
健康接口不返回密钥；停止接口拒绝浏览器 Origin，且必须携带正确实例密钥。

### 编辑器内部约定

`createEditor()` 持有唯一 `state` 和 `commands`，控制器工厂只创建闭包，
不注册事件、不发送请求；组装全部接口后，`bindEvents()` 幂等绑定一次，
随后启动目录和默认图纸载入。控制器不互相导入，通过共享命令表调用其他
控制器；几何、纯文档操作、请求与缓存等底层模块仍使用普通静态导入。
共享命令表的命名接口由原生 ES 模块回归逐项核验。

文件载入、解析、预览和导出继续使用原有 revision/request/session 判断；
拖动和微调仍由 session 统一提交历史。事件绑定与所属控制器放在一起，
页面动作、跨标签页通知和通用偏好在 events 中协调。开发说明见
[web/editor/README.md](web/editor/README.md)。

画布先在脱离页面的 SVG 分组中建立新对象，按顺序通过 DocumentFragment
批量挂入；已有分组保留 DOM 身份。图元图像在 SVG defs 中按图像标识与边界
共享，设备用 use 引用；同样内容的设备复用最多 64 份结构模板，克隆端口时
重写所属设备 ID。模板和图像定义仅保留当前场景所需项，不进入 JSON。
页面/网格复用，端口选择仅使所属设备内容失效；附着文字复用当次节点/路由
索引，带背景文字先统一读取已挂入文字的边界，再写背景，避免逐项强制布局。
载入先计算视图再插入 SVG，普通重绘复用宽度，缩放、适应和 ResizeObserver
重新测量容器，避免每帧读取新场景尺寸。

## 验证与交付

- pytest 覆盖 Python、Node 模块及编辑交互；tests/fixtures/geometry_contract.json
  提供前后端共用路由与挂接案例，补充已有三通拆分合并等回归。
- 原有交互场景通过 tests/web_editor_harness.cjs 加载实际控制器工厂；旧状态名
  仅由测试适配器映射，生产页面不暴露全局变量。另用 Node 原生 ES 模块验证
  实际导入、接口完整性、状态隔离及重复绑定保护，并核验嵌套静态资源的 MIME。
- CI 显式安装 Node 22，RRPLOT_REQUIRE_NODE=1 时缺少 Node 直接失败。
- 发布复用全部 CI 作业，检查标签、源码和构建 wheel 版本一致后再发布。
- sdist 包含服务、网页、启动管理脚本、基准工具及共享夹具；wheel 保持绘图库与模板。
- tools/benchmark_web.py 测量后端解析和响应体大小；不代表浏览器拖动帧率或网络耗时。
  `--shared` 测量去重协议；`/performance.html` 提供独立浏览器基准。
- 浏览器基准在各规模前清空场景，拆分解析/创建/视图阶段，记录同步载入及
  载入到双帧等待的时间。同步计时不涵盖后续全部布局、图片解码和绘制；
  双帧指标受后台/不可见 iframe 节流影响，不作为 FPS 或完整就绪保证。
- `sharedGlyphs: true` 请求返回 glyphs 字典及 geometry.glyphId；未启用仍返回
  geometry.image。SVG 缓存键由类型及规范化参数决定，不存入用户 JSON。
- 图元目录及几何返回 capabilities，挂接集合及执行机构朝向由 Python 注册表
  声明；浏览器优先读取声明并保留旧服务回退，schemaVersion 仍为 1。
- 排版检查仅在点击“检查”时执行，依据真实文字边界及旋转设备包围框，
  跳过正常端点设备与所属管路的挂接阀件，不移动对象、不执行自动避障。

## 继续演进

现行待办见 ROADMAP.md，版本行为变化见 CHANGELOG.md；WEB_PROJECT_PLAN.md
保留历史实施日志。编辑器职责拆分及本轮性能优化已完成；后续以多种真实图纸
和稳定前台环境继续测量，补充持续端到端测试。完整 Web 安装包、自动避障、
协作与热力计算单独规划。
