# ASTRA 宇宙万物观测站

ASTRA 将题目发生器持续推送的异构观测可靠保存，支持分类演化、对象检索、交互星空、完整详情和 NDJSON 流式导出。技术栈为 **FastAPI + SQLite WAL/FULL + React/TypeScript + Three.js**；运行时一个应用容器，发生器独立运行。

[源码仓库](https://github.com/txxxxz/astra-observatory) · [协议与应用详细说明](observatory/README.md)

![ASTRA 星空探索](observatory/evidence/screenshots/fullscreen-stars.jpg)

## 1. 从仓库启动

需要 Git、Python 3.12+、支持 **Linux arm64** 容器的 Docker Engine / Docker Desktop 和 Docker Compose。首次构建与准备发生器需要联网；应用运行不依赖外部模型或 API。浏览器不计入后台资源。

```bash
git clone https://github.com/txxxxz/astra-observatory.git
cd astra-observatory
cd observatory

# 下载公开题包，验证发生器镜像 tar 的 SHA-256，再导入 Docker
python3 scripts/prepare_generator.py

# 同时启动应用与独立发生器
docker compose --profile generator up -d --build

# 期望 status=ok、SQLite=3.51.3、journal_mode=wal、synchronous_name=FULL
curl -fsS http://127.0.0.1:8000/api/health
```

已有题包时，第一步可改为 `python3 scripts/prepare_generator.py --image-tar /absolute/path/flightgen-image.tar`，或使用 `--archive /absolute/path/candidate-package.zip`。

打开 [观测站](http://127.0.0.1:8000/)；[API 文档](http://127.0.0.1:8000/docs) 同源提供。应用端口默认 8000、发生器端口 9001，均只监听 localhost。端口冲突时可设置 `OBS_PORT` / `GENERATOR_PORT`；对应脚本的 `--base-url` / `--generator-url` 也需要匹配。

## 2. 使用系统与接入数据

**应用被动接收 `/ingest` POST；打开网页不会自动启动发生器。** 新安装没有历史数据库，可先重放仓库中的真实协议样本：

```bash
# 仍在 observatory/ 目录；这一命令无需启动发生器负载
python3 scripts/replay_samples.py --output evidence/sample-replay-local.json
```

首次重放期望得到 `attachment-probe-001` 运行、2,080 个有效对象、分类 revision 11、4 次重复与2条整批隔离。再次执行是幂等重试，会显示重复；可用 `--test-id sample-new-001` 创建独立运行。样本用于协议/正确性验证，不作为性能结果。

体验持续输入和查询，可运行：

```bash
# 目标每秒500对象，持续60秒；同时浏览、读详情与流式导出
python3 scripts/benchmark.py --rates 500 --seconds 60 --readers 2 \
  --containers astra-observatory-app-1 astra-observatory-generator-1
```

脚本自动生成独立 `test_id`，报告保存到 `evidence/benchmarks/`。同一时间只运行一个发生器任务。也可直接调用发生器 `/start`、`/status`、`/receipt`；完整请求见 [接入操作](observatory/README.md#先体验再接入新数据)。

界面操作路径：

1. 顶部选择运行和坐标框架；不同 `frame_id / frame_kind / unit` 不混绘。
2. 默认显示铺满视口的星空；拖动旋转、滚轮缩放，点击星点读取对应对象。
3. 底部“分类 / 目录 / 详情 / 状态”按需展开。目录支持分类及后代、名称前缀、对象 ID、分页和导出；无坐标对象也可浏览。
4. “聚焦此对象”拉近镜头，随后变为“回到原处”；返回时恢复此前视角，详情卡保持展开。
5. 持续写入时统计自动更新，点击“全站新增”提示更新星空与目录，避免正在阅读的列表不断跳动。

星空采用空间压缩、纵深调整和随视口展开的**展示坐标**，保持每个点的对象身份；它不是按真实比例绘制的天文星图。详情与导出仍使用原始 XYZ。色彩、光晕及背景星云是视觉表现，不代表测得的温度、亮度或新增观测。

## 3. 运行与验收

以下命令均在 `observatory/` 执行：

```bash
# 自动化正确性测试（无需运行发生器）
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
PYTHONPATH=. pytest tests -q

# 两档真实混合压力：持续写入 + 查询 + 导出
python3 scripts/benchmark.py --rates 500 3000 --seconds 60 --readers 2 \
  --containers astra-observatory-app-1 astra-observatory-generator-1

# 在发生器已停止后执行：SIGKILL应用，再逐项核对已确认数据
python3 scripts/verify_recovery.py
```

判定依据：测试通过；样本重放状态符合预期；混合负载报告 `errors` 为空、最终导出条数与对象数一致；恢复脚本确认已获 ACK 的消息及对象在重启后仍存在。压测同时报告目标速率、实测确认/入库速率、查询 p50/p95/p99、失败计数、导出首条/完整耗时与资源采样，不能仅用设定速率判断性能。

手动验收分类筛选、目录翻页、星点选择、聚焦/返回、原始属性、坐标框架切换和 NDJSON 下载。前端构建与布局测试：

```bash
cd frontend
npm ci
node --test tests/starLayout.test.mjs
npm run build
cd ..
```

布局测试覆盖599/3,000点在宽窄屏比例下的投影边界、密度、原始数据不变以及空/单点。生产运行由应用容器提供构建产物。

## 4. 实际测试结果

以下结果均来自 **2026-11-05 的真实题包发生器**，不是手工生成的吞吐数字。历史三档使用一个浏览客户端，在写入同时进行分页、详情、指标与导出；目标速率与确认/入库分别计量。

| 目标对象/秒 | 时长 | 实际确认/秒 | 有效入库对象数 | 列表 p95 | 详情 p95 | 最终导出 | 应用峰值内存 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 500 | 60 s | 464.97 | 27,900 | 9.03 ms | 5.27 ms | 0.275 s | 51.55 MiB |
| 3,000 | 60 s | 1,734.96 | 104,200 | 13.77 ms | 7.90 ms | 1.111 s | 77.90 MiB |
| 10,000 | 120 s | 2,804.14 | 336,600 | 17.62 ms | 13.87 ms | 4.148 s | 169.40 MiB |

三档共入库 **468,700** 个对象，查询/导出探针0错误，最终导出计数全部匹配。最高档有效入库约2,805对象/秒，没有达到10,000目标，未证明系统吞吐上限。第二、三档各有100个对象在发生器到时停止时已提交、响应中断，因此总确认468,500与入库468,700不同；4,685个已确认批次逐项对账通过。

新版压测增加了点云、分类、坐标框架、后代筛选与更多并发客户端。**20秒短测**使用两个浏览客户端：入库8,300对象、实际确认414.95对象/秒，列表p95 12.03ms、点云p95 9.96ms，3次并发导出，最终数量匹配，报告0错误。此轮用于验证新增探针，不与旧负载直接比较，也不宣称吞吐提升。

正确性测试当前 **37项通过**（原33项后端测试加4项压测脚本测试），另有**3项前端布局测试通过**；原33项曾在修复版SQLite的arm64镜像内复验。SIGKILL恢复验证通过；新只读根文件系统部署后121条样本重放均识别为重复。

| 证据 | 内容 |
|---|---|
| [测试摘要](observatory/evidence/benchmark-summary.json) / [详细压测报告](observatory/docs/benchmark.md) | 历史三档原始结果与统计口径 |
| [ACK对账](observatory/evidence/receipt-audit.json) / [恢复证据](observatory/evidence/recovery.json) | 已确认消息核对、进程崩溃恢复 |
| [20秒新探针报告](observatory/evidence/benchmarks/visual-recheck-500-20261105T035451Z-0.json) | 新版混合查询/导出烟测 |
| [资源与视觉复验](observatory/docs/visual-resource-recheck.md) | 容器限制、只读根、交互验证 |
| [压测优化分析](observatory/docs/performance-review.md) | 后续对照实验、测量范围和候选瓶颈 |

## 5. 关键取舍与资源约束

| 取舍 | 实现与原因 |
|---|---|
| 一个后台应用 + SQLite | 减少组件在4CPU/4GiB中的竞争；单写通道、有界并发，WAL支持读写并行 |
| 事务提交后返回2xx | 原始消息、业务投影和处理状态原子保存；不靠内存队列提前确认换取吞吐 |
| 完整保留JSON + 索引字段 | 陌生属性不丢失，常用分类/身份/名称/坐标查询可索引 |
| 有界可视化与流式导出 | 界面默认最多3,000点；目录分页、详情按需；完整结果逐块输出 |
| 展示布局与原始坐标分离 | 星空优先探索体验，原始XYZ在详情与导出中保留 |

应用容器限制 **4 vCPU / 4 GiB**，独立发生器 **1 vCPU / 256 MiB**，均无额外swap；实际配置见 [compose.yaml](observatory/compose.yaml) 与 [运行核查](observatory/evidence/runtime-budget-recheck.json)。应用根文件系统只读，`/tmp`为64MiB tmpfs（计入内存）。

**20 GiB是整体磁盘预算，当前数据目录使用18 GiB软水位。** DB、WAL、SHM和应用日志一起计数，接近水位时拒绝新接入；剩余预算用于镜像、日志及事务余量。Docker日志轮转。普通named volume没有硬配额：若验收平台要求严格物理上限，还需使用平台提供的受限文件系统/配额卷，并核算镜像和Docker日志。应用不会自动删除历史数据。

## 6. 已知限制

- 分类revision缺口、同ID不同内容的未知更新语义会明确隔离，不猜测修复或默默覆盖。可靠保存的隔离消息可以返回2xx，但不会计作有效对象入库。
- 点云为最早匹配的有界样本，非全量随机采样；展示坐标经过调整，不可用屏幕距离代替真实空间距离。
- SQLite为单写设计；现有压力测试没有填满20GiB，没有证明百万对象、长时间稳态或最大吞吐。下一步优先对照批量大小、并发导出开关和浏览人数，再决定后端优化。
- 进程崩溃恢复测试不等于宿主断电保证；普通Docker volume不提供20GiB硬容量保证。
- 未实现账号系统、云部署、历史回放、任意JSON全文搜索。服务默认限本机访问。
- 源码仓库不包含发生器镜像、观测数据库和运行数据卷。题包可通过准备脚本下载并校验。

## 7. 停止与保留数据

```bash
# 若发生器仍在运行，先停止并等待 /status 返回 finished
curl -fsS -X POST http://127.0.0.1:9001/stop
# 保留数据卷；不加 -v
docker compose --profile generator down
```

常规停止保留命名数据卷；再次启动后可继续浏览已有运行。`docker compose down -v` 会删除数据卷与观测数据，不用于日常停止。
