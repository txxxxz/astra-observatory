# 容器与真实负载验证

2026-11-05，Mac Docker Desktop，Linux arm64。以下数字来自真实题包发生器；设定速率与实测速率分别列出。

## 运行环境

- Python 3.12.16；SQLite 3.51.3，实际 `journal_mode=wal`、`synchronous=FULL`。
- 应用单容器：4 vCPU、4 GiB（含 swap 总额4 GiB）；发生器：1 vCPU、256 MiB（含 swap 总额256 MiB）。实际 Docker inspect 参数见 [runtime.json](../evidence/runtime.json)。
- SQLite 3.51.3 源码按官方 SHA3-256 校验后编译；构建再次断言 Python 实际链接版本。该版本包含 [WAL-reset 修复](https://www.sqlite.org/wal.html#walreset)。
- Python 完整运行依赖锁在 `backend/requirements.lock`；Node/Python 基础镜像固定 digest，前端使用 `npm ci`。首次构建需联网下载构建依赖；运行不依赖外部 API。
- 应用持久化软水位19 GiB；Docker stdout日志最多30 MiB。Compose volume 不提供20 GiB硬配额，应使用本机配额/监控保证物理预算；默认不删除数据。

## 正确性与可恢复性

- [arm64 后端测试日志](../evidence/docker-backend-tests.log)：实际运行最新完整测试目录；涵盖事务隔离、重复/冲突、分类演化、跨运行隔离、未知属性、请求和导出边界。
- [HTTP 原始样本重放](../evidence/sample-replay.json)：121条请求，115条应用成功、4条重复、2条整体隔离；正常对象2080个，分类revision11。样本重放不是吞吐测试。
- 发生器[本地tar验证](../evidence/generator-image.json)与[公开题包下载验证](../evidence/generator-download.json)均通过相同 SHA256 和 linux/arm64 架构检查。
- [SIGKILL 恢复验证](../evidence/recovery.json)：21条已确认消息的状态、内容哈希和原始JSON全部一致；20个对象逐字段一致，重试返回duplicate。此项验证容器进程崩溃恢复，不等价于宿主断电测试。
- [崩溃后数据库结构检查](../evidence/sqlite-integrity.json)：SQLite quick_check=[['ok']]，耗时0.61s。
- [ACK位图逐批核对](../evidence/receipt-audit.json)：4685个已确认批次与数据库状态、有效对象数逐项核对；结果passed。
- `mixed-10000-20261105T031349Z-0`存在已提交但未被发送端确认的批次3365；收据同时记录1次结束时请求中断。故数据库对象数可能大于ACK对象数；这类批次重试仍保持幂等。
- `mixed-3000-20261105T031202Z-1`存在已提交但未被发送端确认的批次1041；收据同时记录1次结束时请求中断。故数据库对象数可能大于ACK对象数；这类批次重试仍保持幂等。

## 持续写入 + 查询 + 导出

每档为独立 test_id；batch_size=100、workers=4、evolving、bursty、5秒爬升；一条分页/详情探针每轮间隔150ms，指标每2秒读取，独立线程每8秒发起一次全量NDJSON流式导出。两端资源每约3秒采样。导出/查询探针在宿主运行，不计入后台容器资源。

| 目标对象/s | 发生器时长 | 实际确认对象/s | 实际有效对象/s | 有效对象 | 分页p95 | 详情p95 | 并发导出次数 | 探针错误 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 500 | 60.00s | 464.97 | 464.97 | 27,900 | 9.03ms | 5.27ms | 7 | 0 |
| 3000 | 60.00s | 1734.96 | 1736.63 | 104,200 | 13.77ms | 7.90ms | 7 | 0 |
| 10000 | 120.00s | 2804.14 | 2804.98 | 336,600 | 17.62ms | 13.87ms | 12 | 0 |

| 目标对象/s | 应用CPU采样最大 | 应用内存采样最大 | 发生器CPU采样最大 | 发生器内存采样最大 | 该档存储增长 | 停流后完整导出 | 导出与对象数一致 |
|---:|---:|---:|---:|---:|---:|---:|:---:|
| 500 | 18.1% | 51.5 MiB | 0.4% | 21.1 MiB | 100.5 MiB | 27,900条 / 0.27s | 是 |
| 3000 | 47.5% | 77.9 MiB | 2.2% | 25.0 MiB | 396.1 MiB | 104,200条 / 1.11s | 是 |
| 10000 | 109.6% | 169.4 MiB | 2.0% | 28.9 MiB | 1294.5 MiB | 336,600条 / 4.15s | 是 |

实际确认速率采用发生器主流 `acknowledged_objects / elapsed_seconds`；重复和故障注入另见receipt中的injections。有效对象速率采用数据库对象数/同一发生器时长。异常整批保存后隔离，因此可靠接收与有效业务入库口径分别保留。

本系统同步事务完成后才确认，没有确认后的异步处理队列；未完成请求由发生器in_flight/timeout/error统计反映。每份报告包含全过程指标、所有探针错误、流式导出条数/字节/耗时及hash、Docker采样、完整发生器收据。

采样CPU最大值不等于全程平均或硬件峰值，内存也是采样最大值。这些短时实验没有填满20 GiB，也不声称无限持续负载或最大吞吐上限。额外浏览器验收可能与运行中的只读探针并行。

原始报告：

- [mixed-500-20261105T031101Z-0](../evidence/benchmarks/mixed-500-20261105T031101Z-0.json.gz)：finish_reason=duration；主流HTTP429=0、5xx=0、timeouts=0、重试=0；隔离消息=4，消息冲突=0。
- [mixed-3000-20261105T031202Z-1](../evidence/benchmarks/mixed-3000-20261105T031202Z-1.json.gz)：finish_reason=duration；主流HTTP429=0、5xx=0、timeouts=0、重试=0；隔离消息=15，消息冲突=0。
- [mixed-10000-20261105T031349Z-0](../evidence/benchmarks/mixed-10000-20261105T031349Z-0.json.gz)：finish_reason=duration；主流HTTP429=0、5xx=0、timeouts=0、重试=0；隔离消息=49，消息冲突=0。

## 复现

```sh
python3 scripts/prepare_generator.py
docker compose --profile generator up --build -d
python3 scripts/replay_samples.py --output evidence/sample-replay.json
python3 scripts/benchmark.py --rates 500 3000 --seconds 60 --containers astra-observatory-app-1 astra-observatory-generator-1
python3 scripts/benchmark.py --rates 10000 --seconds 120 --containers astra-observatory-app-1 astra-observatory-generator-1
python3 scripts/verify_recovery.py
python3 scripts/audit_receipts.py
python3 scripts/summarize_evidence.py
```

恢复脚本会SIGKILL并重启本项目app容器，保留volume；请在无正在运行发生器测试时执行。重复执行样本重放会得到幂等重复响应；可使用`--test-id`创建新的隔离样本运行。
