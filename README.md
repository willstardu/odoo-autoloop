# odoo-autoloop

Odoo 19 自动编程 + 自动测试流水线：GLM-5.2 写代码 → Playwright 确定性 E2E 测试 → 本地 Qwen 诊断失败 → GLM 修复（Git worktree 隔离）→ 循环。

> 完整部署文档见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

## 架构

```
本机 Windows (192.168.108.99)
├── run.py                    主编排器（worktree 隔离版）
├── tests/e2e_odoo.py         Playwright E2E 测试（登录 + OmniPod 全菜单）
├── tests/menu_map.json       OmniPod 菜单 action URL 映射
├── src/nodes/                 Qwen 诊断 / GLM 修复 节点
├── src/utils/                 SFTP 同步 / Git worktree 工具
└── workspace/                 baselife_stock 源码（Git 管理）

模型：
├── GLM-5.2 (TokenHub API)     编码/修复
├── Qwen2.5VL (192.168.108.143:11434)  诊断（文本+截图）
└── Odoo 19 (192.168.108.134:8069, db=odoo19_test)  测试目标
```

## 快速开始

```powershell
# 1. 安装依赖
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
.venv\Scripts\playwright install chromium

# 2. 配置 .env（参考 .env.example，GLM_API_KEY / ODOO_PASSWORD 必填）
Copy-Item .env.example .env

# 3. 同步模块源码（首次）
$env:PYTHONPATH = "$PWD"
.venv\Scripts\python.exe src\utils\sftp_tool.py pull
git -C workspace\baselife_stock init; git -C workspace\baselife_stock add -A; git -C workspace\baselife_stock commit -m "baseline"

# 4. 运行
.venv\Scripts\python.exe run.py
```

## 功能

- **E2E 测试**：登录 Odoo → 遍历 OmniPod 11 个子页面（action URL 直达，比下拉点击稳定）
- **失败诊断**：Qwen2.5VL 分析日志/截图/DOM，输出结构化 JSON 根因
- **自动修复**：GLM 在 Git worktree 中生成补丁 → SFTP 推送 → 重启 Odoo → 重测
- **worktree 隔离**：修复不污染主工作区，通过后才合并
- **定时任务**：`schedule_task.ps1`（每天自动回归）
- **CI**：`.github/workflows/autotest.yml`（需自托管 runner）

## 文档

- [部署文档（含 GitHub 仓库创建与推送）](docs/DEPLOYMENT.md)
- [.env 配置模板](.env.example)
