# LingBot-World 1.3B Windows 11 原生部署与录屏操作手册 v1

更新时间：2026-10-04

> **本手册明确不使用 WSL。** 主线是 Windows 11 原生 PowerShell、原生 Python 虚拟环境、Windows 版 PyTorch/CUDA 和 Windows 原生录屏。
>
> 这是一份给本次手动复现和录屏使用的实验手册，不是已验证的 Windows 安装器。项目目前只有 WSL2/Linux 环境的成功记录；Windows 原生的依赖安装、`flash-attn`、模型加载和推理都必须以本次实际结果为准。请把实际执行的命令、版本、报错和结果原样保留。后续视频只使用本次录屏和本次运行能够证明的事实。

## 0. 先看结论和边界

### 0.1 本手册要完成什么

目标是在一台 Windows 11 电脑上，**不安装、不进入 WSL**，尝试运行 LingBot-World 2.0 的 `i2v-1.3B` 最小图生视频路径，并留下：

1. GPU、驱动、系统内存和 Windows 软件版本记录；
2. 仓库 commit、Python、PyTorch/CUDA 和依赖版本记录；
3. 模型目录、共享资源和下载结果记录；
4. 真实安装、下载、启动、加载和等待过程录屏；
5. 第一次成功输出，或完整、可诊断的失败现场；
6. Windows `ffprobe` 对输出文件的结构化验收结果。

成功与失败都是真实实验结果。不要为了让教程看起来完整而跳过安装错误、资源错误、CUDA 错误或显存不足。

### 0.2 已有参考实测，不是这台 Windows 机器的结论

项目此前在以下环境跑通过一条单进程路径：

- RTX 3060 **Laptop** GPU，6144 MiB；
- Windows 11 宿主机，但模型运行在 WSL2 Ubuntu 24.04.5；
- 宿主机 64 GB RAM，WSL 可见约 47 GiB；
- `lingbot-world-v2` commit `1895d300d8ac936401689b26389f51cbd36530eb`；
- Python 3.12.3；PyTorch 2.11.0+cu128；CUDA 12.8.93；`flash-attn` 2.8.3.post1；
- 单进程 `causal_fast`，13 帧，输出 832×464、16 fps；
- LB-HEAD-001 的 13 帧生成段约 612 秒，成片时长 0.8125 秒，峰值显存 5986 MiB。

这些数字只能作为**历史 WSL 基线**。不能把它们套到本机的 RTX 3060 Laptop（6 GB）、63.73 GiB RAM 或 Windows 原生环境，也不能从计划或截图推断本次耗时和显存。

### 0.3 当前没有验证的事项

本项目目前没有验证：

- Windows 原生 Python 环境能否完整安装并运行该仓库；
- Windows 原生 `flash-attn` 是否有匹配 wheel，或能否由本机 MSVC/CUDA 工具链编译；
- Windows 原生 PyTorch CUDA 是否能在这台机器上正常工作；
- 本机 RTX 3060 Laptop（6144 MiB）在 Windows 原生、单卡 6 GB 显存下是否够用；
- 32 GB 系统内存能否完成 T5、VAE、tokenizer 和 DiT 的加载；
- 上游代码中的路径处理、动作文件 loader 和模型目录结构在 Windows 原生下是否全部兼容；
- 官方 4 卡命令在单卡上的适用性；
- 720p/60fps、实时生成、任意分辨率/帧数或生产服务部署；
- 商业使用。模型和代码许可边界以 CC BY-NC-SA 4.0 及各依赖的许可为准，不要把本教程说成商业授权。

官方 README 的 1.3B 示例使用 `torchrun`、4 个进程、FSDP 和 Ulysses 多卡参数；那不是本手册的单卡 Windows 命令。下面的单卡命令是根据历史 WSL 单进程参数整理出的**待验证本地实验候选**，不是官方 Windows 支持声明。

### 0.4 录制前已核对的上游事实（代码/来源层面，不是本机实测）

2026-10-04 对照固定 commit 的源码和官方仓库补了三条会直接影响录屏顺序的事实。它们是来源核实，不是这台 Windows 机器的运行结果。

1. **cross-attention 硬依赖 flash-attn，没有可用的 SDPA 回退。** `wan/modules/attention.py` 的 `attention()` 在 flash-attn 缺失时会退到 `torch.nn.functional.scaled_dot_product_attention`；但同一个文件里的 `flash_attention()` 带 `assert FLASH_ATTN_2_AVAILABLE`，而 `wan/modules/model_fast.py`（`WanCrossAttention`）与 `wan/modules/model_causal.py`（`CrossAttention_KVCache`）都直接调用 `flash_attention(...)`。所以 `causal_fast` 与 `causal_pretrain` 两条路径都绕不开 flash-attn。
   → 推论：如果现场**没有装成 flash-attn 却跑起来了**，说明实测代码与这个 commit 不一致，必须查明原因，不能当成功结论。
2. **官方 1.3B 参考是多卡。** `run_fast.sh` 对 1.3B 选择 `NPROC=2`、`CUDA_VISIBLE_DEVICES=0,1`、`--ulysses_size 2`，README 的示例是 4 卡。本手册的单卡命令是项目自改的候选路径，不是官方支持。
3. **公开的第三方 Windows wheel 不是本项目验证过的依赖。** 即使能找到与某个 torch、CUDA 和 Python 版本相匹配的预编译包，也不能把它当作官方支持或本机成功证据。本手册不把第三方 wheel、fork 或替代包列为默认安装步骤；若官方入口失败，本次实验停在 `07_error`。

### 0.5 官方路径和本手册候选路径的关系

固定 commit 的官方 README 给出的 1.3B 示例是 4 GPU 多进程命令，包含 `torchrun --nproc_per_node=4`、`--dit_fsdp`、`--t5_fsdp` 和 `--ulysses_size 4`。同一仓库的 `run_fast.sh` 对 1.3B 又会选择 2 个进程、GPU 0/1 和 `--ulysses_size 2`；这两条官方参考路径存在差异，且都不是单卡 Windows 证明。

源码检查还显示：多进程路径使用 NCCL/`env://` 初始化；单进程路径拒绝 FSDP 和大于 1 的 Ulysses size。仓库没有原生 Windows 安装、编译或运行测试；只有少量文件名处理分支涉及 Windows。因此第 6 节命令是从项目历史 WSL 单进程 run 改写的本地候选，必须以本次真实结果验证，不能称为官方 Windows 方案。

## 1. 录屏前准备

本手册由用户本人在 Windows 上手动执行、手动录屏（2026-10-04 决定：本期题材不适合自动化，需要当场处理问题）。项目侧不代跑部署，也不使用脚本化终端回放或自动截图。

录屏以“刚装好的干净 Windows 11”作为叙述起点。本机已经具备的通用组件（显卡驱动、Git、FFmpeg）本次**不重装**，只在画面里声明版本，并把需要的项目和官方安装入口交给观众，见 §2.3。

**操作入口**：这套步骤有配套的分步执行器 `tools/lingbot-deploy/run-deploy-steps.cmd`（说明见 `tools/lingbot-deploy/README.md`）。双击进菜单选编号，或用 `run-deploy-steps.cmd -Step 0` 只跑某一步；每步会先把命令原样打印出来（方便整理教程网页），执行输出默认脱敏并写到 `F:\Temp\lingbot-deploy-logs\`。它只是执行器——口径、判据、失败处理和审批仍以本手册为准。

### 1.1 使用 OBS 录制 Windows 原生过程

推荐使用 OBS Studio；也可以使用 Windows Game Bar 或其他 Windows 原生窗口录制工具。不要使用 WSL 虚拟显示器或 Linux 录屏工具，本手册的录屏对象是 Windows PowerShell 和 Windows 播放器。

建议设置：

- 画布：1920×1080；
- 输出：完整 16:9，不预留独立字幕带；
- 捕获：PowerShell 窗口和结果播放器窗口，尽量不要捕获整个桌面；
- 文字：保证最长命令和 traceback 不被裁掉，字号足够阅读；
- 录制：先录 10 秒测试画面，检查窗口边缘、字体和系统缩放。

录到真实的硬件检查、代码版本、依赖安装、模型下载、实际启动命令、加载日志、错误和结果播放。长下载或长推理可以在最终剪辑中加速或跳过，但必须说明时间轴已压缩；剪辑长度不能代替真实模型耗时。

关闭桌面通知和无关窗口。不要让密码管理器、聊天、邮箱、账号、token、浏览器私人页面、个人文件名或不希望公开的路径入镜。模型需要 Hugging Face 登录时，暂停录屏后在本机完成登录，不要录入 token。

### 1.2 录屏 marker

每个阶段开始时，在 PowerShell 输入一个可见的 marker，或口头清楚读出 marker，并停留 5–8 秒。marker 不包含 token、密码或完整私人目录。

| Marker | 需要录到的内容 | 是否建议单独截图 |
|---|---|---|
| `00_start` | 教程目标、录制分辨率、干净 PowerShell | 否，视频可抽帧 |
| `01_hardware` | GPU/显存、驱动、系统 RAM、Windows 和工具版本 | 是，文字不清楚时保存原生截图 |
| `02_repo` | 仓库 commit、Python、PyTorch/CUDA 和依赖版本 | 是，版本页可抽帧 |
| `03_resources` | DiT、T5/VAE/tokenizer 目录和下载完成情况 | 是，路径或文件名不清楚时保存 |
| `04_install` | venv、requirements 和 `flash-attn` 实际安装过程 | 否，保留连续过程 |
| `05_command` | 完整实际启动命令和输入文件检查 | 是，优先原生截图或停帧抽取 |
| `06_loading` | 真实加载日志、等待过程和实际错误 | 否，保留连续 10–20 秒片段 |
| `07_error` | 第一次完整错误、命令、traceback 和退出码 | 是，错误不能裁掉上下文 |
| `08_result` | 输出文件的真实播放画面 | 否，必须用视频，不只用静帧 |
| `09_verify` | 文件存在、模型退出码、SHA-256、`ffprobe` JSON | 是，结构化验收可抽帧 |
| `99_done` | 本次机器结论和未验证范围 | 否，视频可抽帧 |

**截图策略：** 不需要每个阶段都手动截图。只要 marker 画面停留足够久，后续可以从原始视频按真实 PTS 抽帧。只有命令、版本、关键错误和 `ffprobe` 结果在录屏中不可读时，才在同一次运行中另外保存原生 PNG。不要事后重新输入一条“看起来正确”的命令来补截图。

### 1.3 原始录屏和临时文件

- 原始 OBS 文件保持不改写，不覆盖、不重新编码原文件；
- 后续抽帧、代理、剪辑和中间文件统一写入 `F:\Temp`；
- 原始录屏交回时保留 SHA-256、分辨率、编码、帧率和真实时间轴；
- 不把未脱敏原始录屏、私人声音、token 或账号信息放进 Git、网站 `public/` 或公开素材目录。

## 2. Windows 11 原生硬件和工具检查

在**原生 PowerShell**中输入 `00_start`，然后输入 `01_hardware`。本节不调用 `wsl`，也不要求安装 WSL。

### 2.0 本机已核实的起始环境（2026-10-05，录制前只读实测）

这组值是开录前在本机读到的现状，录制时仍按 2.1、2.2 各跑一遍留下真实画面；本段只用来提前排掉会白录一遍的坑。

| 项 | 实测值 |
|---|---|
| GPU / 显存 | NVIDIA GeForce RTX 3060 Laptop，6144 MiB，空闲 44 MiB |
| 显卡驱动 | 610.47，驱动自带 CUDA UMD 版本 13.3（向后兼容，够跑 cu128 轮子） |
| 系统 | Windows 11 家庭版中文版，版本 10.0.26200，64 位 |
| 内存 | 63.73 GiB |
| 已有工具 | `nvidia-smi`、`git 2.55.0.windows.1`、`ffmpeg 9.0.2`（Scoop）、`ffprobe 9.0.2`（Scoop） |
| 磁盘剩余 | C: 138.7 GiB、D: 76.4 GiB（系统盘）；E: 295 GiB、F: 310.3 GiB（第二块 980 PRO NVMe）；M: 网络盘，不用 |
| **Python** | **尚未安装。** `py` 启动器不存在，`python` 只有 Microsoft Store 的应用执行别名占位，会打印"Python was not found" |

Python 相关的两个必须避开的坑：

1. **不能用 Scoop 里那个 Python 3.14。** 已安装的 `D:\Scoop\apps\python\3.14.5` 版本过新，与本手册要用的 torch Windows 轮子（本手册按 `cp312` 核对；`flash-attn` 在 Windows 上根本没有轮子，见 §2.0 更正）都对不上；而且它只提供 `python3` 入口，没有 `python`，与手册命令不一致。
2. **不能沿用现在的 Store 别名版。** 当前的 `python` 会落到 `WindowsApps\python.exe` 占位程序，装依赖和建 venv 都会失败。

本机采用**零安装目录方案**（2026-10-05 决定）：Python 3.12 直接用已装 uv 里的 `cpython-3.12.13`，**不安装系统级 Python、不写注册表、不改系统 PATH**。仓库、依赖、权重和输出都落在 **`F:\AI`** 下，回滚就是删掉这一个目录。具体命令见 §4.1。

**放盘规则（2026-10-05 用户要求）：不要装在 C 盘系统盘。** 本机盘位：C: 138.7 GiB / D: 76.4 GiB 在系统盘（Samsung 980 1TB，Disk 0）上；E: 295 GiB / F: 310.3 GiB 在第二块 Samsung 980 PRO 1TB（Disk 1）上。本篇统一用 **`F:\AI`**（第二块 NVMe、剩余最多）；换成 `E:\AI` 只需改 §3 的 `$Root` 一处，但后面所有变量必须跟着一致。**不要放到 M:**，那是网络盘，模型加载速度本身是本次要记录的测量项，网络盘会直接污染这一项。

> 观众侧不走这条：视频里给读者的是官方安装器装 **Python 3.12 x64**（勾选 `Add python.exe to PATH`），这是最通用的做法，后面所有命令都一样。两种方式只在"解释器从哪来"上不同。

**2026-10-05 实测后更正三处事实**（原文说"不需要 CUDA Toolkit、本篇走预编译轮子"，与实测不符）：

1. **`flash-attn` 在 Windows 上没有可用的预编译轮子。** PyPI 上 76 个发行版全部是 sdist（源码包），不存在"直接装轮子"这条路；`pip download --only-binary=:all: flash-attn` 直接报 `No matching distribution found`。
2. **本机其实已经装了 CUDA Toolkit 13.3**（`C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.3\bin\nvcc.exe`）。torch 官方 Windows 轮子自带 CUDA 运行时，所以**跑推理不需要它**；但一旦走源码编译，构建脚本会读到它并要求与 PyTorch 的编译版本一致 —— 实测报错 `The detected CUDA version (13.3) mismatches the version that was used to compile PyTorch (12.8)`。
3. **本机没有 MSVC**（`cl.exe` 不存在），源码编译这条路也不通。实测 `pip install flash-attn --no-build-isolation` 退出码 1；失败链见 §4.4。

### 2.1 基础工具检查

逐行执行并保留真实输出：

```powershell
Get-Command nvidia-smi,git,ffmpeg,ffprobe -ErrorAction SilentlyContinue |
  Select-Object Name,Source

nvidia-smi
py --list
py --version
python --version
python -m pip --version
git --version
ffmpeg -version
ffprobe -version
```

如果某一条命令不存在，不要用另一台机器的输出替代。记录缺少的工具并停止到 `07_error`，或在录屏外安装后从该阶段重新开始，明确说明重新开始的原因。

本机按 §2.0 的零安装方案走，因此 `py`、`python` 两条**预期就是缺失**的（`python` 只会打印 Store 的提示）。保留这段真实输出，不要把它当成失败；接着补一条本机自己的检查：

```powershell
uv --version
uv python find 3.12
```

口播对应说明："我这台机器不装系统级 Python，用 uv 提供的 3.12；你如果用官网安装器，这一步应该看到 `py --list` 里有 3.12，后面命令一样。"

`ffmpeg.exe` 和 `ffprobe.exe` 必须是 Windows 可执行文件，并且位于 `PATH` 中，或者后续命令要写出它们的完整路径。`ffprobe` 只负责验收输出，不证明模型已经成功运行。

### 2.2 记录 GPU、Windows、RAM 和磁盘

```powershell
Get-CimInstance Win32_OperatingSystem |
  Select-Object Caption,Version,OSArchitecture,LastBootUpTime

Get-CimInstance Win32_ComputerSystem |
  Select-Object Manufacturer,Model,
    @{Name='TotalRAM_GiB';Expression={[math]::Round($_.TotalPhysicalMemory / 1GB, 2)}}

Get-CimInstance Win32_VideoController |
  Select-Object Name,DriverVersion,AdapterRAM

Get-PSDrive -PSProvider FileSystem |
  Select-Object Name,Root,Used,Free
```

`Get-CimInstance` 的 `AdapterRAM` 在部分驱动上可能不完整，以 `nvidia-smi` 的显存总量为准。至少保存：

- `nvidia-smi` 显示的完整 GPU 名称、显存总量、驱动版本；
- Windows 版本和系统架构；
- 实际 RAM，而不是“32G”这样的口头概数；
- 模型所在盘的剩余空间；
- Python、Git、FFmpeg/FFprobe 版本。

本次实测是 RTX 3060 Laptop、6144 MiB（以这条 `nvidia-smi` 的真实结果为准），不是 3080；不要用别的型号或别的卡的数字替代本次结果。

### 2.3 给观众的前置条件清单（本篇不重装的部分）

录屏以“刚装好的干净 Windows 11”为起点叙述。本机已经具备的通用组件**本次不重装**，只在画面里声明版本，并把需要的项目和官方安装入口交给观众；驱动、CUDA 这类有官方安装文档的通用组件，不在这条视频里重复教安装流程，告诉观众按官方文档装即可。

| 项目 | 是否需要 | 怎么获得 | 本机状态 |
|---|---|---|---|
| Windows 11 x64 | 需要 | 系统自带 | 家庭版 10.0.26200 |
| NVIDIA 显卡驱动 | **需要**（唯一必须的 GPU 组件） | NVIDIA 官方驱动下载页，按显卡型号搜 | 610.47，已装，本次不重装 |
| CUDA Toolkit | 跑推理**不需要**；源码编译扩展时需要，且版本必须与 PyTorch 一致 | 见 NVIDIA 官方文档 | **本机已装 13.3**（含 `nvcc`），而 torch cu128 是 12.8 编的 —— 实测源码编译因此报版本不匹配 |
| MSVC / Visual Studio Build Tools | **本机没有** | 只有源码编译才需要，见 Microsoft 官方文档 | 实测 `cl.exe` 不存在；这正是源码编译 `flash-attn` 失败的原因之一 |
| Python 3.12 x64 | 需要 | 观众走 python.org 官方安装器；本机走 uv 便携方案 | 由 uv 提供，不装系统级 |
| Git | 需要 | git-scm.com 官方安装包 | 2.55.0，已装 |
| FFmpeg / FFprobe | 建议 | 官方构建站或包管理器 | 9.0.2，已装 |
| 磁盘空闲 | ≥ 20 GB，且**不要用系统盘 C 盘** | — | F: 310.3 GiB（第二块 NVMe） |
| 系统内存 | 建议 ≥ 32 GB（T5 在 CPU 上跑） | — | 63.73 GiB |

`01_hardware` 阶段的口播建议（照实情说，不照读未发生的事）：

> “驱动、Git、FFmpeg 这些我机器上已经有了，就不重新装一遍；你需要哪些、去哪里下载，我放在视频简介里。像 CUDA 和显卡驱动这种通用组件，官方文档写得很清楚，照着装就行，这条视频不重复讲。这次真正要动手的是 Python 环境、依赖和模型。”

## 3. 获取代码并固定版本

本节在 PowerShell 执行。先输入 `02_repo`。

建议使用不含空格、中文和个人用户名的示例目录：

```powershell
$Root = 'F:\AI\lingbot-world-v2'
$Base = Split-Path $Root -Parent
New-Item -ItemType Directory -Force $Base | Out-Null
Set-Location $Base

git clone https://github.com/robbyant/lingbot-world-v2.git
Set-Location $Root
git checkout 1895d300d8ac936401689b26389f51cbd36530eb

Write-Host 'repo_commit='
git rev-parse HEAD
git status --short
```

预期 commit 为：

```text
1895d300d8ac936401689b26389f51cbd36530eb
```

如果仓库已存在，不要直接 `git pull` 覆盖现场。先执行：

```powershell
Set-Location $Root
git status --short
git rev-parse HEAD
```

工作区有未保存修改时，停止并保留原状；不要为了录教程删除别人的改动。实际使用的路径、commit 和是否存在本地修改都要记录。

> **兼容性边界：** 上游仓库 README 主要提供 Unix shell 和多 GPU 示例，仓库没有原生 Windows 安装和运行的项目实测。本次路径是实验候选，不是上游 Windows 支持结论。Windows 的反斜杠路径由 PowerShell 传给 Python；如果上游 loader 在模型路径、动作路径或资源路径处报错，保留错误，不把 WSL 结果当成修复证明。

## 4. 建立原生 Python 虚拟环境

### 4.1 创建 venv

仍在 PowerShell 中执行。本机按 §2.0 定的零安装目录方案走：解释器取自本机已有的 uv 托管 3.12，venv 建在仓库目录内，系统里不装 Python。

```powershell
Set-Location $Root

# 0) 让 uv 和 pip 的缓存也落在 F: 上，避免几 GB 的 wheel 堆到 C 盘用户目录
$env:UV_CACHE_DIR = 'F:\AI\runtime\uv-cache'
$env:PIP_CACHE_DIR = 'F:\AI\runtime\pip-cache'

# 1) 取一个 3.12 解释器。本机 uv 里已有 cpython-3.12.13，这步直接命中，不下载
$Py312 = (uv python find 3.12).Trim()
& $Py312 --version

# 2) 在仓库目录建 venv，并把 pip / setuptools / wheel 一起装进去
$Venv = Join-Path $Root '.venv'
uv venv --python 3.12 --seed $Venv
$Py = Join-Path $Venv 'Scripts\python.exe'
& $Py --version
& $Py -m pip --version
```

2026-10-05 在本机实测：`uv python find 3.12` 返回 `D:\Dev\workspace\uv\python\cpython-3.12-windows-x86_64-none\python.exe`（即 3.12.13，MSC v.1944 64 位，`venv` 与 `ensurepip` 均可用）；`uv venv --seed` 会把 pip 直接装进新 venv，不需要额外补。

`UV_CACHE_DIR` / `PIP_CACHE_DIR` 是**当前会话**的环境变量，重开 PowerShell 要重设一次。不要写进用户级环境变量——那会往注册表里加东西，和本篇的零安装口径冲突。

想让解释器也收进 `F:\AI`（完全自包含）时，改用下面这条：它会联网下载一份新的 3.12 到 `F:\AI\runtime\python`，两种做法都不写注册表。

```powershell
$env:UV_PYTHON_INSTALL_DIR = 'F:\AI\runtime\python'
uv python install 3.12
```

如果 venv 里没有 pip（例如手动用 `-m venv` 建的），补一次：

```powershell
& $Py -m ensurepip --upgrade
```

观众侧的等价写法是官方安装器加系统解释器，后面完全一样：

```powershell
py -3.12 -m venv .venv
$Venv = Join-Path $Root '.venv'
$Py = Join-Path $Venv 'Scripts\python.exe'
& $Py -m pip --version
```

如果 `py -3.12` 不存在，先保留 `py --list` 和错误。不要把 Python 3.12 的历史 WSL 版本口播成 Windows 已验证版本，也不要用本机 Scoop 里的 Python 3.14（原因见 §2.0）。

可以激活环境：

```powershell
& (Join-Path $Venv 'Scripts\Activate.ps1')
python --version
```

如果 PowerShell 执行策略阻止激活，不要默认修改全局执行策略。直接使用 `$Py` 的完整路径继续执行即可：

```powershell
& $Py -m pip --version
```

### 4.2 安装官方依赖

输入 `04_install`，先升级 pip，再按固定 commit 的官方 `requirements.txt` 安装：

```powershell
Set-Location $Root
# 重开过 PowerShell 就先重设缓存目录，避免 wheel 落到 C 盘
$env:UV_CACHE_DIR = 'F:\AI\runtime\uv-cache'
$env:PIP_CACHE_DIR = 'F:\AI\runtime\pip-cache'
& $Py -m pip install --upgrade pip
& $Py -m pip install -r (Join-Path $Root 'requirements.txt')
```

该文件包含 `torch>=2.4.0`、`torchvision>=0.19.0`、`transformers>=4.49.0,<=4.51.3`、`numpy<2`、`diffusers`、`accelerate`、`imageio` 以及未固定版本的 `flash_attn` 等约束。实际安装的版本必须从本机环境记录；不要为了复刻历史输出而手动宣称安装了某个 CUDA 或 PyTorch 版本。

> `requirements.txt` 本身包含 `flash_attn`。因此 `pip install -r` 可能已经在该依赖处失败。出现失败时保留完整输出并进入第 4.3 节的停点，不要删除 requirements 中的依赖来制造“安装成功”。后面的官方显式安装命令用于记录/重试官方给出的 source-build 入口，不是保证 Windows 可用的修复。

安装成功后记录软件版本：

```powershell
& $Py -m pip show torch torchvision flash-attn transformers diffusers accelerate
& $Py -c "import torch; print('torch:', torch.__version__); print('cuda_available:', torch.cuda.is_available()); print('torch_cuda:', torch.version.cuda); print('gpu:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no CUDA'); print('vram_bytes:', torch.cuda.get_device_properties(0).total_memory if torch.cuda.is_available() else 'n/a')"
```

### 4.3 PyTorch CUDA gate

必须先通过 CUDA gate，再下载大模型或运行生成：

```powershell
$TorchCudaExit = 0
& $Py -c "import torch; print('torch:', torch.__version__); print('cuda_available:', torch.cuda.is_available()); print('torch_cuda:', torch.version.cuda); print('gpu:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no CUDA')"
$TorchCudaExit = $LASTEXITCODE
Write-Host "torch_cuda_check_exit=$TorchCudaExit"
```

如果 `cuda_available: False`，输入 `07_error`，保存完整版本和驱动信息，停止运行。不要先下载模型，也不要用历史 WSL 的 `torch.cuda` 输出代替本次结果。

先记录，再决定是否修复。Windows 上 `pip install torch` 默认可能拿到不匹配的构建，若要换成官方 CUDA 构建，用官方索引重装并**同时记录替换前后的版本串**（2026-10-04 核实 `cu128` 索引提供 `cp312` 的 Windows 轮子：2.7.0 / 2.7.1 / 2.8.0 / 2.9.0 / 2.9.1 / 2.10.0 / 2.11.0）：

```powershell
& $Py -m pip install --force-reinstall `
  --index-url https://download.pytorch.org/whl/cu128 `
  'torch==2.11.0' 'torchvision==0.26.0'
```

替换 torch 会连带改变 4.4 节能装哪个 `flash-attn` 轮子，两处版本必须一起核对后再开录。

### 4.4 Windows 原生 `flash-attn` 停点

这是本次原生 Windows 路径的最大不确定项，也是**必须先于模型下载和推理处理**的一项：按 §0.4 第 1 条，`causal_fast` 的 cross-attention 没有 flash-attn 就无法执行。

官方仓库给出的安装入口是：

```powershell
& $Py -m pip install flash-attn --no-build-isolation
```

随后立即检查导入：

```powershell
& $Py -c "import flash_attn; print('flash_attn import ok')"
$FlashAttnExit = $LASTEXITCODE
Write-Host "flash_attn_import_exit=$FlashAttnExit"
```

项目只在 WSL2/Linux 上安装和使用过 `flash-attn`。固定仓库没有 Windows 原生 wheel、编译成功记录或兼容性声明。因此本手册默认不引入第三方 wheel、GitHub fork 或替代包：

- 不要把未经项目验证的预编译 wheel 当成默认教程步骤；
- 不要把 `pip` 找不到匹配发行版说成显存不足；
- 不要把 WSL 的成功安装复制为 Windows 的成功证据；
- 如果源码编译失败、找不到匹配发行版或导入失败，保留完整 pip 输出、Python/PyTorch/CUDA/驱动版本和本机 MSVC/Build Tools 信息，输入 `07_error` 后停止；
- 只有 `import flash_attn` 成功后，才进入模型资源和生成阶段。

本节失败不是需要隐藏的“中间问题”，而是当前 Windows 原生实验的重要结论。
### 4.4.1 本次实测记录（2026-10-05，Windows 原生）

执行 `& $Py -m pip install flash-attn --no-build-isolation`，**退出码 1**；随后 `import flash_attn` 同样失败（`flash_attn_import_exit=1`）。完整输出留档：

- 录屏：`07-素材/世界模型部署相关/录屏-20261005/raw/step-06a-flashattn-fail.mp4`
- 文本：`07-素材/世界模型部署相关/录屏-20261005/logs/flashattn-install-failure.log`

失败链（三条叠加，缺任何一条都不至于失败）：

1. `Precompiled wheel not found. Building from source...` → 构建脚本去找预编译轮子，`urllib.error.HTTPError: HTTP Error 404: Not Found`；
2. 回退源码编译 → `FileNotFoundError: [WinError 2] 系统找不到指定的文件`（本机没有 MSVC）；
3. `RuntimeError: The detected CUDA version (13.3) mismatches the version that was used to compile PyTorch (12.8)`。

**结论：官方入口在 Windows 原生下必然失败**，本次实验按 §4.4 的规则停在 `07_error`；随后改用"新增 SDPA 等价实现"的代码补丁路径（见 §4.4.2）。

### 4.4.2 采用的替代路径：SDPA 等价实现

不改依赖，而是给 `wan/modules/attention.py` 增加一条与 flash-attn varlen 语义等价的 PyTorch SDPA 实现，
让 `flash_attention()` 在缺少 flash-attn 时回退到它（`causal_fast` 的 cross-attention 是唯一硬依赖点）。

- 触发方式：环境变量 `WAN_ATTENTION_IMPL=auto|flash|sdpa`；`auto` 时**装了 flash-attn 就优先用 flash-attn**，补丁不需要回滚。
- 覆盖语义：GQA/MQA 展开、变长 padding mask、causal、滑动窗口 `window_size=(left,right)`。
- 改动三处：① 顶部加 `import os`；② `flash_attention()` 开头加分支，缺少 flash-attn 时走新实现；③ `attention()` 改为委托 `flash_attention()`（**原版官方回退会静默忽略 padding mask，会改变结果**）。文件末尾新增 `_attention_impl()` 与 `_sdpa_varlen_attention()`。
- 验证：与 float64 手写参考实现逐元素比对（误差 < 2e-5），**17 项离线测试全部通过**（`Ran 17 tests ... OK`）；另有对照测试证明原版官方回退确实忽略 padding。
- 真机验证：CUDA 上用真实量级形状冒烟通过 —— `out: (1, 1560, 12, 128) bfloat16 | 有限值 True | 峰值显存 23.6 MiB`（Lq=1560/Lk=512/heads=12/dim=128，`k_lens=[400]` 走 padding 分支）。
- 文件哈希：原版 `b6f57f0a9bb36164cdccc3f03345f287f95dc5703bbc25cf1aaddaff946b8500` → 补丁版 `d0efbca939f07b8948e49cf44e43834d388e1b5f6efd0f4d37f7141063511558`；差异 125 行。
- 素材与验证记录：`07-素材/世界模型部署相关/录屏-20261005/patch/`（含 `attention-patch.diff`、两个版本的文件、`VERIFY.txt`、17 项测试源码）。
- 该路径**不是官方支持**，属于本机实验分支；使用时必须在成片里说明。

## 5. 下载模型和共享资源

### 5.1 资源关系

1.3B Hugging Face 包主要是 DiT 权重；T5、VAE 和 tokenizer 需要从 `robbyant/lingbot-world-v2-14b-causal-fast` 资源中复用。项目历史测试没有下载 14B DiT 本体。

建议把模型放在 Windows 本地磁盘的非系统盘上，例如 `F:\AI\models`（本机第二块 NVMe，剩余 310.3 GiB）。**不要放在 C 盘系统盘**（2026-10-05 用户要求），也不要放在 M: 这类网络盘——模型加载速度是本次要记录的测量项，网络盘会直接污染它。不要把路径写成 WSL 的 `/home` 或 `/mnt` 路径。具体盘符可以改，但后续所有变量必须一致。

先输入 `03_resources`：

```powershell
$Models = 'F:\AI\models'
$DitDownload = Join-Path $Models 'downloads\lingbot-world-v2-1.3b-causal-fast'
$Dit = $DitDownload
$DitTransformers = Join-Path $Dit 'transformers'
$Assets = Join-Path $Models 'lingbot-world-v2-14b-assets'

New-Item -ItemType Directory -Force $DitDownload,$Assets | Out-Null
Get-PSDrive -PSProvider FileSystem |
  Select-Object Name,Root,Free
```

### 5.2 安装 Hugging Face CLI

```powershell
Set-Location $Root
& $Py -m pip install 'huggingface_hub[cli]'
$HfCandidates = @(
  (Join-Path $Venv 'Scripts\hf.exe'),
  (Join-Path $Venv 'Scripts\huggingface-cli.exe')
)
$Hf = $HfCandidates |
  Where-Object { Test-Path -LiteralPath $_ } |
  Select-Object -First 1
if (-not $Hf) {
  throw 'Neither hf.exe nor huggingface-cli.exe was found in the venv'
}
Write-Host "hf_cli=$Hf"
& $Hf --help
```

如果 CLI 的实际入口名称或参数在当前版本发生变化，先保存 `--help` 和版本信息，按当前官方 CLI 文档调整，不要静默改用另一套下载工具。

如果仓库要求登录，暂停 OBS 后手动完成登录；不要在录屏或命令历史中放 token。

### 5.3 下载 1.3B DiT

固定使用已核对过的 Hugging Face revision `7e36a5f919f86cb4255cc9bfc30adb44963fbde1`。官方 README 的资源布局是：checkpoint 根目录下包含 `transformers` 子目录。为避免 `$Dit`、下载目录和 loader 目录混淆，本手册让 `$Dit` 直接指向隔离下载目录；下载完成后应当在 `$Dit\transformers` 下看到权重文件。若当前 CLI 实际把文件放在其他层级，先记录目录树和 CLI 版本，再按实际 loader 要求重新设置变量或调整下载命令，不要手工搬运权重改变证据：

```powershell
$DitDownload = Join-Path $Models 'downloads\lingbot-world-v2-1.3b-causal-fast'
$Dit = $DitDownload
$DitTransformers = Join-Path $Dit 'transformers'
New-Item -ItemType Directory -Force $DitDownload | Out-Null

& $Hf download `
  robbyant/lingbot-world-v2-1.3b-causal-fast `
  --revision '7e36a5f919f86cb4255cc9bfc30adb44963fbde1' `
  --local-dir $DitDownload

Get-ChildItem -LiteralPath $DitDownload -Recurse -File |
  Select-Object Length,FullName
```

下载完成后，`$Dit` 应保持为 `$DitDownload`，并确认 loader 所需的 index 在 `$Dit\transformers`：

```powershell
$DitTransformers = Join-Path $Dit 'transformers'
Test-Path -LiteralPath (Join-Path $DitTransformers 'model.safetensors.index.json')
```

如果 index 不在该位置，先记录 CLI 版本、完整目录树和 loader 报错，再调整下载命令或变量；不要手工移动权重改变证据。

### 5.4 下载共享 T5/VAE/tokenizer

固定使用已核对过的 Hugging Face revision `5c33dd40b213598c418fd25bff30fdbd23fd38a7`。下面的 include 组合是按照项目当前资源文件名整理的候选命令，用来避免无意下载完整的 14B DiT。不同版本的 Hugging Face CLI 对重复 `--include` 的解析可能不同，执行前可查看 `& $Hf download --help`。

```powershell
& $Hf download `
  robbyant/lingbot-world-v2-14b-causal-fast `
  --revision '5c33dd40b213598c418fd25bff30fdbd23fd38a7' `
  --local-dir $Assets `
  --include 'Wan2.1_VAE.pth' `
  --include 'models_t5_umt5-xxl-enc-bf16.pth' `
  --include 'google/umt5-xxl/*'
```

如果当前 CLI 不接受多个 `--include`，不要把整个 14B 包直接下载来“试试看”。保留 CLI 版本、帮助输出和报错，先确认当前官方等价语法。不要把 14B DiT 当作 1.3B DiT 的必需文件。

### 5.5 核对目录和文件

下载后，用 Windows PowerShell 检查实际目录，不要凭下载器显示的“完成”推断 loader 一定能加载：

```powershell
Get-ChildItem -LiteralPath $Dit -Recurse -File |
  Sort-Object Length |
  Select-Object Length,FullName -Last 20

Get-ChildItem -LiteralPath $Assets -Recurse -File |
  Sort-Object FullName |
  Select-Object Length,FullName

$Required = @(
  (Join-Path $DitTransformers 'model.safetensors.index.json'),
  (Join-Path $Assets 'Wan2.1_VAE.pth'),
  (Join-Path $Assets 'models_t5_umt5-xxl-enc-bf16.pth')
)
$Required | ForEach-Object {
  [pscustomobject]@{Path=$_; Exists=Test-Path -LiteralPath $_}
}
```

还要确认六个 DiT 分片和 tokenizer 文件都存在：

```powershell
$DitShardNames = 1..6 | ForEach-Object {
  'model-{0:D5}-of-00006.safetensors' -f $_
}
$TokenizerNames = @(
  'special_tokens_map.json',
  'spiece.model',
  'tokenizer.json',
  'tokenizer_config.json'
)

$Checks = foreach ($Name in $DitShardNames) {
  $Path = Join-Path $DitTransformers $Name
  [pscustomobject]@{Path=$Path; Exists=Test-Path -LiteralPath $Path}
}
$Checks += foreach ($Name in $TokenizerNames) {
  $Path = Join-Path $Assets (Join-Path 'google\umt5-xxl' $Name)
  [pscustomobject]@{Path=$Path; Exists=Test-Path -LiteralPath $Path}
}
$Checks | Format-Table -AutoSize
```

如果上表任何 `Exists` 为 `False`，不要继续运行生成；先保留实际路径、CLI 版本和下载输出，进入 `07_error`。

项目记录的 1.3B DiT 六个 safetensors 分片总磁盘占用约 6.84 GB；这是历史文件占用参考，不是本次下载耗时、总资源需求或 Windows 可用空间承诺。共享资源实际占用以本次 `Get-ChildItem` 结果为准。

如需核对完整文件的 SHA-256，使用 Windows 原生命令。下面的哈希来自历史 `model.json`，只用于与本次落地文件逐一比对：

```powershell
$ExpectedHashes = @{
  'model.safetensors.index.json' = 'b0409d663b57810af19443c9e8d8dde43320193c8dbb979d86f6618102922e42'
  'model-00001-of-00006.safetensors' = '4169eaf504fc63c235f4b66c95887951ecd71ba4ca9492e8528b6709d63ed9b2'
  'model-00002-of-00006.safetensors' = 'e6745d1e600f697f2285ca435de09c49d2082303b7f9a2bb39003fc87b354d2f'
  'model-00003-of-00006.safetensors' = '20f9b226fcfcfb4dead5c1e3ff1b77da182787442ebabfdaf23d3c68aca44ceb'
  'model-00004-of-00006.safetensors' = '5b5c18cc18a4de976002f45777f59b4d27d30786c6db94e134d0af5a031f5272'
  'model-00005-of-00006.safetensors' = '089575f86c3c62e12566a79c5e0afd663415aa4376e193b45ee2bb2ac65a9cbe'
  'model-00006-of-00006.safetensors' = 'c0d3d8643d07b6d6e26d614f80cf3538a562f575937a759c64a71d5575f2f915'
  'Wan2.1_VAE.pth' = '38071ab59bd94681c686fa51d75a1968f64e470262043be31f7a094e442fd981'
  'models_t5_umt5-xxl-enc-bf16.pth' = '7cace0da2b446bbbbc57d031ab6cf163a3d59b366da94e5afe36745b746fd81d'
  'special_tokens_map.json' = '7b8a9f5040adb67b5805abdfd42c1f8d0f3d0e711f10726580eb3789cd0ad61d'
  'spiece.model' = 'e3909a67b780650b35cf529ac782ad2b6b26e6d1f849d3fbb6a872905f452458'
  'tokenizer.json' = '6e197b4d3dbd71da14b4eb255f4fa91c9c1f2068b20a2de2472967ca3d22602b'
  'tokenizer_config.json' = 'ed9a3a8b0faa71a70a32847e0435fe036e6e112d4df4edb7bb48a921e344dc05'
}

$HashPaths = @{}
$HashPaths['model.safetensors.index.json'] = Join-Path $DitTransformers 'model.safetensors.index.json'
foreach ($Name in $DitShardNames) {
  $HashPaths[$Name] = Join-Path $DitTransformers $Name
}
$HashPaths['Wan2.1_VAE.pth'] = Join-Path $Assets 'Wan2.1_VAE.pth'
$HashPaths['models_t5_umt5-xxl-enc-bf16.pth'] = Join-Path $Assets 'models_t5_umt5-xxl-enc-bf16.pth'
foreach ($Name in $TokenizerNames) {
  $HashPaths[$Name] = Join-Path $Assets (Join-Path 'google\umt5-xxl' $Name)
}

$HashResults = foreach ($Name in $ExpectedHashes.Keys) {
  $Path = $HashPaths[$Name]
  if (-not (Test-Path -LiteralPath $Path)) {
    [pscustomobject]@{
      File = $Name
      Match = $false
      SHA256 = 'MISSING'
    }
    continue
  }
  $Actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
  [pscustomobject]@{
    File = $Name
    Match = ($Actual -eq $ExpectedHashes[$Name])
    SHA256 = $Actual
  }
}

$HashResults | Format-Table -AutoSize
$HashMismatches = @($HashResults | Where-Object { -not $_.Match })
if ($HashMismatches.Count -gt 0) {
  throw "SHA-256 mismatch or missing model files; stop before generation"
}
```

### 5.6 资源校验的停止条件

如果目录表中任何 `Exists` 为 `False`，或 SHA-256 校验显示 `Match=False`，不要继续运行生成；先保留实际路径、CLI 版本、下载输出和校验结果，进入 `07_error`。

## 6. 候选单进程单卡路径（Windows 原生未验证）

### 6.1 先确认输入动作文件

`causal_fast` 的历史单卡路径使用仓库自带的 `examples\03`。在 PowerShell 中输入 `05_command`，然后执行：

```powershell
Set-Location $Root
$Image = Join-Path $Root 'examples\03\image.jpg'
$ActionPath = Join-Path $Root 'examples\03'

Get-Item -LiteralPath $Image
Get-ChildItem -LiteralPath $ActionPath -File |
  Select-Object Name,Length,FullName
```

历史成功路径需要动作目录；其中应能看到 `poses.npy` 和 `intrinsics.npy`。项目曾记录过省略 `--action_path` 后在采样前退出，因此本次命令不能省略该参数。虽然上游 parser 的默认值可能显示为 optional，但是否能进入这条 causal-fast 路径要由实际 loader 校验决定。

### 6.2 准备输出目录和参数

```powershell
$OutputDir = 'F:\AI\lingbot-output'
$Out = Join-Path $OutputDir 'lingbot-13f.mp4'
New-Item -ItemType Directory -Force $OutputDir | Out-Null

Write-Host "root=$Root"
Write-Host "dit=$Dit"
Write-Host "assets=$Assets"
Write-Host "image=$Image"
Write-Host "action_path=$ActionPath"
Write-Host "save_file=$Out"
git -C $Root rev-parse HEAD
```

### 6.3 执行 13 帧单卡命令

下面的参数保留了历史成功 run 的核心设置：`i2v-1.3B`、`causal_fast`、`480*832`、13 帧、`t5_cpu`、模型卸载、dtype 转换、18/6 attention 参数和 seed 42。

这是**原生 Windows 待验证候选**，不是已经在 Windows 上跑通的命令。使用参数数组可以减少 PowerShell 续行和引号错误：

```powershell
Set-Location $Root

$RunArgs = @(
  'generate.py',
  '--task', 'i2v-1.3B',
  '--infer_mode', 'causal_fast',
  '--size', '480*832',
  '--frame_num', '13',
  '--ckpt_dir', $Dit,
  '--assets_dir', $Assets,
  '--image', $Image,
  '--action_path', $ActionPath,
  '--t5_cpu',
  '--convert_model_dtype',
  '--offload_model', 'True',
  '--local_attn_size', '18',
  '--sink_size', '6',
  '--base_seed', '42',
  '--prompt', 'A serene lakeside scene with a lone tree standing in calm water, surrounded by distant snow-capped mountains under a bright blue sky with drifting white clouds.',
  '--save_file', $Out
)

& $Py @RunArgs
$ModelExitCode = $LASTEXITCODE
Write-Host "model_exit_code=$ModelExitCode"
```

**退出码必须紧接着保存。** 保存 `$ModelExitCode` 之后，才能执行播放、`Get-Item` 或 `ffprobe`。不要执行其他 PowerShell 命令后再读取 `$LASTEXITCODE`，否则它可能已经被其他命令覆盖。

运行期间输入 `06_loading`，保留真实日志和等待过程。历史 WSL run 的耗时、显存采样和 wrapper 输出不能复制到 Windows 录屏中；如果本次没有单独的显存监控，就如实说“未测量”，不要从截图目测显存。

如果程序直接报参数、路径、动作文件或导入错误，保留完整上下文，输入 `07_error`。不要先把 13 改成 5，也不要同时改变分辨率、模型目录和依赖版本。

### 6.4 成功判定和真实播放

只有模型命令退出码、输出文件和播放都通过，才进入 `08_result`。先启动真实输出文件：

```powershell
if ($ModelExitCode -ne 0) {
  Write-Warning "model command failed; do not call this a successful result"
}

if (-not (Test-Path -LiteralPath $Out)) {
  Write-Warning "output file not found: $Out"
} else {
  Start-Process -FilePath $Out
}
```

可以用 Windows 默认播放器、VLC 或 OBS Media Source 播放，但必须播放本次命令实际生成的 MP4。不能只显示文件名、目录列表或 `99_done` 静帧来代替动态结果。

### 6.5 Windows 结构化验收

播放器启动后，输入 `09_verify`。先确认 `$ModelExitCode` 仍是前面保存的模型退出码：

```powershell
Write-Host "model_exit_code=$ModelExitCode"

if (-not (Test-Path -LiteralPath $Out)) {
  throw "output file does not exist: $Out"
}

Get-Item -LiteralPath $Out |
  Format-List FullName,Length,LastWriteTime

Get-FileHash -LiteralPath $Out -Algorithm SHA256

ffprobe.exe -v error `
  -select_streams v:0 `
  -show_entries stream=width,height,nb_frames,avg_frame_rate,duration `
  -of json `
  $Out
```

如果 `ffprobe.exe` 不在 `PATH`，改用已安装的 Windows `ffprobe.exe` 完整路径，并在录屏中说明路径来源。`file exists` 不等于生成成功；至少保留退出码、非零文件大小、SHA-256 和 `ffprobe` JSON。

历史 LB-HEAD-001 的参考结果是 832×464、13 帧、16/1 fps、0.8125 秒。本次 Windows 输出的尺寸、帧数、帧率、时长和耗时必须来自本次日志及 `ffprobe`，不能预先照读这个数字。

## 7. 失败处理和可选扩展

### 7.1 第一次失败时保留什么

任何失败都先输入 `07_error`，保留：

- 完整实际命令和参数变量；
- 从第一条错误到 traceback 末尾的连续 PowerShell 画面；
- `nvidia-smi`、Windows、Python、PyTorch/CUDA/`flash-attn` 版本；
- 仓库 commit；
- 模型目录实际文件列表和剩余磁盘空间；
- `$ModelExitCode` 或安装命令的退出码；
- 失败发生在安装、导入、下载、加载、采样还是写文件阶段。

不要删掉失败录屏，也不要把失败文件重命名成成功。若是 OOM，不要立刻连续改十个参数；先保存现场，后续再决定是否做只改变一个变量的复测。

### 7.2 本项目已有的历史边界

以下是历史项目记录，可用于解释实验设计，但不是 Windows 已验证结果：

- 缺少 `--action_path`：历史 run 在采样前退出；本次使用 `examples\03`；
- `--frame_num 5`：历史 run 在 `chunk_size=4` 下产生无效时间维；本路径已观察到的最短合法长度是 13（`4n+1`）；
- 21 帧：历史代码路径可能收回到 13 帧；下一档实际变长的已测值是 29 帧；
- 旧 WSL run 的峰值显存和墙钟不能套用到本次 RTX 3060 Laptop Windows run。

### 7.3 只有 13 帧成功以后才做 29 帧

如果 13 帧在本次 Windows 环境中成功，且仍需要一个扩展结果，再另开一个清楚标识的 run，只改变 `--frame_num 29`，其他参数、输入图、动作路径、seed 和权重路径保持不变。不要覆盖 13 帧结果。

没有必要为本期教程先测试更高分辨率、361 帧或官方 4 卡命令。官方 1.3B README 示例是 4 GPU 多进程路径；`generate.py` 的单进程路径不会自动变成多卡路径。不要把 `torchrun --nproc_per_node=4`、`--dit_fsdp`、`--t5_fsdp` 或 `--ulysses_size 4` 改写成单卡 Windows 已验证命令。

## 8. 录屏交回后的处理约定

你把原始 OBS 录屏交回后，我会按以下顺序处理：

1. 只读检查原文件是否稳定可读，记录 SHA-256、分辨率、编码、帧率、总帧数和真实 PTS；
2. 按 marker 定位 `05_command`、`06_loading`、`08_result`、`09_verify` 和 `07_error`；
3. 原始录屏不改写，抽帧、代理和剪辑只写入 `F:\Temp`；
4. 生成素材清单，记录源文件路径、源 SHA、起止时间、原始帧数、倍速、用途和是否证据；
5. 连续安装、加载和运行过程使用真实视频；长等待可加速并明示时间轴压缩；
6. 命令、错误、版本和验收若在视频中不可读，只采用同一次 run 的原生截图，不重建截图；
7. 结果用实际生成视频展示，不用 `99_done` 静帧冒充动态结果；
8. 派生片段、裁切、放大、字幕卡和概念素材标为 `is_evidence=false`；真实原始截图/录屏才可标为 `real_capture`/`is_evidence=true`。

同一真实画面最多复用两次；不循环操作画面填时长；裁切使用整数坐标，避免文字抖动和亚像素模糊。最终成片仍使用完整 1920×1080、16:9 画面，不预留独立字幕带。

## 9. 本次录屏结束时的口头总结模板

输入 `99_done` 后，按实际情况读下面的模板，不要照读未发生的成功：

> 本次在 [GPU 完整名称]、[显存]、Windows 11 原生 Python 环境、[系统内存] 上，使用 `lingbot-world-v2` commit [commit] 和 [实际软件版本]，尝试运行 `i2v-1.3B causal_fast`。PyTorch CUDA gate 为 [通过/失败]，`flash_attn` gate 为 [通过/失败]，最小 13 帧运行结果为 [成功/失败/未进入运行]。如果成功，输出为 [实际尺寸]、[实际帧数]、[实际帧率]，结构化验收见 `ffprobe`；如果失败，完整错误和环境记录已保留。这个结果只证明本次具体机器和版本，不外推到其他显卡型号、WSL、其他 Windows 版本、720p/60fps、实时生成或商业使用。

如果 `flash_attn` 在安装阶段失败，必须明确说“本次没有进入模型推理”，不要说成模型显存不够或 Windows 已不支持。

## 10. 事实源、许可和素材标签

本手册对应的事实源：

- `01-实验/2026-09-26_lingbot-world-1.3b-6gb/README.md`
- `01-实验/2026-09-26_lingbot-world-1.3b-6gb/results/LB-HEAD-001.md`
- `01-实验/2026-09-26_lingbot-world-1.3b-6gb/environment.json`
- `01-实验/2026-09-26_lingbot-world-1.3b-6gb/model.json`
- `02-内容工厂/output/bench-note-lingbot-world-1.3b-v1.md`
- 固定 commit 的官方 README、`requirements.txt` 和 `generate.py`

1.3B 模型、共享资源、代码和依赖分别受其许可证约束。当前模型和代码边界包含 CC BY-NC-SA 4.0；教程不提供商业使用授权，也不替用户判断具体发布行为是否符合许可证。

素材标签遵循项目规则：

| 素材 | `media_origin` | `is_evidence` |
|---|---|---:|
| 本次 Windows 原生真实录屏、同一次运行原生截图 | `real_capture` | `true` |
| 根据本次真实 metrics/日志绘制的图表 | `rendered_chart` | `true` |
| 后期剪辑片段、裁切、字幕卡、概念图/视频 | `derived` 或 `generated` | `false` |

在本次 Windows 原生运行和录屏完成前：

- 不创建新的 `videoctl` 生产任务；
- 不付费生成配音或视频；
- 不公开发布新的部署教程；
- 不修改已公开的 LingBot 旧 job、旧事件或旧素材 lineage；
- 不把历史 WSL 录屏剪辑成 Windows 原生成功证据。

本次实验完成后，先核对原始录屏和本次真实实验记录，再另行决定脚本、配音、字幕、成片和发布流程。
