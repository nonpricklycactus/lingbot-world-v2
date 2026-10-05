# LingBot-World 1.3B 部署：6GB 笔记本 Windows 原生跑通图生视频

中文图文**候审稿**（13 页）。用户审核通过后，才据它写录音稿；本目录自己不做配音、成片或发布。

[图文预览](preview.html) · [PDF](lingbot-deploy-windows.zh.pdf) · [素材出处](asset-sources.json) · [事实绑定](report-facts.json)

## 这一版讲了什么

一台 RTX 3060 Laptop（6 GB 显存）、64 GB 内存的 Windows 11 笔记本，**不装系统级 Python、不动系统环境**，把 `lingbot-world-v2` 的 `i2v-1.3B / causal_fast` 单卡 13 帧路径跑通。全部文件落在 `F:\AI` 一个目录里，回滚就是删目录。

页面顺序：封面 → 这次要回答什么 → 机器与起点 → 代码与虚拟环境 → 下载提速 → 依赖与 CUDA 闸门 → flash-attn 卡点 → SDPA 回退补丁 → 权重与 13 项校验 → 13 帧命令与耗时 → 命令参数逐条 → 结果 → 代价与边界。

## 事实口径（写数字前先看这里）

| 项 | 值 | 口径 |
|---|---|---|
| 生成段耗时 | 约 763 秒（12 分 43 秒） | 模型日志 16:55:29 → 17:08:12/13，含模型加载之后的全过程；不是纯采样 |
| 显存 | 运行中采样到 4996 MiB / 6144 MiB | **单次采样**，不是连续峰值；不拿它下"更省显存"的结论 |
| 输出 | 832 × 464 · 13 帧 · 16 fps · 0.8125 秒 · 1,273,344 字节 | ffprobe 与文件系统实测 |
| 输出 SHA-256 | `897c908d04950630a89ac88f95e3831c3327f76e4be796af0d2b507cf6d66b8f` | 定稿时本机重算 |
| 权重校验 | 13 / 13 匹配 | 定稿时本机重算，对照手册 §5.5 的期望哈希 |

不声称：作者本人逐字敲入（本期录屏是在虚拟显示器上以程序化输入完成的）、720p / 60fps、多卡、其他显卡、实时生成、商业用途。补丁是**本机实验分支**，不是官方支持路径。对外只写本次实测，不写内部参考记录。

## 素材与来源

- 原始录屏与结果：`07-素材/世界模型部署相关/录屏-20261005/`（`raw/` 17 段、`result/lingbot-13f.mp4`、`patch/`、`logs/`）
- 用户本机截图：`07-素材/世界模型部署相关/基础信息01-03.png`（录制当天 12:10 的只读实测；第 3 页的 nvidia-smi 图取自 `基础信息01.png`，已裁掉命令行提示符，画面里不含用户名）
- 手册：`02-内容工厂/output/lingbot-world-1.3b-deployment-manual-v1.md`
- 报告里 12 张图全部是录屏抽帧（整数坐标裁切，未放大、未重绘），逐张的来源与 SHA-256 见 `asset-sources.json`

## 构建与复核（从仓库根目录运行）

```bash
node 02-内容工厂/output/bench-note-lingbot-deploy-windows-v1/build-report.cjs     # 生成 panels/ + page-plan.json + .zh.md（内含事实断言）
node tools/benchnote/cli.cjs check  02-内容工厂/output/bench-note-lingbot-deploy-windows-v1.zh.md
node tools/benchnote/cli.cjs render 02-内容工厂/output/bench-note-lingbot-deploy-windows-v1.zh.md 02-内容工厂/output/bench-note-lingbot-deploy-windows-v1
node 02-内容工厂/output/bench-note-lingbot-deploy-windows-v1/package-report.cjs   # 面板几何 QA + preview.html
python 02-内容工厂/output/bench-note-lingbot-deploy-windows-v1/export-pdf.py 02-内容工厂/output/bench-note-lingbot-deploy-windows-v1 02-内容工厂/output/bench-note-lingbot-deploy-windows-v1/qa/pdf-raster
node 02-内容工厂/output/bench-note-lingbot-deploy-windows-v1/qa-fill.cjs          # 各页余量

# 去 AI 味复核（humanizer-zh，仓库内 .claude/skills/humanizer-zh/）
python .claude/skills/humanizer-zh/tests/check_structure.py \
  02-内容工厂/output/bench-note-lingbot-deploy-windows-v1/qa/prose-zh.before.md \
  02-内容工厂/output/bench-note-lingbot-deploy-windows-v1/qa/prose-zh.md
```

`build-report.cjs` 在出图的同时把每页的段落、步骤说明和表格按页序抽成 `qa/prose-zh.md`，改稿时对着它做文字复核，保证复核对象和出图内容同源；这一版的过程记录在 `qa/humanizer-review.json`。

## 本版 QA 结论

- `check`：25 块 → 13 页，0 预警 0 错误
- `render`：两次渲染的 13 张 PNG **逐字节一致**
- `package-report.cjs`：13 页几何检查通过，无内部溢出、无面板溢出、图片全部解码
- `export-pdf.py`：13 页、每页嵌入像素与 page-*.png 完全相同；PDF SHA-256 `22afe6b1e5d03ff67fb4e4924c91706494e4bae43834f8e7d7d2384461be8d77`
- 去 AI 味：humanizer-zh 四轮（套话尾巴、过度断言「必然失败」、会原样显示的反引号、中文直引号、图注里「真实录屏」这类一眼可见的强调、「真跑 / 实录 / 原样保留 / 照实记录」这类词；按用户要求删掉原「一页复用清单」页；参数改成一条一行、不再几个参数挤在一格里）；表格数据、代码块、数字与口径逐字未动，前后对照见 `qa/humanizer-review.json`
- 审批状态：`pending`（本目录没有 06-review 记录）

## 已知缺口（照实留档）

1. `step-10-verify.mp4` 里的 SHA-256 校验命令写坏了，屏幕上只有 `Get-FileHash` 的报错；报告里的 13/13 是定稿时另行重算的。
2. 模型退出码没能从终端回读。
3. 没有连续显存采样，只有一次运行中读数。
4. 手册 §6.3/§6.5 目前仍只有"计划命令 + 早前实验的基线"，本次真实结果还没写回手册。

## 状态

本目录是候审稿，`is_evidence` 规则按项目约定：页内录屏抽帧为 `real_capture`，输出视频抽帧为 `real_capture`，版式文字与图示为 `derived`。等待用户审核；通过前不生成录音稿，也不公开发布。
