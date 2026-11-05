# 项目 Skills

安装位置：`.agents/skills/`，仅用于当前项目。安装日期：2026-11-04。

工作顺序：`grill-me` 对齐想法 → `writing-plans` 固定任务 → `executing-plans` 推进 → `verification-before-completion` 验收 → `ce-compound` 沉淀经验。

在 Codex 中可用 `$grill-me`、`$writing-plans` 等名称明确调用。这是推荐调用顺序，安装本身不会自动运行整条流程。

## 来源与固定版本

| 上游 | Commit | 安装内容 |
| --- | --- | --- |
| [mattpocock/skills](https://github.com/mattpocock/skills) | `4ae2317ddb22b046e26455e4f9c9b3aaaf62212d` | `grill-me`、其依赖 `grilling` |
| [obra/superpowers](https://github.com/obra/superpowers) | `22f0b463e7a5e579904dd6211a520321035526f7` | `writing-plans`、`executing-plans`、`verification-before-completion` |
| [EveryInc/compound-engineering-plugin](https://github.com/EveryInc/compound-engineering-plugin) | `a3bcedfc7136d5db2262c8339e514b6fb15b8f81` | `ce-compound`，包含其 references、assets 和 scripts |

Superpowers 辅助依赖使用相同 commit：`subagent-driven-development`、`using-git-worktrees`、`test-driven-development`、`systematic-debugging`、`requesting-code-review`、`finishing-a-development-branch`、`using-superpowers`。其中共享脚本由 `executing-plans` 直接引用。

保留上游 skill 内容；补回下载 ZIP 未保留的 Bash 脚本可执行权限。
