#!/usr/bin/env python3
"""Create a concise, source-linked report from the actual saved test evidence."""

import argparse
import gzip
import json
import pathlib
import re


def memory_mib(value):
    number, unit = re.fullmatch(r"([\d.]+)([A-Za-z]+)", value.strip()).groups()
    factor = {
        "B": 1 / 1024**2,
        "KiB": 1 / 1024,
        "MiB": 1,
        "GiB": 1024,
        "kB": 1000 / 1024**2,
        "MB": 1000**2 / 1024**2,
        "GB": 1000**3 / 1024**2,
    }[unit]
    return float(number) * factor


def maxima(report, name):
    samples = [
        c
        for s in report["resource_samples"]
        for c in s["containers"]
        if c["Name"] == name
    ]
    if not samples:
        return "未采集", "未采集"
    return (
        f"{max(float(c['CPUPerc'].rstrip('%')) for c in samples):.1f}%",
        f"{max(memory_mib(c['MemUsage'].split('/')[0]) for c in samples):.1f} MiB",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args()
    root = args.root
    reports = [
        (
            p,
            json.loads(
                gzip.decompress(p.read_bytes()) if p.suffix == ".gz" else p.read_bytes()
            ),
        )
        for p in sorted((root / "evidence/benchmarks").glob("*.json*"))
        if not (p.suffix == ".gz" and p.with_suffix("").exists())
    ]
    reports.sort(key=lambda pair: pair[1]["started_at_utc"])
    runtime = json.loads((root / "evidence/runtime.json").read_text())
    text = [
        "# 容器与真实负载验证",
        "",
        "2026-11-05，Mac Docker Desktop，Linux arm64。以下数字来自真实题包发生器；设定速率与实测速率分别列出。",
        "",
        "## 运行环境",
        "",
        f"- Python {runtime['runtime']['python'].split()[0]}；SQLite {runtime['runtime']['sqlite']}，实际 `journal_mode=wal`、`synchronous=FULL`。",
        "- 应用单容器：4 vCPU、4 GiB（含 swap 总额4 GiB）；发生器：1 vCPU、256 MiB（含 swap 总额256 MiB）。实际 Docker inspect 参数见 [runtime.json](../evidence/runtime.json)。",
        "- SQLite 3.51.3 源码按官方 SHA3-256 校验后编译；构建再次断言 Python 实际链接版本。该版本包含 [WAL-reset 修复](https://www.sqlite.org/wal.html#walreset)。",
        "- Python 完整运行依赖锁在 `backend/requirements.lock`；Node/Python 基础镜像固定 digest，前端使用 `npm ci`。首次构建需联网下载构建依赖；运行不依赖外部 API。",
        "- 应用持久化软水位19 GiB；Docker stdout日志最多30 MiB。Compose volume 不提供20 GiB硬配额，应使用本机配额/监控保证物理预算；默认不删除数据。",
        "",
        "## 正确性与可恢复性",
        "",
        "- [arm64 后端测试日志](../evidence/docker-backend-tests.log)：实际运行最新完整测试目录；涵盖事务隔离、重复/冲突、分类演化、跨运行隔离、未知属性、请求和导出边界。",
        "- [HTTP 原始样本重放](../evidence/sample-replay.json)：121条请求，115条应用成功、4条重复、2条整体隔离；正常对象2080个，分类revision11。样本重放不是吞吐测试。",
        "- 发生器[本地tar验证](../evidence/generator-image.json)与[公开题包下载验证](../evidence/generator-download.json)均通过相同 SHA256 和 linux/arm64 架构检查。",
    ]
    recovery = root / "evidence/recovery.json"
    if recovery.exists():
        r = json.loads(recovery.read_text())
        text.append(
            f"- [SIGKILL 恢复验证](../evidence/recovery.json)：{r['acknowledged_messages']}条已确认消息的状态、内容哈希和原始JSON全部一致；{r['objects_checked_field_by_field']}个对象逐字段一致，重试返回duplicate。此项验证容器进程崩溃恢复，不等价于宿主断电测试。"
        )
    integrity_path = root / "evidence/sqlite-integrity.json"
    if integrity_path.exists():
        integrity = json.loads(integrity_path.read_text())
        text.append(
            f"- [崩溃后数据库结构检查](../evidence/sqlite-integrity.json)：SQLite quick_check={integrity['sqlite_quick_check']}，耗时{integrity['seconds']:.2f}s。"
        )
    audit_path = root / "evidence/receipt-audit.json"
    if audit_path.exists():
        audit = json.loads(audit_path.read_text())
        acknowledged = sum(item["ack_bitmap_batches"] for item in audit["runs"])
        text.append(
            f"- [ACK位图逐批核对](../evidence/receipt-audit.json)：{acknowledged}个已确认批次与数据库状态、有效对象数逐项核对；结果{audit['status']}。"
        )
        for item in audit["runs"]:
            if item["committed_unacknowledged_batches"]:
                batches = ", ".join(
                    str(v["batch_id"]) for v in item["committed_unacknowledged_batches"]
                )
                text.append(
                    f"- `{item['test_id']}`存在已提交但未被发送端确认的批次{batches}；收据同时记录{item['interrupted_requests']}次结束时请求中断。故数据库对象数可能大于ACK对象数；这类批次重试仍保持幂等。"
                )
    text += [
        "",
        "## 持续写入 + 查询 + 导出",
        "",
        "每档为独立 test_id；batch_size=100、workers=4、evolving、bursty、5秒爬升；一条分页/详情探针每轮间隔150ms，指标每2秒读取，独立线程每8秒发起一次全量NDJSON流式导出。两端资源每约3秒采样。导出/查询探针在宿主运行，不计入后台容器资源。",
        "",
        "| 目标对象/s | 发生器时长 | 实际确认对象/s | 实际有效对象/s | 有效对象 | 分页p95 | 详情p95 | 并发导出次数 | 探针错误 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, d in reports:
        text.append(
            f"| {d['config']['objects_per_second']} | {d['generator_elapsed_seconds']:.2f}s | {d['generator_acknowledged_objects_per_second']:.2f} | {d['applied_objects_per_generator_second']:.2f} | {d['final_metrics']['object_count']:,} | {d['query_latency']['list']['p95_ms']:.2f}ms | {d['query_latency']['detail']['p95_ms']:.2f}ms | {len(d['concurrent_exports'])} | {len(d['errors'])} |"
        )
    text += [
        "",
        "| 目标对象/s | 应用CPU采样最大 | 应用内存采样最大 | 发生器CPU采样最大 | 发生器内存采样最大 | 该档存储增长 | 停流后完整导出 | 导出与对象数一致 |",
        "|---:|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for _, d in reports:
        ac, am = maxima(d, "astra-observatory-app-1")
        gc, gm = maxima(d, "astra-observatory-generator-1")
        growth = (
            d["final_metrics"]["database_bytes"] - d["health"]["storage_bytes"]
        ) / 1024**2
        text.append(
            f"| {d['config']['objects_per_second']} | {ac} | {am} | {gc} | {gm} | {growth:.1f} MiB | {d['final_export']['count']:,}条 / {d['final_export']['duration_ms'] / 1000:.2f}s | {'是' if d['final_export_count_matches'] else '否'} |"
        )
    text += [
        "",
        "实际确认速率采用发生器主流 `acknowledged_objects / elapsed_seconds`；重复和故障注入另见receipt中的injections。有效对象速率采用数据库对象数/同一发生器时长。异常整批保存后隔离，因此可靠接收与有效业务入库口径分别保留。",
        "",
        "本系统同步事务完成后才确认，没有确认后的异步处理队列；未完成请求由发生器in_flight/timeout/error统计反映。每份报告包含全过程指标、所有探针错误、流式导出条数/字节/耗时及hash、Docker采样、完整发生器收据。",
        "",
        "采样CPU最大值不等于全程平均或硬件峰值，内存也是采样最大值。这些短时实验没有填满20 GiB，也不声称无限持续负载或最大吞吐上限。额外浏览器验收可能与运行中的只读探针并行。",
        "",
        "原始报告：",
        "",
    ]
    for p, d in reports:
        stats = d["receipt"]["stats"]
        text.append(
            f"- [{d['test_id']}](../evidence/benchmarks/{p.name})：finish_reason={stats.get('finish_reason')}；主流HTTP429={stats.get('http_429')}、5xx={stats.get('http_5xx')}、timeouts={stats.get('timeouts')}、重试={stats.get('retries')}；隔离消息={d['final_metrics']['quarantined_count']}，消息冲突={d['final_metrics']['conflict_count']}。"
        )
    text += [
        "",
        "## 复现",
        "",
        "```sh",
        "python3 scripts/prepare_generator.py",
        "docker compose --profile generator up --build -d",
        "python3 scripts/replay_samples.py --output evidence/sample-replay.json",
        "python3 scripts/benchmark.py --rates 500 3000 --seconds 60 --containers astra-observatory-app-1 astra-observatory-generator-1",
        "python3 scripts/benchmark.py --rates 10000 --seconds 120 --containers astra-observatory-app-1 astra-observatory-generator-1",
        "python3 scripts/verify_recovery.py",
        "python3 scripts/audit_receipts.py",
        "python3 scripts/summarize_evidence.py",
        "```",
        "",
        "恢复脚本会SIGKILL并重启本项目app容器，保留volume；请在无正在运行发生器测试时执行。重复执行样本重放会得到幂等重复响应；可使用`--test-id`创建新的隔离样本运行。",
    ]
    path = root / "docs/deployment-report.md"
    path.write_text("\n".join(text) + "\n")
    print(path)


if __name__ == "__main__":
    main()
