# DRAM 命令时序与有限读返回闭环

`service/dram` 为既有读执行器增加可选 Ramulator 命令后端。固定地址先获得有限 source 返回空间，控制器接受请求后才进入 DRAM；只有命令模型的完成回调能使该字进入 HB 发送。请求 outstanding、source 队列、HB 序列化、RX 和任务依赖仍由 `read_replay` 管理。默认 slot 模型及历史结果不变。

## 注册的参考组织

固定上游 [CMU SAFARI Ramulator](https://github.com/CMU-SAFARI/ramulator2/tree/72427a1bba3771564c4fb0e494ba02242fd1eaa7)，提交 `72427a1bba3771564c4fb0e494ba02242fd1eaa7`。使用 `HBM2_2Gb`、`HBM2_2000Mbps`，每 memory 实例一条 channel、两个 pseudochannels、32 banks、512 MiB。控制器 HBM12，FRFCFS，open row，all-bank refresh，读队列深度 32。

这是公开 HBM2 参考，**不是定制 WoW DRAM 标定**。上游 [HBM2 参数](https://github.com/CMU-SAFARI/ramulator2/blob/72427a1bba3771564c4fb0e494ba02242fd1eaa7/python/ramulator/dram/hbm2.py) 明确包含估算值。HBM 通道数据总线也是模型资源；不能将其与旧的每 memory 1 TB/s 独立 bank 服务视为相同预算。后端变化后的绝对时间只用于解释参考约束的影响，不证明同预算下某种 fabric 退化。

| 参数 | 约定 |
|---|---|
| 原子传输 | 32 bytes，与逻辑字严格相等，不隐式拆分或合并 |
| DRAM 周期 | 1000 ps |
| endpoint slot | 1024 ps；slot t 推进至 floor(t×1024/1000) 个 DRAM 周期 |
| 每 bank 容量 | 2^19 个字，16 MiB；检查全部对象驻留，不仅活动对象 |
| 行与列 | 行 = bank-local word // 32；列 = (word % 32)×4 |
| 地址向量 | channel, pseudochannel, SID, bankgroup, bank, row, column |
| 编号映射 | global bank // 32 为 channel；local bank 按 16/4/1 分解 |
| 额外 native 延迟 | 必须为 0，禁止再叠加旧固定 latency 或周期 ready |

所有 endpoint admission 必须先预留 source 字容量。控制器拒绝时保留原请求，下一 slot 重试。接受时分配唯一 ticket，回调恰好一次；HB 交付结束时控制器 pending 必须清零。控制器可乱序完成，当前 source 按接受顺序排队，可能产生队首阻塞；该保守约定不是新增无限 reorder buffer。

## 分层代码

- `service/dram/bridge.cpp`：薄 C++ 适配，只暴露 send、tick、callback、stats，命令选择与时序来自上游。
- `service/dram/ramulator.py`：公开 profile、时钟映射、地址/容量检查、版本和配置身份。
- `service/read_replay.py`：有限请求和返回缓冲，接收可选 native backend。
- `experiments/run_dram_bridge.py`：冻结 pilot；不把运行逻辑放入 service 层。
- `validation/dram_bridge.py`：重新核对归档哈希、固定 bank/route 字节和完整交付。
- `tests/test_dram_backend.py`：完成接口、row hit/conflict、bank 并行、刷新、队列反压、有限 HB/RX。

后端原生依赖为可选项。没有编译时，原有 LP、理论分析和 slot 实验照常运行；原生测试明确 skip，不以 skip 宣称 DRAM 检查通过。

## 构建和复跑

以下在服务器已有工程虚拟环境中执行。源码与构建放工程外或 ignored build 内。上游 CMake 会下载构建依赖并生成 DRAM C++ 描述；生成文件差异与二进制哈希随结果记录，不把生成差异隐藏为干净源码。

```sh
cd /Projects/haoning/w2w
export W2W_DRAM_SRC=/Projects/haoning/w2w-tools/ramulator2-72427a1
# 首次准备；若目录已存在先检查，不覆盖。
git clone https://github.com/CMU-SAFARI/ramulator2.git "$W2W_DRAM_SRC"
git -C "$W2W_DRAM_SRC" checkout 72427a1bba3771564c4fb0e494ba02242fd1eaa7
.venv/bin/python -m pip install PyYAML==6.0.3
cmake -S "$W2W_DRAM_SRC" -B "$W2W_DRAM_SRC/build" \
  -DPython_EXECUTABLE="$PWD/.venv/bin/python" -DCMAKE_BUILD_TYPE=Release
cmake --build "$W2W_DRAM_SRC/build" -j4
cmake -S w2w/service/dram -B build/dram_bridge \
  -DRAMULATOR_SOURCE="$W2W_DRAM_SRC" -DPython_EXECUTABLE="$PWD/.venv/bin/python"
cmake --build build/dram_bridge -j4
export PYTHONPATH="$W2W_DRAM_SRC/python"
export W2W_RAMULATOR_BRIDGE="$PWD/build/dram_bridge/_w2w_ramulator.cpython-310-x86_64-linux-gnu.so"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
.venv/bin/python -m unittest tests.test_dram_backend -v
.venv/bin/python -m w2w run_dram_bridge --ramulator-source "$W2W_DRAM_SRC" \
  --output /Projects/haoning/w2w-dram-pilot-NEW
.venv/bin/python -m w2w audit_dram_bridge \
  --source /Projects/haoning/w2w-dram-pilot-NEW \
  --trace-source artifacts/results/workload/provisioning_holdout/inputs/h0_b1/trace.json \
  --output /Projects/haoning/dram-pilot-audit.json
```

扩展名路径对应当前 Python 3.10/Linux，其他 Python 版本使用实际生成的 `.so`。构建检查上游 revision，运行再检查二进制内嵌 revision。实验要求工程已提交且干净；结果记录完整解析配置、桥接二进制、上游库与生成差异的 SHA256。

## 最小实验范围

从 `h0_b1` 冻结 trace 按顺序选第一个有读请求的任务。保持完整 18,878,976-byte expert 权重、128 个驻留对象和已有 expert owner，只隔离该任务并归零依赖/起始时间。分别运行 home、k2、wide k3、B configurable；每个设计各跑旧 slot 和新 HBM2 参考，N=192。

此实验是 **真实 routing 派生的完整对象读取探针**，不是整个 serving batch、GPU 推理或完整应用延迟。跨后端必须有相同 residency hash 和逐 bank 字节。相同 HBM2 资源下可比较这四个冻结设计的单任务服务，但不能由一个任务估计真实 workload 的平均收益。

后续应按同一 DRAM 组织扩展冻结 batch 与请求容量敏感性，并验证 address mapping、row policy 与端点返回预留的影响。最终 WoW 定量结论还需要指定原生数据路径与时序参数；工艺 PPA/signoff 继续使用独立证据链。
