# hn072 可选出站代理（当前默认直连）

2026-10-07 配置于 `hn072@143.89.78.72`，账号 home 为 `/Projects/haoning`。
服务器原本可以直连 Hugging Face；此配置用于用户指定的 VPS 出口，不是修复 HF 可达性。
401 为数据集授权问题，与出口切换分开处理。

## 使用

用户要求根据 HF 实际速度决定是否使用代理。对同一授权 trace 做 direct/proxy/proxy/direct
四次完整下载，直连 1.645309 / 1.420950 秒，代理 21.584776 / 3.689110 秒，全部哈希相同。
因此最终恢复默认直连，用户隧道服务已 disable/stop；不是 HF 访问失败。

重新 SSH 登录后默认直连。已打开的终端清除旧代理变量：

```sh
. /Projects/haoning/.config/w2w-network/proxy.sh
curl https://api.ipify.org
# 143.89.78.72
```

当前终端临时切换：`proxy_on` 启动隧道并切到 VPS，`proxy_off` 恢复直连；单条 curl
直连可用 `curl --noproxy '*' URL`。新登录默认直连。
手动开启后如需停止后台隧道，执行 `systemctl --user stop w2w-download-proxy.service`。

环境变量是账号级默认值，不是服务器透明网关：不改路由表，不影响其他用户、
已运行进程或不读取代理环境变量的程序。非交互 SSH 命令与新后台服务应显式
source 上述文件；`hn072` 默认 shell 是 `/bin/sh`，非登录 shell 不保证读取 `.profile`。

## 实现与维护

- 实验服务器 HTTP/HTTPS：`http://127.0.0.1:18081`。
- 实验服务器 SOCKS：`socks5h://127.0.0.1:18080`。
- `http_proxy/https_proxy` 和大写变量指向 HTTP 入口；`all_proxy/ALL_PROXY` 指向 SOCKS。
- `no_proxy/NO_PROXY` 仅豁免 `localhost,127.0.0.1,::1`。
- SSH 隧道连接 VPS `216.36.109.31:13013` 的专用 `w2wproxy` 账号；
  专用公钥登录、只允许本地 TCP forwarding，禁止交互 session。
- VPS 的 tinyproxy 仅监听 `127.0.0.1:18888`，由 SSH 转发到实验服务器。
  两端均未开放公网代理监听；HTTPS 保留客户端到目标站点的 TLS。
- `systemctl --user status w2w-download-proxy.service` 查看隧道。
  当前 disabled/inactive；手动启动后账号原有 `Linger=yes` 允许退出后继续运行，断线自动重试。
- VPS 使用 `w2w-http-proxy.service`，已 enable；配置位于 `/etc/w2w-proxy/tinyproxy.conf`。
- 用户环境：`/Projects/haoning/.config/w2w-network/proxy.sh`，从 `.profile` 和 `.bashrc` 加载。
  两文件原件分别备份为 `.profile.pre-w2w-proxy`、`.bashrc.pre-w2w-proxy`。

密钥只保存在实验服务器 `.config/w2w-network`，不入 Git；密码及 HF token 不存入代理配置。
撤销默认代理时删除两个启动文件中的 `W2W default proxy` 加载段，并停止用户服务；
先在当前终端 `proxy_off`，避免已继承的环境变量继续指向已停止的代理。

## 实测证据

代理开启时，不带 `--proxy` 的 curl 和 Python urllib 均返回出口 `216.36.109.31`；
HF 首页 HTTP 200，curl TLS 校验返回 0。恢复直连后，新登录环境的普通 curl 返回
`143.89.78.72`，隧道服务 disabled。SOCKS 入口还验证了真实授权 trace 的 Range 续传：

- 固定 revision：`27febb7b2d24169560a9f6f83d38eb53f94916cf`。
- 文件：`Qwen/Qwen3-235B-A22B-FP8/mmlu/abstract_algebra/59.json`。
- 先取 65,536 bytes，再用 `curl --continue-at -`，服务端返回 206。
- 完整 3,408,360 bytes，SHA-256：`500f15d6e4f628f7a7fc86379d51821ecfa14c041adbe142eec1a5dcd06bb0da`。
- Git blob：`f09867a7e7d3f1b7cc08239aa7e2a866eb108503`，与已固定 HF 元数据一致。
- 明文 token 仅经加密 SSH stdin 传入进程内存；没有写入远端文件或命令参数。

证据在服务器 `w2w-trace-20261007/build/proxy_validation/receipt.json`。
此续传检查不表示现有 Python corpus downloader 已支持部分文件续传；它的 `--resume`
仍只复用已完成且身份校验通过的文件。代理配置没有改变现有实验或下载采样协议。
