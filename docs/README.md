# 文档导航

| 内容 | 入口 |
| --- | --- |
| Python 上手、设计与 API | [Sphinx 文档入口](index.rst) |
| 当前架构与模块边界 | [架构说明](ARCHITECTURE.md) |
| 路线图、方案与实施验收 | [计划索引](plans/README.md) |
| Web 编辑器操作 | [Web 使用说明](../web/README.md) |
| 编辑器内部维护约定 | [编辑器控制器](../web/editor/README.md) |
| 历史评审与复审 | [评审索引](../review/README.md) |
| 已交付版本变化 | [变更记录](../CHANGELOG.md) |
| 开发与贡献 | [贡献指南](../CONTRIBUTING.md) |

根目录保留 README、贡献指南、变更记录和许可证等入口文档。使用/API 文档与
当前架构放在 `docs/`，计划放在 `docs/plans/`，历史评审放在 `review/`。

Markdown 文档直接在仓库阅读；Sphinx 继续构建现有 reStructuredText 文档，
架构和计划通过下载链接提供，不引入 Markdown 解析依赖。
