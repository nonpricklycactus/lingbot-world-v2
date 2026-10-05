# Windows 原生部署套件 · LingBot-World 2.0 / i2v-1.3B

本分支 = **上游代码 + 在一台 6GB 显存 Windows 笔记本上跑通单卡 13 帧的改动与记录**。
上游官方 README 只给 Linux / 多卡示例；这里的路径是单进程、单卡、原生 Windows 的实测路径。

> 非官方支持分支。上游代码与模型许可为 **CC BY-NC-SA 4.0**（署名、非商业、相同方式共享），
> 本分支是添加 Windows 部署改动的衍生版本，不提供任何商业授权。

## 目录

| 路径 | 内容 |
|---|---|
| `wan/modules/attention.py` | 已打好的 SDPA 回退补丁（原版见 `deploy/patch/attention.py.orig`） |
| `deploy/patch/` | 补丁 diff、改前/改后文件、17 项离线测试、验证记录 |
| `deploy/manual/` | Windows 原生部署与录屏手册：口径、判据、失败处理 |
| `deploy/tools/lingbot-deploy/` | 分步执行器：每步先打印命令再执行，输出脱敏并留日志 |
| `deploy/tools/vdesk-operator/` | 在虚拟显示器上以拟人节奏操作并只录那一块屏（可选，录教程用） |
| `deploy/report/` | 13 页图文、PDF、抽帧图与 QA（本次实测结果） |

## 最短路径

1. **准备**：NVIDIA 显卡驱动、Git、FFmpeg；Python 3.12（官网安装器或 uv 都可以）。磁盘留 20 GB 以上，别放在系统盘。
2. **取代码**：`git clone <本仓库>`，切到本分支。
3. **建环境**：在仓库目录里建 venv，装依赖。torch 轮子建议用 aria2 多连接抓到本地再 `pip install` 本地文件——同一条 URL，单连接 2.15 MiB/s，`aria2c -c -x16 -s16 -k1M` 均速 18 MiB/s，约 8 倍。
4. **CUDA 闸门**：`python -c "import torch; print(torch.cuda.is_available(), torch.version.cuda)"` 应为 `True 12.8`。
5. **补丁**：本分支已应用；要复核就跑 `deploy/patch/test_attention_fallback.py`（17/17 过），哈希对照见 `deploy/patch/VERIFY.txt`。
6. **下权重**：1.3B DiT 六个分片 + index（6.84 GB）与共享 T5 / VAE / tokenizer（11.89 GB），逐个核对 SHA-256，只取需要的文件，不要拉 14B 本体。
7. **跑 13 帧**：命令与参数见 `deploy/manual/` 的 §6.3 与 §6.5。

## 为什么需要这个补丁

`causal_fast` 的 cross-attention 在源码里硬依赖 flash-attn，而 flash-attn 在 Windows 上没有可用轮子
（PyPI 上全是源码包；源码编译又要求 MSVC 与和 PyTorch 一致的 CUDA 版本）。
补丁给 `flash_attention()` 加了一条与 flash-attn varlen 语义等价的 PyTorch SDPA 实现：
GQA 展开、变长 padding mask、causal、滑动窗口。装了真 flash-attn 的环境会自动优先用它，不需要回滚。
开关：`WAN_ATTENTION_IMPL=auto|flash|sdpa`。

## 本机实测（参考量级，不是通用性能）

- 机器：RTX 3060 Laptop 6GB / 64 GB 内存 / Windows 11 家庭版 10.0.26200 / 驱动 610.47
- 输出：832×464、13 帧、16 fps、0.8125 秒；SHA-256 `897c908d04950630a89ac88f95e3831c3327f76e4be796af0d2b507cf6d66b8f`
- 生成段：日志时间戳约 763 秒（12 分 43 秒）；运行中采样显存 4996 MiB / 6144 MiB
- 上游 README 给的 1.3B 示例是四卡；单卡路径是本次实测的候选方案，不是官方结论

## 边界

- 只对本次具体机器与版本负责，不外推到其他显卡、其他 Windows 版本、720p/60fps、实时生成或商业使用。
- `deploy/report/` 里的构建脚本按原始工作区目录写路径，搬到本仓库只作留档；图片、PDF 与事实绑定可直接看。
- 素材里的录屏、抽帧与用户素材不上传；需要画面证据时按 `deploy/report/` 的说明在本机重放。