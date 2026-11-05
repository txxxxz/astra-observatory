# 压测测量与优化复核（2026-11-05）

本次先改进测量覆盖和对照条件，没有修改接收事务、降低持久化等级或声称吞吐已经提升。原始历史结果未改写，新脚本的报告版本为 2。

## 已有证据

来源：`evidence/benchmark-summary.json` 与 `evidence/benchmarks/*.json.gz`。

| 目标速率 | 时长 | 有效入库对象/秒 | 列表 p95 | 指标 p95 | 应用峰值 CPU / 内存 |
|---|---:|---:|---:|---:|---:|
| 500 | 60 s | 464.97 | 9.03 ms | 11.41 ms | 18.12% / 51.55 MiB |
| 3,000 | 60 s | 1,736.63 | 13.77 ms | 18.01 ms | 47.51% / 77.90 MiB |
| 10,000 | 120 s | 2,804.98 | 17.62 ms | 36.33 ms | 109.63% / 169.40 MiB |

最高档总入库 336,600 个对象，最终完整导出 499,691,553 字节，耗时 4.15 秒；主流 ACK 336,500 个对象，发生器记录了收尾阶段的 1 个 interrupted request。ACK 和最终入库的差别已有 receipt audit，不应把两者混写。Docker CPU 100% 约对应一个逻辑核；该档发生器采样峰值 CPU 仅 2.05%，不支持“发生器 CPU 跑满”的判断。

现有测试只包含一个串行浏览客户端，最高档 725 次列表、719 次详情和 59 次指标请求；没有测量星空点云、分类导航或多人查询。它证明了这组负载下的表现，不能称为系统吞吐上限。60–120 秒结果也不能替代长期稳态、接近磁盘容量或百万对象测试。

## 本次已实现的脚本改进

- 增加 `--readers`、`--browse-interval`：控制并发浏览人数和操作间隔。每 10 个浏览周期探测一次分类、坐标系、点云和分类后代筛选；默认点云 3,000 点，可用 `--points-limit` 调整（最高 5,000）。
- 输出 p50/p95/p99/max、请求成功/失败数和 HTTP 状态计数；启动初期的 404 仍计入请求计数，不再把 5 秒之后的指标 404 静默略过。延迟分位数仅包含成功响应，必须和失败计数一起阅读。
- 同时保留全阶段与 `--warmup-seconds` 之后的延迟统计，避免用预热筛选隐藏全程表现。浏览客户端是“请求结束后等待”的闭环模型，不能用于声称开放到达率下的最大 RPS。
- 导出额外记录响应头到达时间、第一条有效记录到达时间和完整耗时，空导出的首条时间为 null。`--no-exports` 可禁用持续写入期间的导出，仍保留结束后的完整导出数量校验。
- 记录发生器 ACK、attempted、in-flight、429/5xx 和进程 CPU/内存时间序列，便于区分发送节奏、等待 ACK 和应用压力。
- 同一批次矩阵固定 `--seed`（默认 42），不再按档位自动变更种子；记录 `probe_config`，版本 2 与旧脚本的不同查询负载不能直接作吞吐回归对比。
- 指标时间序列仅保留标量；最终完整指标仍保留。旧最高档重复保存分类树/最近消息约 4.6 MB，这些重复内容与趋势测量无关。
- 记录开始健康检查到结束指标之间观察到的目录字节差。它包含 WAL/checkpoint 和其他运行的变化，不是每对象精确物理成本。

验证：`python3 -m unittest discover -s tests -p test_benchmark.py -v`，4 个测试通过；覆盖尾延迟、空导出、响应头/首条/完整导出计时，以及并发探针、429 计数、固定种子、紧凑指标及最终数量校验。单测不访问真实发生器或 Docker。新版本已执行20秒短测（2个浏览客户端），入库8,300个对象，列表p95 12.03 ms、点云p95 9.96 ms，3次并发导出，最终导出数量匹配，0错误。报告见 `evidence/benchmarks/visual-recheck-500-20261105T035451Z-0.json`。该轮仅验证新测量链路，不代表持续性能或调优收益。

## 优先验证的性能改进

| 优先级 | 对照实验 | 要回答的问题 |
|---|---|---|
| 1 | 相同数据配置下，并发导出开/关 | 完整导出是否占用 CPU、磁盘和查询线程，拖慢接入或交互？ |
| 2 | batch_size 100 / 500，workers 固定 4 | 更大的批事务能否摊薄每次 FULL commit、连接建立和协议成本？同时看尾延迟、错误及内存。 |
| 3 | 固定批量，readers 1 / 4 / 8 | 当前点云、递归分类、指标聚合在持续写入时的尾延迟和失败率如何？ |
| 4 | 先分别测 60–120 秒，再在选定档位测 5–10 分钟 | 吞吐、WAL/目录大小、RSS、429 和查询 p99 是否随时间恶化？ |

源码显示写入由单个 `Store.writer` 锁串行化，每批创建 SQLite 连接，在 FULL WAL 下提交；因此事务同步、验证/序列化和锁等待都是值得测量的候选开销。应用只用约一个 CPU 核而未占满 4 核，**不能**据此单独判定 SQLite/fsync 就是唯一瓶颈。应先加写入各阶段计时或进行上述对照，再决定是否复用专用 writer 连接、批量优化或迁移存储；不应靠增加 Uvicorn 进程绕过单写入设计。

`metrics()` 每次返回完整分类、坐标系和最近消息，且重算分类子树统计；实际浏览器的轮询成本值得单独量化。若此接口的 p99/CPU 随规模增长明显，可以将轻量计数与低频分类更新分开，或按 revision 缓存分类结构。应以实测收益决定，避免先添加 Redis 等后台组件。

## 复现入口

从 `observatory` 目录运行，应用和发生器容器均需已启动，每个命令自动创建新 test_id。不要与另一个发生器测试同时运行。

```bash
# 覆盖新报告字段的短烟测，不作为持续性能结果
python3 scripts/benchmark.py --rates 500 --seconds 15 --readers 2 --prefix probe-v2-smoke

# 相同负载下对照并发导出的影响
python3 scripts/benchmark.py --rates 3000 --seconds 120 --readers 4 --seed 42 --prefix exports-on --containers astra-observatory-app-1 astra-observatory-generator-1
python3 scripts/benchmark.py --rates 3000 --seconds 120 --readers 4 --seed 42 --no-exports --prefix exports-off --containers astra-observatory-app-1 astra-observatory-generator-1

# 固定其他参数，对照更大的发生器批量
python3 scripts/benchmark.py --rates 10000 --seconds 120 --readers 4 --batch-size 100 --prefix batch-100
python3 scripts/benchmark.py --rates 10000 --seconds 120 --readers 4 --batch-size 500 --prefix batch-500
```

报告保存在 `evidence/benchmarks/`。长期压力前查看剩余磁盘；当前保留原始消息和投影，不自动清理历史运行。不要将上一档留下的总磁盘大小误认为本档独占成本。

## Docker 与 20 GiB 容量边界

当前 Compose 的后台只有应用一个容器；`cpus: 4.0`、`mem_limit: 4g`、`memswap_limit: 4g` 是容器 cgroup 限制，4 GiB 内存之外没有额外 swap 配额。独立发生器限制为 1 CPU / 256 MiB（同样无额外 swap）。`evidence/runtime.json` 记录了先前 `docker inspect` 对应值；当前重建后的值应再次 inspect，不能只凭 compose 文件证明执行环境。

| 项目 | 所在位置与当前控制 | 是否纳入 `/api/health.storage_bytes` |
|---|---|---|
| SQLite 主库、WAL、SHM | `observatory-data:/data`；每次接入前检查目录体积、剩余磁盘 | 是 |
| 应用警告日志 | `/data/observatory.log`；2 MiB × 当前文件及 3 个备份，约 8 MiB | 是 |
| Docker stdout/stderr | Docker 引擎日志；10m × 3 个文件，约 30 MiB | 否 |
| 应用镜像及容器层 | Docker 引擎存储；应用根文件系统已设只读，`/tmp` 为64 MiB tmpfs（计入内存） | 否 |
| 构建缓存/历史镜像 | 开发构建开销，应与交付运行空间区分；仍消耗宿主物理盘 | 否 |
| 发生器镜像与收据卷 | 独立发生器资源，单独报告 | 否 |
| benchmark 报告 | 发压客户端宿主 `evidence/benchmarks` | 否，且 `.dockerignore` 排除，不进入应用镜像 |
| NDJSON 导出 | 后端按块读取，宿主测试客户端流式校验，无后台导出落地文件 | 不额外占持久化卷；缓冲占内存 |
| 浏览器下载 | 浏览器/下载目录 | 否，属于浏览器侧输出 |

`OBS_STORAGE_LIMIT_BYTES=19327352832` 是 **18 GiB 应用软水位**。检查在单写入锁内，事务开始前还会估算 `max(1 MiB, 原消息字节 ×6)` 余量；达到水位或可用空间不足返回非 2xx。这是避免继续确认不可保存数据的保护，不是文件系统硬配额，也不是对单次事务膨胀的数学上限。

普通 Docker named volume 没有可移植的 `20 GiB` 硬上限。当前 `/data` 软水位预留的 2 GiB 应覆盖运行镜像、日志及事务余量，但完整预算必须以实际镜像、writable layer、Docker 日志和数据卷的合计检查，不能只报告 DB 文件或单独 volume。若评测要求严格限制物理磁盘，应把数据卷放在评测平台提供的配额卷/独立受限文件系统中，并把其他运行开销纳入预算；通用 Compose `storage_opt` 不能当作 named-volume 容量限制的替代。

下一轮容器验证应记录以下只读证据：

```bash
docker inspect astra-observatory-app-1 --format '{{json .HostConfig}}'
docker inspect --size astra-observatory-app-1 --format 'writable={{.SizeRw}} rootfs={{.SizeRootFs}}'
docker image inspect astra-observatory:local --format '{{.Size}}'
docker compose exec -T app sh -c 'du -sk /data; df -k /data'
```

镜像共享层、日志轮转和 WAL checkpoint 都会使简单相加出现重复或时点误差，应在报告说明计量口径。不要执行系统清理来美化结果，不要删除正在使用的 WAL/DB；归档/删除旧运行需另行明确操作范围。
