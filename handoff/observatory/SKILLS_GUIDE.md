# 本地技能选择（2026-11-05 检查）

已检查下面的 SKILL.md 文件。这里是为 Astra 选择执行技能，不代表本轮已经执行了这些技能的开发/测试流程。是否能调用对应工具，还要以 Astra 所在会话为准。

## 建议按阶段用

| 技能 | 用途 | 使用时机 |
| --- | --- | --- |
| build-web-apps:react-best-practices | 避免轮询重复请求、整页重渲染、无界列表与包体积问题 | React 实现和检查 |
| build-web-apps:frontend-testing-debugging | 实际浏览器验证页面、console、交互、截图和窄屏 | 核心界面完成后 |
| playwright | 通过 CLI 操作真实浏览器，检查界面流程 | 缺少合适内置浏览器时的备选；和上一个技能协调，避免重复测试 |
| systematic-debugging | 先复现和定位，再最小修改 | 接入、Docker、数据库、UI 失败时 |
| verification-before-completion | 用真实测试/构建输出支持完成结论 | 提交与最终汇报前 |
| build-web-data-visualization:data-visualization | 图表语义、坐标、采样、缺失数据与可视化选择 | 可视化设计遇到具体问题时按需使用 |

绝对路径：

- React：`/Users/zhouchendi/.codex/plugins/cache/openai-curated-remote/build-web-apps/0.1.2/skills/react-best-practices/SKILL.md`
- 前端测试：`/Users/zhouchendi/.codex/plugins/cache/openai-curated-remote/build-web-apps/0.1.2/skills/frontend-testing-debugging/SKILL.md`
- Playwright：`/Users/zhouchendi/.codex/skills/playwright/SKILL.md`
- 故障定位：`/Users/zhouchendi/Documents/ChatGPT/aicoding/.agents/skills/systematic-debugging/SKILL.md`
- 交付验证：`/Users/zhouchendi/Documents/ChatGPT/aicoding/.agents/skills/verification-before-completion/SKILL.md`
- 可视化：`/Users/zhouchendi/.codex/plugins/cache/openai-curated-remote/build-web-data-visualization/0.1.21/skills/data-visualization/SKILL.md`

已确认本机存在 `/opt/homebrew/bin/npx` 和可执行 Playwright wrapper：`/Users/zhouchendi/.codex/skills/playwright/scripts/playwright_cli.sh`。本轮未启动浏览器，未验证 CLI 依赖或浏览器二进制；存在技能不等于运行时已经就绪。

## 可用但不建议默认启动的流程

`build-web-apps:frontend-app-builder`：文件存在，已检查关键规则。默认要求 Image Gen 完整概念图，并持续对照视觉效果，交付前有图片比对要求。这不是本题两小时内的优先工作。主提示词明确选择代码原生 UI、不要生成概念图；如确实调用该技能，应按明确用户范围处理其允许的例外，不要假称完成了未执行的设计流程。

路径：`/Users/zhouchendi/.codex/plugins/cache/openai-curated-remote/build-web-apps/0.1.2/skills/frontend-app-builder/SKILL.md`

`data-visualization` 是路由技能，不是即插即用图表组件；高级视觉流程也可能引入概念图、审批和额外专业技能。只在实际需要时读取适用部分，避免扩展为大型可视化工程。

项目还安装有 writing-plans、executing-plans、requesting-code-review、subagent-driven-development、test-driven-development、using-git-worktrees 等技能；本轮只核实其文件/描述，不宣称已审核完整流程。基础目录为 `/Users/zhouchendi/Documents/ChatGPT/aicoding/.agents/skills/`。不需要为了“用技能”把所有流程串起来。是否使用多代理、工作树等按当前用户授权、仓库规则和任务实际需要决定。

这次检查的相关技能中，没有发现专门替代 SQLite 接入语义设计或 Docker 故障恢复验证的现成技能。它们仍需要具体实现和测试。没有必要引入 Supabase、Vercel、OpenEnv、云部署或模型 API。
