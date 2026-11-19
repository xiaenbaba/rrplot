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
| 交互入口 | web/app.js | 编辑状态、历史、画布与事件编排，按功能渐进分离 |
| 请求调度 | web/requests.js | 包含响应体的截止时间、错误分类，一个运行中请求＋一个最新待处理快照 |
| 图元传输 | web/glyphs.js | 共享图元响应还原、有界内存图像缓存及旧服务兼容 |
| 画布更新 | web/canvas.js | 按 ID 保留 SVG 分组，按内容签名更新变化子元素与属性 |
| 浏览器测量 | web/performance.html、benchmark.js | 独立合成图纸，真实编辑器绘制/选择/移动/撤销计时 |
| 服务状态 | web/service.js | 健康检查、版本与代码变更提示，不修改图纸 |
| 属性展示 | web/inspector.js | 可折叠分组、缩略图 URL 和 DOM 辅助 |
| 其他 UI | web/checks.js、objects.js、styles.js | 检查、对象搜索与批量样式 |
| HTTP 服务 | server/run.py | API、静态资源、渲染锁与停止接口 |
| 生命周期 | server/manage.py、service.py | 启停、实例身份、代码指纹和后台日志 |

正式 JSON 由用户下载，草稿与偏好保存在浏览器 localStorage，历史保存在内存。
管理凭证位于忽略提交的 .rrplot-web/service-端口.json，不由 HTTP 静态接口公开。
健康接口不返回密钥；停止接口拒绝浏览器 Origin，且必须携带正确实例密钥。

## 验证与交付

- pytest 覆盖 Python、Node 模块及编辑交互；tests/fixtures/geometry_contract.json
  提供前后端共用路由与挂接案例，补充已有三通拆分合并等回归。
- CI 显式安装 Node 22，RRPLOT_REQUIRE_NODE=1 时缺少 Node 直接失败。
- 发布复用全部 CI 作业，检查标签、源码和构建 wheel 版本一致后再发布。
- sdist 包含服务、网页、启动管理脚本、基准工具及共享夹具；wheel 保持绘图库与模板。
- tools/benchmark_web.py 测量后端解析和响应体大小；不代表浏览器拖动帧率或网络耗时。
  `--shared` 测量去重协议；`/performance.html` 提供独立浏览器基准。
- `sharedGlyphs: true` 请求返回 glyphs 字典及 geometry.glyphId；未启用仍返回
  geometry.image。SVG 缓存键由类型及规范化参数决定，不存入用户 JSON。
- 图元目录及几何返回 capabilities，挂接集合及执行机构朝向由 Python 注册表
  声明；浏览器优先读取声明并保留旧服务回退，schemaVersion 仍为 1。
- 排版检查仅在点击“检查”时执行，依据真实文字边界及旋转设备包围框，
  跳过正常端点设备与所属管路的挂接阀件，不移动对象、不执行自动避障。

## 继续演进

现行待办见 ROADMAP.md，版本行为变化见 CHANGELOG.md；WEB_PROJECT_PLAN.md
保留历史实施日志。继续根据浏览器实测拆分交互、历史与文件控制器，补充持续
端到端测试。完整 Web 安装包、自动避障、协作与热力计算单独规划。
