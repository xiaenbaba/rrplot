# HVAC 工程标准 SVG 图元库

## 特性
- 17 个标准 SVG 图元
- 每个图元带 data-symbol / data-connection-points 元数据
- 连接点可用于管道自动吸附
- 图元支持拖拽、缩放、旋转的工程软件扩展
- 附带浏览器端编辑器 Demo

## 目录
- symbols/：独立 SVG 图元
- library.json：图元库与连接点定义
- 编辑器_demo.html：浏览器拖拽编辑 Demo

## 连接点
连接点以唯一 id 标识，例如 in/out、water_in/water_out、loop1/loop2/loop3。
后续可以据此实现正交管线自动连接、吸附、断开、重新路由。

## 说明
SVG 图元为重新绘制的工程矢量图，不是简单把 PNG 嵌入 SVG，因此可无限缩放。
