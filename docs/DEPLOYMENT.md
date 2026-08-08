# Odoo 19 自动编程 + 自动测试流水线 部署文档

> 编码用 GLM-5.2（云端 API），测试用 Playwright（确定性 E2E），失败诊断用本地 Qwen2.5VL（Ollama）。
> GLM 修复在 Git worktree 中隔离进行，测试通过后合并回主分支。

---

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│  本机 Windows 11  (192.168.108.99)                              │
│                                                                 │
│  odoo-autoloop/         编排器 + 测试 + 修复                     │
│  ├── run.py            主编排器（worktree 隔离版）                │
│  ├── tests/e2e_odoo.py Playwright E2E                            │
│  ├── src/nodes/         Qwen 诊断 / GLM 修复 节点                │
│  ├── src/utils/         SFTP 同步 / Git worktree 工具             │
│  └── workspace/         baselife_stock 源码（Git 管理）           │
│                                                                 │
│  OpenCode + GLM-5.2 (TokenHub API)    云端编码模型               │
│  Playwright (Chromium)                 确定性 E2E 测试           │
└────────────────────────────┬────────────────────────────────────┘
                             │ 局域网
┌────────────────────────────┴────────────────────────────────────┐
│  Ubuntu 192.168.108.134                                        │
│  ├── Odoo 19 (Community) :8069  db=odoo19_test                 │
│  └── /opt/custom-addons/baselife_stock   OmniPod 备件库模块      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  192.168.108.143  (Win11, RTX 4080 32G)                        │
│  └── Ollama :11434  qwen2.5vl-tools:latest (33.5B Q4_K_M)       │
│      视觉+工具调用，用于失败诊断                                  │
└─────────────────────────────────────────────────────────────────┘
```

**核心原则：**
- **断言确定性**：Playwright 用固定脚本/固定 action URL 做断言，结果可复现
- **推理交给 LLM**：仅失败时把日志/截图/DOM 交给 Qwen 诊断；GLM 只按结构化诊断修复
- **worktree 隔离**：GLM 修复永不直接改主工作区，合并前可回滚

---

## 2. 前置条件

| 资源 | 地址 | 说明 |
|---|---|---|
| Odoo 19 | `http://192.168.108.134:8069` | 测试库 `odoo19_test`，账号 `admin` |
| Ollama | `http://192.168.108.143:11434` | 模型 `qwen2.5vl-tools:latest` |
| GLM-5.2 API | `https://api.tokenhub.market/v1` | API Key（OpenAI 兼容） |
| 本机 | Win11，Git ≥2.53，Node ≥20，Python 3.12 | 运行编排器 |

网络要求：
- 本机可访问 `192.168.108.134:8069`（Odoo）
- 本机可访问 `192.168.108.143:11434`（Ollama）
- 本机可访问 Ubuntu SSH（`root@192.168.108.134:22`）

---

## 3. 部署步骤（全新机器）

### 3.1 安装依赖

```powershell
# Python 3.12（https://www.python.org/downloads/，勾选 Add to PATH）

# 克隆本项目
git clone https://github.com/willstardu/odoo-autoloop.git
cd odoo-autoloop

# 虚拟环境 + 依赖（国内网络用清华镜像）
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
.venv\Scripts\playwright install chromium
```

### 3.2 配置 `.env`

```powershell
Copy-Item .env.example .env
notepad .env
```

必填项：
```ini
GLM_API_KEY=你的 TokenHub GLM Key
ODOO_PASSWORD=odoo123456        # Odoo admin 密码
```

其余按默认即可（默认值已指向正确环境）。

### 3.3 同步模块源码并建 Git 基线

```powershell
# 从 Ubuntu 拉取 baselife_stock 模块（首次）
$env:PYTHONPATH = "$PWD"
.venv\Scripts\python.exe src\utils\sftp_tool.py pull

# 建立 Git 基线（worktree 隔离依赖）
git -C workspace\baselife_stock init
git -C workspace\baselife_stock add -A
git -C workspace\baselife_stock commit -m "baselife_stock baseline"
```

### 3.4 验证模型链路

```powershell
# 验证 Qwen
.venv\Scripts\python.exe -c "from openai import OpenAI; c=OpenAI(base_url='http://192.168.108.143:11434/v1', api_key='ollama'); print(c.chat.completions.create(model='qwen2.5vl-tools:latest', messages=[{'role':'user','content':'1+1=?'}], max_tokens=10).choices[0].message.content)"

# 验证 GLM
$env:TOKENHUB_GLM_API_KEY="你的key"; .venv\Scripts\python.exe -c "from openai import OpenAI; import os; c=OpenAI(base_url='https://api.tokenhub.market/v1', api_key=os.environ['TOKENHUB_GLM_API_KEY']); print(c.chat.completions.create(model='glm-5.2', messages=[{'role':'user','content':'hi'}], max_tokens=10).choices[0].message.content)"
```

### 3.5 运行

```powershell
.venv\Scripts\python.exe run.py
```

预期输出：`[TESTS PASSED]`，报告写入 `artifacts/reports/final_report.json`，每页截图在 `artifacts/screenshots/`。

---

## 4. 流水线工作原理

```
Round 1:
  E2E 测试（登录 + OmniPod 11 个 action 页面）
    ├─ 通过 → 输出报告，结束
    └─ 失败 → 创建 Git worktree fix/roundN
             Qwen 诊断（日志+截图+DOM → JSON）
             GLM 在 worktree 中生成修复补丁
             应用补丁 → 提交 worktree → SFTP 推送 Ubuntu
             重启 odoo19.service → 等待 8s
Round 2..N: 重测；通过则 merge worktree → main
            失败则 reset worktree 重来
达到 MAX_RETRIES → 保存诊断与截图，返回失败
```

**菜单导航**：通过 `tests/menu_map.json` 中记录的 action ID 直接访问
`/odoo/action-XXX`（比模拟点击下拉更稳定）。重新生成映射：
```powershell
.venv\Scripts\python.exe tests\probe_menu_api.py
```

---

## 5. 定时任务（自动回归）

```powershell
# 管理员 PowerShell
powershell -ExecutionPolicy Bypass -File schedule_task.ps1 -Install
# 自定义时间（如每天 06:30）
powershell -ExecutionPolicy Bypass -File schedule_task.ps1 -Install -Hour 6 -Minute 30
# 卸载
powershell -ExecutionPolicy Bypass -File schedule_task.ps1 -Uninstall
```

任务：`OdooAutoTestLoop`，以 SYSTEM 身份每天运行 `run.py`。

---

## 6. CI（GitHub Actions + 自托管 Runner）

Odoo/Qwen 在局域网内，GitHub 云端 runner 无法访问，因此需自托管 runner：

```powershell
# 在本机添加 self-hosted runner（Settings → Actions → Runners → New self-hosted runner）
# 标签: self-hosted, windows, odoo-lan
```

仓库 Secrets（Settings → Secrets and variables → Actions）：
| 名称 | 值 |
|---|---|
| `GLM_API_KEY` | TokenHub GLM Key |
| `ODOO_PASSWORD` | Odoo admin 密码 |

仓库 Variables：
| 名称 | 值 |
|---|---|
| `GLM_BASE_URL` | `https://api.tokenhub.market/v1` |
| `GLM_MODEL` | `glm-5.2` |
| `QWEN_BASE_URL` | `http://192.168.108.143:11434/v1` |
| `QWEN_MODEL` | `qwen2.5vl-tools:latest` |
| `ODOO_URL` | `http://192.168.108.134:8069` |
| `ODOO_DB` | `odoo19_test` |
| `ODOO_USER` | `admin` |
| `MAX_RETRIES` | `3` |

工作流在 `.github/workflows/autotest.yml`：
- push 到 main
- 每天 02:00 UTC（北京时间 10:00）
- 手动触发（workflow_dispatch）

产物自动上传：截图、报告、workspace。

---

## 7. 常见问题

| 现象 | 排查 |
|---|---|
| 登录超时 | Odoo URL/密码是否正确；`Test-NetConnection 192.168.108.134 -Port 8069` |
| Qwen 调用失败 | Ollama 是否运行：`Test-NetConnection 192.168.108.143 -Port 11434` |
| 页面 FAIL | 菜单 action ID 是否变化 → 重新生成 menu_map.json |
| GLM 无修改 | 诊断 confidence 低或根因不在代码，查看 `final_report.json` |
| push 失败 | Ubuntu SSH 凭据（`src/utils/sftp_tool.py` 顶部） |
| 中文乱码 | 已自动 `reconfigure utf-8`；PowerShell 控制台用 `chcp 65001` |

---

## 8. 安全说明

- `.env` 含密钥，已在 `.gitignore`，**永不提交**
- Odoo 密码 / GLM Key 通过环境变量或 Secrets 注入
- 测试账号建议使用独立测试库专用账号，勿在生产库跑 E2E
