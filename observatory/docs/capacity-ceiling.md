# 容量与吞吐实测（2026-11-05）

本次未触发接收限流的最高吞吐为 **9,733 有效对象/秒**：每批 1,000 个对象、4 个发生器 worker，持续 60 秒，写入期间有 4 个并发查询客户端和完整导出。把 worker 加到 10 后仅提高到 **10,066/秒**，但出现 973 次 429，列表 p99 从 69 ms 上升到 153 ms。继续增加发送并发，吞吐提升有限，查询延迟明显增加。

数据库现有 **2,447,800 个对象**，数据目录 **9.20 GiB**。本轮新增 1,968,700 个对象，所有结束后的完整导出均与入库数量一致。

## 测试条件

- Linux arm64 Docker；应用 4 vCPU / 4 GiB，独立发生器 1 vCPU / 256 MiB，无额外 swap。SQLite 3.51.3，WAL + synchronous=FULL。实际配置见 [runtime-configuration.json](../evidence/capacity-ceiling/runtime-configuration.json)。
- 所有档位 seed=42、evolving、tree_every_batches=20、retries=2；4 个并发查询客户端，每轮操作间隔 150 ms，查询列表、详情、分类、坐标系、3,000 点空间视图与分类筛选；每 8 秒尝试一次完整导出。
- 前两档目标速率有 5 秒爬坡；不限速发送使用 rate=0、ramp=0。表中延迟为全阶段成功请求统计，原报告也保留 5 秒之后统计。查询开始时尚未创建运行的 404 单独记数。
- 数据目录容量阈值（软限制）为 18 GiB，继续加档的停止阈值为 12 GiB。各轮数据保留，后续档位面对更大的已有数据库；表中的容量是当前运行服务的数据目录总占用。

## 吞吐与交互延迟

| 目标速率 | 每批 / worker | 时长 | 已确认对象/s | 有效入库/s | 列表 p95 / p99 | 点云 p95 / p99 | 接收 429 |
|---|---|---:|---:|---:|---:|---:|---:|
| 5,000 | 100 / 4 | 60s | 2,071.64 | 2,076.64 | 16.6 / 24.5 ms | 77.1 / 95.7 ms | 0 |
| 15,000 | 100 / 4 | 60s | 3,369.93 | 3,376.60 | 18.0 / 24.1 ms | 132.0 / 253.4 ms | 0 |
| 不限速发送 | 100 / 4 | 60s | 4,666.58 | 4,666.58 | 20.6 / 28.7 ms | 266.0 / 290.8 ms | 0 |
| 不限速发送 | 500 / 4 | 60s | 7,891.64 | 7,924.97 | 33.7 / 43.3 ms | 146.5 / 206.9 ms | 0 |
| 不限速发送 | 1000 / 4 | 60s | 9,666.60 | 9,733.26 | 46.1 / 69.2 ms | 400.7 / 479.7 ms | 0 |
| 不限速发送 | 1000 / 10 | 30s | 10,066.49 | 10,066.49 | 125.3 / 153.3 ms | 458.8 / 492.1 ms | 973 |

六档查询与导出均成功，发生器发送对象批次时未出现 HTTP 5xx 或请求超时。最后一档是过载实验：尝试 620 批、确认 302 批，318 批未确认，655 次重试；应用最多同时处理 8 个接入请求，超过上限时返回 HTTP 429。

批量从 100 提高到 500，不限速发送入库速率提高约 70%；从 500 提高到 1,000 再提高约 23%，但点云 p99 从 207 ms 增至 480 ms。分类更新按批次触发，因此批量增大也降低了每对象的分类演化频率；这些结果比较的是完整发生器配置。

## 资源与输出

| 每批 / worker（目标） | 应用峰值 CPU / 内存 | 发生器峰值 CPU / 内存 | 数据目录增量 / 结束占用 | 并发导出次数 | 导出首条最慢 | 最终完整导出 |
|---|---:|---:|---:|---:|---:|---:|
| 100 / 4（5000） | 70.4% / 94.2 MiB | 1.45% / 23.0 MiB | 0.48 / 2.26 GiB | 7 | 18.7 ms | 124,600 条 / 1.40s |
| 100 / 4（15000） | 70.6% / 143.9 MiB | 1.84% / 24.3 MiB | 0.78 / 3.04 GiB | 6 | 18.8 ms | 202,600 条 / 2.48s |
| 100 / 4（尽力） | 138.9% / 187.7 MiB | 1.71% / 26.3 MiB | 1.07 / 4.11 GiB | 6 | 19.5 ms | 280,000 条 / 3.42s |
| 500 / 4（尽力） | 130.3% / 325.6 MiB | 1.31% / 44.2 MiB | 1.78 / 5.90 GiB | 5 | 25.9 ms | 475,500 条 / 5.61s |
| 1000 / 4（尽力） | 151.5% / 454.4 MiB | 1.33% / 43.3 MiB | 2.17 / 8.07 GiB | 5 | 68.0 ms | 584,000 条 / 6.56s |
| 1000 / 10（尽力） | 151.0% / 535.4 MiB | 3.26% / 95.0 MiB | 1.13 / 9.20 GiB | 3 | 191.0 ms | 302,000 条 / 3.30s |

CPU 100% 对应约一个逻辑核，内存列为 Docker 容器内存采样值。最终应用进程 RSS 为 402.78 MiB，本次容器生命周期 RSS 峰值为 416.22 MiB；独立发生器进程 RSS 峰值约 87.04 MiB，见 [runtime-after.json](../evidence/capacity-ceiling/runtime-after.json)。

应用 CPU 峰值约 1.51 核，内存低于 0.53 GiB，发生器 CPU 峰值 3.26%。增加发送并发后吞吐只增 3.4%、限流明显，下一步应测量写入锁等待、事务提交和序列化时间，再选择改动；本轮无需增加数据库、缓存或队列服务。

未触发接收限流的最高吞吐配置最终导出 847.86 MB，6.56 秒完成。全部导出由宿主测试客户端流式校验，后台不生成导出副本。数据目录包含 DB/WAL/SHM/应用日志，18 GiB 是应用设置的容量阈值（软限制）；镜像、Docker 日志和容器层另外计入后台总磁盘预算。

## 数据确认与实际边界

前两档已确认数与入库数分别相差 300、400 个对象；batch500 相差 2,000，batch1000/worker4 相差 4,000，均与到时中断的完整批次数相符。发生器未收到确认时，服务可能已经提交。报告分别记录这两个计数，重复投递仍由原有幂等规则处理。

最初尝试 batch1000/worker16 时，发生器拒绝启动，返回“worker batch buffers exceed the 80 MiB configuration budget”。保持数据大小配置后改为 worker10，缓冲估算 78.125 MiB，完成最终过载测试。原始拒绝响应保存在 [workers16-start-rejection.json](../evidence/capacity-ceiling/workers16-start-rejection.json)。

本次测试覆盖正常接收和并发过载，数据目录最终占用 9.20 GiB。未触发接收限流的最高吞吐为 9,733 对象/s；日常边写边看建议使用 batch500 / worker4（约 7,925/s、列表 p99 43 ms、点云 p99 207 ms）。容量方面已实际保存约 245 万对象；下一轮可单独测试更长运行及大库查询，不再同时调整发送批量与并发。

## 复现与证据

在 `observatory` 目录、应用和发生器均已启动时运行。每条命令自动创建新 test_id，报告写入指定目录。

```bash
python3 scripts/benchmark.py --rates 5000 15000 --seconds 60 --readers 4 --seed 42 --batch-size 100 --workers 4 --prefix ceiling-b100-w4 --containers astra-observatory-app-1 astra-observatory-generator-1 --output evidence/capacity-ceiling
python3 scripts/benchmark.py --rates 0 --seconds 60 --readers 4 --seed 42 --batch-size 100 --workers 4 --prefix ceiling-b100-w4 --containers astra-observatory-app-1 astra-observatory-generator-1 --output evidence/capacity-ceiling
python3 scripts/benchmark.py --rates 0 --seconds 60 --readers 4 --seed 42 --batch-size 500 --workers 4 --prefix ceiling-b500-w4 --containers astra-observatory-app-1 astra-observatory-generator-1 --output evidence/capacity-ceiling
python3 scripts/benchmark.py --rates 0 --seconds 60 --readers 4 --seed 42 --batch-size 1000 --workers 4 --prefix ceiling-b1000-w4 --containers astra-observatory-app-1 astra-observatory-generator-1 --output evidence/capacity-ceiling
python3 scripts/benchmark.py --rates 0 --seconds 30 --readers 4 --seed 42 --batch-size 1000 --workers 10 --prefix ceiling-b1000-w10 --containers astra-observatory-app-1 astra-observatory-generator-1 --output evidence/capacity-ceiling
```

摘要：[summary.json](../evidence/capacity-ceiling/summary.json)。数据库盘点：[database-inventory-after.json](../evidence/capacity-ceiling/database-inventory-after.json)。完整报告已无损 gzip 归档，原文与压缩文件 SHA-256 见 [archive-manifest.json](../evidence/capacity-ceiling/archive-manifest.json)。旧压测报告保持原样。

- [ceiling-b100-w4-5000-20261105T040624Z-0](../evidence/capacity-ceiling/ceiling-b100-w4-5000-20261105T040624Z-0.json.gz)
- [ceiling-b100-w4-15000-20261105T040739Z-0](../evidence/capacity-ceiling/ceiling-b100-w4-15000-20261105T040739Z-0.json.gz)
- [ceiling-b100-w4-0-20261105T040944Z-0](../evidence/capacity-ceiling/ceiling-b100-w4-0-20261105T040944Z-0.json.gz)
- [ceiling-b500-w4-0-20261105T041100Z-0](../evidence/capacity-ceiling/ceiling-b500-w4-0-20261105T041100Z-0.json.gz)
- [ceiling-b1000-w4-0-20261105T041227Z-0](../evidence/capacity-ceiling/ceiling-b1000-w4-0-20261105T041227Z-0.json.gz)
- [ceiling-b1000-w10-0-20261105T041529Z-0](../evidence/capacity-ceiling/ceiling-b1000-w10-0-20261105T041529Z-0.json.gz)
