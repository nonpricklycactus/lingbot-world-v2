# LingBot 部署分步执行器

本期「LingBot 部署教程」（Windows 11 原生）用的操作入口。手册负责口径和判据，这里只负责三件事：

1. 把每一步真正要执行的命令**原样打印出来**，方便事后整理教程网页；
2. 执行并把输出留成日志；
3. 输出**默认脱敏**，避免把本机信息带进公开页面。

手册：[`02-内容工厂/output/lingbot-world-1.3b-deployment-manual-v1.md`](../../02-内容工厂/output/lingbot-world-1.3b-deployment-manual-v1.md)

## 怎么用

```text
双击 run-deploy-steps.cmd            进入菜单，选编号执行
run-deploy-steps.cmd -Step 0         只跑第 0 步（适合分批录制）
run-deploy-steps.cmd -NoRedact       关闭脱敏（默认开启，不建议）
run-deploy-steps.cmd -Yes            跳过长步骤的确认
```

也可以直接调 PowerShell：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools\lingbot-deploy\deploy-steps.ps1 -Step 0
```

`-ExecutionPolicy Bypass` 只作用于这一次进程，**不修改**系统或用户级执行策略。

## 步骤与手册对应

| 编号 | 内容 | 手册 |
|---|---|---|
| 0 | 环境自检（基础工具 + uv） | §2.1 |
| 1 | 硬件与系统记录 | §2.2 |
| 2 | 获取代码并固定 commit | §3 |
| 3 | 建立 venv（uv，零安装） | §4.1 |
| 4 | 安装官方依赖 `requirements.txt` | §4.2 |
| 5 | PyTorch CUDA gate | §4.3 |
| 6 | 安装 flash-attn（预编译 wheel，分支 A） | §4.4 |
| 7 | 安装 Hugging Face CLI | §5.2 |
| 8 | 下载 1.3B DiT 权重 | §5.3 |
| 9 | 下载共享 T5 / VAE / tokenizer | §5.4 |
| 10 | 资源目录与 SHA-256 核对 | §5.5 |
| 11 | 检查输入动作文件 `examples\03` | §6.1 |
| 12 | 执行 13 帧单卡生成 | §6.3 |
| 13 | 输出验收（文件 + SHA-256 + ffprobe） | §6.5 |
| 99 | 自检：脱敏与日志 | 附录 |

第 4、8、9、12 步耗时较长或下载量大，会先要求确认；其余步骤是只读或可重复的。

## 脱敏规则

输出在写屏和写日志之前统一过一遍替换，命中项包括：

| 类型 | 处理 |
|---|---|
| 本机用户名（含 `C:\Users\<用户名>`） | `<user>` |
| 本机机器名 | `<pc>` |
| Hugging Face / GitHub / OpenAI 风格令牌，`token=`、`api_key=`、`password=`、`secret=` 等键值 | `hf_***`、`gh_***`、`sk-***`、`key=***` |
| 邮箱 | `<email>` |
| MAC 地址 | `<mac>` |
| Windows SID | `<sid>` |

第 99 步可以把样例字符串过一遍，直接看到脱敏效果。**脱敏只处理脚本能看见的输出**：`Read-Host` 里手输的内容、OBS 录到的其他窗口、以及 PowerShell 自己的提示符不在范围内，录制时仍要按手册 §1.1 控制取景。

## 日志

每次运行写一份日志到 `F:\Temp\lingbot-deploy-logs\run-<时间戳>.log`（临时区，按项目约定用完即清）。要把它写进教程网页前，先通读一遍再复制；确认无敏感内容后再转存到项目目录。

## 边界

- 脚本只做手册里写过的步骤，不安装系统级 Python、不改注册表、不改系统 PATH、不修改服务或定时任务。
- 缓存目录固定指向 `F:\AI\runtime`（`UV_CACHE_DIR` / `PIP_CACHE_DIR`），避免几个 GB 的 wheel 落到 C 盘用户目录。
- 路径与固定值集中在 `deploy-steps.ps1` 顶部的 `$Cfg`；换盘或换目录只改那里，并同步手册。
- 第 6 步的 wheel 由使用者提供：脚本只负责核对哈希、安装和导入验证，不替使用者下载或判断来源。
- 脚本不判断结果是否有效：退出码、文件、哈希和 `ffprobe` 仍按手册 §6.4/§6.5 人工核对。
