# 星空、资源与压测复验（2026-11-05）

- 默认固定空间压缩/Z轴增强布局，移除布局切换按钮；详情与导出保持原始坐标。
- 聚焦距离从原先的7.5展示单位缩短到2.5；保留“回到原处”与详情展开。
- 星点增加亮核、光晕、柔和衍射效果；程序化星云共用现有WebGL上下文，单层背景绘制，减少动态效果偏好时停止流动。
- 借鉴React Bits Aurora、Fade Content和Dock的设计，淡入/悬停使用CSS，未引入GSAP/Motion或第二WebGL运行时。SpotlightCard保留上游许可证。
- 浏览器实测1280×800：空间增强按钮DOM数量为0；星点提示底部662px，底栏顶部687.5px，间距25.5px；点选、近距聚焦、回到原处均成功，详情保持可见，无控制台error。截图见 `evidence/screenshots/nebula-tooltip.jpg`。当前设备瞬时显示120FPS，不视为跨设备性能保证。

## 资源约束复验

应用4 vCPU、4GiB、无额外swap，发生器独立1 vCPU/256MiB。新部署inspect见 `evidence/runtime-budget-recheck.json`：根文件系统只读，tmpfs `/tmp`64MiB，容器可写增量4096字节。健康接口报告SQLite3.51.3/WAL/FULL，数据目录约1.79GiB；软水位调整为18GiB，为20GiB总预算预留余量。普通Docker named volume没有硬配额，严格物理容量仍需部署平台文件系统配额，不声称已实现Docker20GiB硬上限。

只读根部署后重放121条真实样本，全部识别为重复，持久化卷及去重路径正常，见 `evidence/readonly-sample-replay.json`。后端及压测测试合计37项通过，前端TypeScript/Vite构建通过。

## 新压测探针烟测

`python3 scripts/benchmark.py --rates 500 --seconds 20 --readers 2 --prefix visual-recheck --containers astra-observatory-app-1 astra-observatory-generator-1`

真实入库8300对象，实测确认414.95对象/秒；列表p95 12.03ms、点云p95 9.96ms，3次并发导出，最终导出数量匹配，报告errors=0。该轮覆盖新增探针，不是长期稳态测试，也不表示已提升后端吞吐。详情见 `evidence/benchmarks/visual-recheck-500-20261105T035451Z-0.json` 与 `docs/performance-review.md`。

## 默认铺屏布局复验

默认投影在水平、垂直方向分别进行密度展开，并随视口比例调整；保留对象ID和有界Z纵深。599点与3000点均可覆盖视口四周，宽屏不会只占中央一团。相同坐标的对象采用每轴独立、稳定的打散顺序，避免二维相同排序造成斜线伪影。此变换不修改详情与导出的原始坐标。

新增3项布局测试覆盖599/3000点在390×844、1280×800、1920×900比例下的边界、边缘密度、原始输入不变、空/单点及同坐标防直线回归。浏览器验证1440×900和390×844、599/3000运行、点选及聚焦返回，无控制台error；截图见 `evidence/screenshots/fullscreen-stars.jpg`。
