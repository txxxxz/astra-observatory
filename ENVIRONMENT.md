# 考前开发环境

检查日期：2026-11-05。此目录仅用于通用环境准备，不作为正式考试答题仓库。

## 使用

```bash
conda activate dev
python --version
docker version
docker compose version
```

Python 环境：`/opt/miniconda3/envs/dev`。已有 Python 3.12.13、SQLite 3.51.2、pip、venv、pytest、ruff、requests、httpx、FastAPI 和 uvicorn；`pip check` 通过。无需为了考前准备升级现有业务依赖。

Docker Desktop 4.97.0 安装于 `/Applications/Docker.app`，Docker CLI 29.9.2 及凭据助手链接于 `dev/bin`。使用手动应用安装方式，未通过 Homebrew 管理。Docker 引擎为 Linux/ARM64，Compose v5.6.1 可用。

已拉取官方 `python:3.12-slim` 镜像，安装时 digest：`sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30`。

## 已验证

- 从 dev 的 Python 创建独立临时虚拟环境，并通过 pip 从包源安装 packaging。
- Python SQLite 建表、插入和查询。
- 现有 Python 开发包导入及依赖一致性。
- GitHub CLI 登录账号 `txxxxz`，Git 通过 HTTPS 读取远程仓库。
- Git 在独立临时目录完成本地 commit。
- 官方 Python Linux 容器成功运行，容器内 SQLite 和 venv 可用，挂载目录的读取、写入及主机侧结果核对通过。
- Git 全局提交身份设为 `Chendi Zhou <134213743+txxxxz@users.noreply.github.com>`，并配置 gh 凭据助手。
- 新建本地 Git 仓库默认分支已设为 `main`。
- GitHub 公开测试仓库已成功创建、HTTPS 推送及全新克隆；默认分支为 `main`，本地与远端 commit SHA 一致。
  - 测试仓库：https://github.com/txxxxz/github-env-check-20261105-022727
  - 验证 commit：`83ddfced13ade28edc193aefddcb7e090d3111c2`
  - 仓库仅含环境测试 README，不能作为考试答题仓库。

## 考前还需确认

- 摄像头、麦克风权限需要在考试所用浏览器与平台内确认。
- 正式开考计时后，另建全新目录和 GitHub public repo，不复用本目录 `.git` 或临时测试仓库历史。
- 最终推送到默认分支后，还需在考试平台独立点击“交卷”并确认成功。
