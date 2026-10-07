# hn072 CPU 研究服务器：Git 与实验入口

本地开发目录：`/Users/haoning/project/w2w/nw-design-for-wsi`。
服务器：`hn072@143.89.78.72`；主工作区：`/Projects/haoning/w2w`。
唯一研究远端：[HaoningJiang-space/w2w-memory](https://github.com/HaoningJiang-space/w2w-memory)，
只维护 `main`。服务器工作区直接通过 GitHub SSH 完整 clone，没有源码压缩包同步。

## 分工与同步

在本地修改、测试、commit；推送 `research-origin main`。服务器随后：

```sh
cd /Projects/haoning/w2w
git status --short --branch
git pull --ff-only research-origin main
git rev-parse HEAD
.venv/bin/python -m unittest tests.test_patterns_trace tests.test_patterns_batch tests.test_read_workload tests.test_request_window tests.test_patterns_replay
```

实验从干净提交启动，记录完整 commit、协议和输入哈希。结果核对后回收到本地归档提交，
再 push/pull。不要在运行中的旧 checkout 上 pull；不要 force-push、reset 或覆盖另一位开发者的修改。

两端保留 `origin=https://github.com/spcl/nw-design-for-wsi.git` 作为原论文 upstream；
服务器的 `research-origin=git@github.com:HaoningJiang-space/w2w-memory.git`，main 跟踪它。
服务器已验证 SSH `ls-remote` 和 `push --dry-run`。使用仓库专用可写 Deploy Key；
不是 GitHub 账户全仓库授权。私钥仅在服务器 `~/.ssh/id_ed25519_github`，不入 Git。
GitHub 账户公钥 API 当时返回 HTTP 500，因此采用了仓库级授权。

## 实验材料在哪里

| 内容 | 主工作区入口 | 实际位置 / 说明 |
|---|---|---|
| 全部 Git 源码、RTL、协议、报告、已归档结果 | `w2w/`, `rtl/`, `docs/`, `artifacts/` 及上游文件 | 完整 main 历史，非浅克隆 |
| 真实 routing / demand / replay | `memory_results/` | 链接到 `/Projects/haoning/w2w-trace-20261007/memory_results` |
| 256-request 原始 corpus | `memory_results/pbc_corpus256/` | 849 MB；manifest 记录固定 revision、ID、SHA-256 |
| 48次多窗口实验 | `memory_results/pbc_multiwindow/` | 旧 checkout 上以 `aa9d911` 启动，保留其 provenance；以 summary 和审计判断是否完成 |
| ASIC / endpoint 历史展开输出 | `build/asic_runs/` | 链接到 `/Projects/haoning/w2w-memory-slice-20261007`，不移动正在使用的目录 |
| PDF 技术报告 | `docs/reports/W2W_MEMORY_SERVICE_TECHNICAL_REPORT.pdf` | 已在 Git 中 |

历史实验的压缩证据和元数据已在 `artifacts`；原始大 trace、PDK/工具安装、密钥、许可证、
venv、临时 build 缓存不进入 Git。其他开发者的 ASIC 目录保留原样；其工具或授权条件不代表
新 CPU venv 自动具备 ASIC 重跑能力。旧 eex005 的全部工作区也没有因此被删除或迁走。

## Python 与 Codex

主工作区使用独立 `.venv`，按正在运行的 trace 环境 pip freeze 安装；
锁文件和安装日志在 `build/requirements-server.lock.txt`、`build/environment_install.log`。
主要依赖为 Python 3.10、NumPy 2.2.6、SciPy 1.15.3、NetworkX 3.4.2、Shapely 2.1.2、
PyMetis 2025.2.2。不需要 GPU。

Codex CLI 0.161.0 已按 [OpenAI 官方安装方式](https://learn.chatgpt.com/docs/codex/cli)
安装到 `/Projects/haoning/.local/bin/codex`，新登录环境已在 PATH。
安装独立二进制，不额外安装 Node.js；没有复制本机的 OpenAI 登录凭证。

用户在服务器自行授权：

```sh
codex login --device-auth
cd /Projects/haoning/w2w
codex
```

设备登录需账号允许，参见[官方认证说明](https://learn.chatgpt.com/docs/auth)。
研究仍以本地修改、Git 同步、服务器执行为主，不同时让两个工作区编辑同一任务。

HF 实测直连更快，已恢复默认直连；可选 VPS 用法见[网络配置与实测](HN072_PROXY.md)。
