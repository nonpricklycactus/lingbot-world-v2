'use strict';
// LingBot-World 1.3B · Windows 11 原生部署实录  ——  图文构建器
// 事实源：02-内容工厂/output/lingbot-world-1.3b-deployment-manual-v1.md（本机实测段）
//         07-素材/世界模型部署相关/录屏-20261005/（原始录屏、失败日志、补丁）
//         01-实验/2026-09-26_lingbot-world-1.3b-6gb/（同一模型早前的实验记录）
//         本次独立复核：模型文件 SHA-256、输出 MP4 字节与哈希
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto'), assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../../..');
const out = __dirname;
const assetsRel = '02-内容工厂/output/bench-note-lingbot-deploy-windows-v1/assets';
const hash = (p) => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// ── 事实断言：凡是报告里写死的数字，先在这里对回原始文件 ──────────────────────
const F = {
  outMp4: 'F:/AI/lingbot-output/lingbot-13f.mp4',
  repo: 'F:/AI/lingbot-world-v2',
  models: 'F:/AI/models',
  wheels: 'F:/AI/runtime/wheels/torch-2.11.0+cu128-cp312-cp312-win_amd64.whl',
  manual: path.join(root, '02-内容工厂/output/lingbot-world-1.3b-deployment-manual-v1.md'),
  faLog: path.join(root, '07-素材/世界模型部署相关/录屏-20261005/logs/flashattn-install-failure.log'),
  patchDiff: path.join(root, '07-素材/世界模型部署相关/录屏-20261005/patch/attention-patch.diff'),
  patchOrig: path.join(root, '07-素材/世界模型部署相关/录屏-20261005/patch/attention.py.orig'),
  patchNew: path.join(root, '07-素材/世界模型部署相关/录屏-20261005/patch/attention.py.patched.py'),
};
const stat = (p) => ({ bytes: fs.statSync(p).size, sha256: hash(p) });
const outMp4 = stat(F.outMp4);
assert.equal(outMp4.bytes, 1273344, '输出 MP4 字节数变了');
assert.equal(outMp4.sha256, '897c908d04950630a89ac88f95e3831c3327f76e4be796af0d2b507cf6d66b8f', '输出 MP4 哈希变了');
assert.equal(stat(F.patchOrig).sha256, 'b6f57f0a9bb36164cdccc3f03345f287f95dc5703bbc25cf1aaddaff946b8500', '原版 attention.py 哈希变了');
assert.equal(stat(F.patchNew).sha256, 'd0efbca939f07b8948e49cf44e43834d388e1b5f6efd0f4d37f7141063511558', '补丁版 attention.py 哈希变了');
assert.equal(stat(F.patchDiff).bytes, 5247, '补丁 diff 字节数变了');
// diff 口径：git diff -U3 的整份行数（含上下文、@@ 与文件头），与 VERIFY.txt 记的"差异 125 行"一致
const rawDiff = fs.readFileSync(F.patchDiff, 'utf8');
const diffLines = rawDiff.endsWith('\n') ? rawDiff.split('\n').length - 1 : rawDiff.split('\n').length;
assert.equal(diffLines, 125, 'diff 改动行数变了');
const reqTxt = fs.readFileSync(path.join(F.repo, 'requirements.txt'), 'utf8');
assert.ok(!/einops/i.test(reqTxt), 'requirements.txt 里已经出现 einops，需改口径');
const modelFast = fs.readFileSync(path.join(F.repo, 'wan/modules/model_fast.py'), 'utf8');
assert.ok(/from einops import rearrange/.test(modelFast), 'model_fast.py 里没有 einops import，需改口径');
const patchedAttn = fs.readFileSync(path.join(F.repo, 'wan/modules/attention.py'), 'utf8');
assert.ok(/_sdpa_varlen_attention/.test(patchedAttn), '仓库里的 attention.py 不含 SDPA 回退实现');
const faLog = fs.readFileSync(F.faLog, 'utf8');
for (const s of ['Precompiled wheel not found', 'HTTP Error 404', 'FileNotFoundError: [WinError 2]',
  'The detected CUDA version (%s) mismatches the version that was used to compile', 'ERROR: Failed building wheel for flash-attn', "No module named 'flash_attn"])
  assert.ok(faLog.includes(s), '失败日志缺少: ' + s);
assert.equal(fs.statSync(F.faLog).size, 26771, 'flash-attn 失败日志字节数变了');
assert.equal(hash(F.faLog), '23abbd74c8f06548e716618f9068c55bd15ee5f664ef3d81dbb7327238680f36', 'flash-attn 失败日志哈希变了');
assert.equal(fs.statSync(F.wheels).size, 2753189216, 'torch 轮子字节数变了');
const ditDir = path.join(F.models, 'downloads/lingbot-world-v2-1.3b-causal-fast');
const ditFiles = fs.readdirSync(ditDir).filter((f) => f.endsWith('.safetensors') || f.endsWith('.json'));
assert.equal(ditFiles.length, 7, 'DiT 目录文件数变了');
assert.equal(ditFiles.reduce((a, f) => a + fs.statSync(path.join(ditDir, f)).size, 0), 6838201925, 'DiT 总字节数变了');
const assetsDir = path.join(F.models, 'lingbot-world-v2-14b-assets');
assert.equal(fs.statSync(path.join(assetsDir, 'models_t5_umt5-xxl-enc-bf16.pth')).size, 11361920418, 'T5 字节数变了');
assert.equal(fs.statSync(path.join(assetsDir, 'Wan2.1_VAE.pth')).size, 507609880, 'VAE 字节数变了');

// ── 版式：沿用已获批的本机实验报告样式（米色纸面 / 大题面 / 短点评） ─────────
const css = [
  '.report-panel,.report-panel *{box-sizing:border-box;font-family:"Microsoft YaHei",sans-serif!important}.report-panel{color:#292824}.report-panel p,.report-panel figure{margin:0}.report-panel h1,.report-panel h2,.report-panel h3{margin:0}.report-panel h1:before,.report-panel h2:before{content:none!important}',
  '.report-panel .eyebrow{font-size:21px;letter-spacing:1px;color:#8e4937;font-weight:700;padding-bottom:14px;border-bottom:2px solid #a99b83}.report-panel .title{font-size:45px;line-height:1.3;color:#8e4937;font-weight:800}.report-panel .lead{font-size:29px;line-height:1.6}.report-panel .text{font-size:27px;line-height:1.62}.report-panel .note{font-size:22px;line-height:1.58;color:#766c5e}.report-panel .footer{font-size:19px;line-height:1.55;color:#817765;border-top:1px solid #cfc5b3;padding-top:14px;margin-top:auto}',
  '.report-panel .two{display:grid;grid-template-columns:1fr 1fr;gap:34px}.report-panel .split{display:grid;grid-template-columns:1fr 1fr;gap:32px;border-top:2px solid #a99b83;padding-top:20px}.report-panel .split>div+div{border-left:1px solid #cfc5b3;padding-left:32px}.report-panel .label{font-size:23px;color:#766c5e;line-height:1.5;margin-bottom:8px}.report-panel .num{font-size:66px;line-height:1.1;font-weight:800;letter-spacing:-2px}.report-panel .unit{font-size:25px;letter-spacing:0;font-weight:400}.report-panel .green{color:#5c713e}.report-panel .rust{color:#9b4938}.report-panel .big{font-size:36px;font-weight:700;line-height:1.45}',
  '.report-panel .question{padding:12px 0 12px 22px;border-left:4px solid #9b4938;font-size:28px;line-height:1.58}.report-panel .observation{padding-top:18px;border-top:2px solid #9b4938;font-size:27px;line-height:1.6}',
  '.report-panel table{width:100%;border-collapse:collapse;table-layout:fixed;margin:0;font-size:25px;line-height:1.45}.report-panel th{font-size:22px;color:#766c5e;font-weight:400;text-align:left;padding:12px 10px;border-bottom:2px solid #a99b83}.report-panel td{padding:14px 10px;border-bottom:1px solid #d7cfbf;text-align:left;vertical-align:top;overflow-wrap:anywhere}.report-panel td:first-child{color:#766c5e}.report-panel .compact td{padding:11px 10px}.report-panel .mono td,.report-panel .mono th{font-family:Consolas,"Microsoft YaHei",monospace!important;font-size:21px}',
  '.report-panel .tight th{padding:6px 10px}.report-panel .tight td{padding:7px 10px;font-size:22px}.report-panel .tight.mono td{font-size:20px}',
  '.report-panel .kv th:first-child,.report-panel .kv td:first-child{width:29%}.report-panel .kv td:last-child{color:#292824}',
  '.report-panel .step{display:grid;grid-template-columns:58px 1fr;gap:18px;padding:13px 0;border-bottom:1px solid #d7cfbf}.report-panel .step .index{font-size:34px;font-weight:700;color:#9b4938}.report-panel .step b{font-size:28px}',
  '.report-panel .shot{margin:0 auto;border:1px solid #cfc5b3;background:#f8f5ee}.report-panel .shot img{display:block;width:100%;height:auto}.report-panel .capture-label{font-size:22px;line-height:1.4;margin-bottom:8px}.report-panel .capture-label strong{color:#8e4937}',
  '.report-panel .code{font-family:Consolas,"Microsoft YaHei",monospace!important;font-size:20px;line-height:1.5;white-space:pre-wrap;word-break:break-all;background:#f6f2e7;border-left:3px solid #a99b83;padding:16px 20px;color:#3b3a35}',
  '.report-panel .cover-name{font-size:88px;font-weight:800;line-height:1.2;letter-spacing:-3px}.report-panel .cover-sub{font-size:44px;font-weight:700;line-height:1.38;color:#8e4937}.report-panel .cover-question{font-size:56px;font-weight:800;line-height:1.38}.report-panel .spacer{height:10px;flex-shrink:0}',
].join('\n');

// 顺带把每页的散文/表格/步骤按页序抽出来，供 humanizer-zh 的去 AI 味复核比对（qa/prose-zh.md）
const prose = [];
const p = (s, c = 'text') => {
  prose.push({ page: pages.length + 1, kind: 'p', text: s });
  return '<p class="' + c + '">' + esc(s).replace(/\n/g, '<br>') + '</p>';
};
const table = (heads, rows, cls = '') => {
  prose.push({ page: pages.length + 1, kind: 'table', heads, rows });
  return '<table class="' + cls + '"><thead><tr>' + heads.map((x) => '<th>' + esc(x) + '</th>').join('') +
    '</tr></thead><tbody>' + rows.map((r) => '<tr>' + r.map((x) => '<td>' + esc(x).replace(/\n/g, '<br>') + '</td>').join('') + '</tr>').join('') + '</tbody></table>';
};
const step = (index, title, note) => {
  prose.push({ page: pages.length + 1, kind: 'step', index, title, note });
  return '<div class="step"><span class="index">' + esc(index) + '</span><div><b>' + esc(title) + '</b>' + p(note, 'note') + '</div></div>';
};
const code = (s) => '<div class="code">' + esc(s) + '</div>';

const assets = [];
function shot(name, width, label, source) {
  const file = path.join(out, 'assets', name);
  assert.ok(fs.existsSync(file), 'missing asset ' + name);
  const meta = stat(file);
  assets.push({ name, ...meta, source, width });
  prose.push({ page: pages.length + 1, kind: 'p', text: label });
  return '<figure><p class="capture-label">' + esc(label) + '</p><div class="shot" style="width:' + width + 'px" data-source="' + esc(source) +
    '" data-source-sha256="' + meta.sha256 + '"><img src="' + assetsRel + '/' + name + '" alt="' + esc(label) + '"></div></figure>';
}

const pages = [];
function add(kind, group, title, body, footer) {
  const n = pages.length + 1;
  pages.push({
    page: n, kind, title,
    html: '<section class="report-panel" style="width:960px;height:1180px;display:flex;flex-direction:column;gap:18px" data-height="1180" data-page-title="' +
      esc(title) + '"><style>' + css + '</style>' + p(String(n).padStart(2, '0') + ' / ' + group, 'eyebrow') +
      '<h2 class="title">' + esc(title) + '</h2>' + body + (footer ? p(footer, 'footer') : '') + '</section>\n',
  });
}

// 01 封面
pages.push({
  page: 1, kind: 'cover', title: 'LingBot-World 1.3B 部署：6GB 笔记本 Windows 原生跑通图生视频',
  html: '<section class="report-panel" style="width:960px;height:1180px;display:flex;flex-direction:column;gap:24px" data-height="1180" data-page-title="LingBot-World 1.3B 部署">' +
    '<style>' + css + '</style>' + p('世界模型部署', 'eyebrow') +
    '<div class="spacer" style="height:90px"></div>' +
    '<h1 class="cover-name">LingBot-World</h1>' + p('1.3B 图生视频 · Windows 11 原生', 'cover-sub') +
    '<div style="height:38px;flex-shrink:0"></div>' +
    p('单卡 6 GB\nWindows 原生\n能跑起来吗？', 'cover-question') +
    p('13 帧 · 832×464 · 一步约 12.7 分钟', 'lead') +
    '<div class="split"><div>' + p('显存', 'label') + '<p class="num">6<span class="unit"> GB</span></p></div><div>' +
    p('系统内存', 'label') + '<p class="num">64<span class="unit"> GB</span></p></div></div>' +
    p('环境 → 克隆 → 依赖 → 卡点 → 补丁 → 权重 → 13 帧\n仓库与手册：github.com/nonpricklycactus/lingbot-world-v2 · 分支 windows-native-deploy', 'footer') + '</section>\n',
});

// 02 这次要回答什么
add('main', '实验设计', '这次要回答什么',
  p('在一台 6GB 显存的 Windows 笔记本上，不装系统级 Python，\n也不动系统环境，能不能把 LingBot-World 的图生视频跑起来？', 'question') +
  p('官方 README 给的 1.3B 示例是 4 卡多进程，没有单卡 Windows 的安装说明。这次走单进程、单卡的原生 Windows 路径，行不行看这次运行。', 'text') +
  table(['项', '本次做法'], [
    ['运行环境', 'Windows 11 原生 PowerShell，不装系统级组件、不改系统环境'],
    ['Python', '由本机已有的 uv 提供 3.12，不装系统级、不改 PATH'],
    ['文件位置', '仓库、依赖、权重、输出都在 F:\\AI 一个目录，回滚＝删目录'],
    ['模型', '只取 1.3B DiT 与共享 T5 / VAE / tokenizer，不下载 14B 本体'],
    ['本次不测', '720p / 60fps、多卡、其他显卡型号、商业用途'],
  ], 'compact') +
  p('这次卡住的地方在安装阶段；下面把报错画面也留着。', 'observation'),
  '这些是本次实验的设计与边界，不代表官方 Windows 支持。');

// 03 机器与起点
add('main', '环境', '机器与起点',
  shot('env-basicinfo.png', 880, 'nvidia-smi：GPU、驱动与驱动自带的 CUDA UMD', '07-素材/世界模型部署相关/基础信息01.png') +
  shot('hw-os.png', 720, '系统版本与架构', 'step-01-hardware.mp4 @30s') +
  shot('hw-ram.png', 560, '机型与系统内存', 'step-01-hardware.mp4 @30s') +
  table(['项', '本机'], [
    ['GPU / 显存', 'RTX 3060 Laptop · 6144 MiB'],
    ['显卡驱动', '610.47（驱动自带 CUDA UMD 13.3）'],
    ['系统 / 内存 / 目标盘', 'Windows 11 家庭版 10.0.26200 · 63.73 GiB · F: 第二块 NVMe 剩余 310.3 GiB'],
    ['已有工具', 'git 2.55.0 · ffmpeg 9.0.2（本次不重装）'],
  ], 'compact'),
  '本机已有的驱动、Git、FFmpeg 只在画面里声明版本；观众要装什么、去哪装，写在手册和简介里。');

// 04 代码、解释器与虚拟环境
add('main', '环境', '代码、解释器与虚拟环境',
  shot('clone.png', 800, '从零 git clone', 'step-02-repo-v2.mp4 @205s') +
  step('01', '固定版本', 'clone 后 HEAD 为 1895d300d8ac936401689b26389f51cbd36530eb，与预期一致。') +
  step('02', '解释器不装系统级', 'Python 3.12.13 直接取自本机已有的 uv，在仓库目录内建 venv；系统 PATH 不变。') +
  step('03', '虚拟环境', 'venv 内 pip 26.2.1；卸载方式就是删掉 F:\\AI 这一个目录。') +
  code('Set-Location F:\\AI\n' +
    'git clone https://github.com/robbyant/lingbot-world-v2.git\n' +
    'git -C .\\lingbot-world-v2 rev-parse HEAD      # 1895d300…（与预期一致）\n' +
    'uv venv .\\lingbot-world-v2\\.venv --python 3.12\n' +
    '.\\lingbot-world-v2\\.venv\\Scripts\\python.exe --version   # Python 3.12.13') +
  p('仓库没有 Windows 安装说明，路径处理和模型加载器都是这次现验的。', 'observation'),
  '命令原文、预期输出与失败处理都写在部署手册里。');

// 05 下载：先解决"慢"
add('main', '环境', '下载：把 2.75 GB 的 torch 从 20 分钟压到 2 分 20 秒',
  p('单连接拉 torch 官方 Windows 轮子只有 2.15 MiB/s，\n照这个速度要等约 20 分钟。', 'question') +
  shot('aria2.png', 700, 'aria2 多连接下载：CN:16，逐段进度与 ETA', 'step-04a-wheels.mp4 @150s') +
  '<div class="split"><div>' + p('curl 单连接', 'label') + '<p class="num rust">2.15<span class="unit"> MiB/s</span></p>' + p('约 20 分钟', 'note') + '</div><div>' +
  p('aria2c -c -x16 -s16 -k1M', 'label') + '<p class="num green">18<span class="unit"> MiB/s</span></p>' + p('均速；峰值 24 MiB/s，2 分 20 秒完成', 'note') + '</div></div>' +
  p('做法只有两步：先用 aria2 把轮子抓到本地，再让 pip 从本地文件安装。全程走官方源，不引第三方镜像。', 'observation'),
  '同一条 URL、同一台机器、同一天实测；速度取自下载器自身输出。');

// 06 依赖与 CUDA 闸门
add('main', '环境', '依赖装齐，CUDA 闸门通过',
  shot('cudagate.png', 690, 'PyTorch CUDA gate：torch / cuda / 版本 / 卡名', 'step-05-cudagate.mp4 @40s') +
  table(['包', '版本', '包', '版本'], [
    ['torch', '2.11.0+cu128', 'transformers', '4.51.3'],
    ['torchvision', '0.26.0+cu128', 'diffusers', '0.39.0'],
    ['torchaudio', '2.11.0', 'accelerate', '1.15.0'],
    ['numpy', '1.26.4', 'scipy', '1.17.1'],
    ['opencv-python', '4.11.0.86', 'tokenizers', '0.21.4'],
    ['imageio', '2.38.0', 'einops', '0.8.2'],
  ], 'compact mono') +
  step('A', '不能用本机那个 3.14', '版本过新，与 torch 的 Windows 轮子对不上；它也只提供 python3 入口。') +
  step('B', '不能用应用商店的别名', 'python 会落到一个占位程序，建 venv 和装依赖都会失败。') +
  p('CUDA 闸门的判据是代码里真的返回 True：torch.cuda.is_available() 为 True、torch.version.cuda 为 12.8，卡的名称读得出来。', 'observation'),
  '驱动自带的 CUDA UMD 13.3 与 PyTorch 编译时用的 12.8 不是同一层东西，两者并存不代表冲突。');

// 07 卡点：flash-attn
add('main', '卡点', '卡点：flash-attn 在 Windows 原生下装不了',
  p('官方入口 pip install flash-attn --no-build-isolation，\n在这台机器上退出码 1，import 也失败。', 'question') +
  table(['折在哪一步', '实际输出'], [
    ['找预编译轮子', 'Precompiled wheel not found → HTTP Error 404'],
    ['回退源码编译', 'FileNotFoundError [WinError 2]：本机没有 MSVC'],
    ['构建脚本校验 CUDA', 'RuntimeError：检测到 13.3，而 PyTorch 由 12.8 编译'],
  ], 'compact mono kv') +
  shot('fa-cuda.png', 880, 'CUDA 版本不匹配，源码编译中止', 'step-06a-flashattn-fail.mp4 @290s') +
  p('失败发生在安装阶段，模型一个字节都还没加载——这不是显存问题。', 'observation'),
  '三条同时成立才失败；本次不装 MSVC 与另一套 CUDA，改用代码回退（下一页）。');

// 08 解法：SDPA 等价回退
add('main', '卡点', '解法：给 cross-attention 加一条 PyTorch 等价回退',
  p('causal_fast 的 cross-attention 在源码里硬依赖 flash-attn。\n这里不动依赖，在 attention.py 里补一条等价实现。', 'question') +
  code('wan/modules/attention.py（本机实验分支）\n' +
    '① 顶部加 import os\n' +
    '② flash_attention() 开头加分支：没有 flash-attn 时走新实现\n' +
    '③ attention() 改为委托 flash_attention()（原版回退会静默忽略 padding mask）\n' +
    '④ 文件末尾新增 _attention_impl() 与 _sdpa_varlen_attention()\n' +
    '   覆盖 GQA 展开 / 变长 padding mask / causal / 滑动窗口\n' +
    'WAN_ATTENTION_IMPL=auto|flash|sdpa    # 装了 flash-attn 仍优先走 flash-attn') +
  table(['验证项', '结果'], [
    ['离线数值测试', 'Ran 17 tests … OK（17 / 17）'],
    ['与 float64 手写参考实现比对', '逐元素误差 < 2e-5'],
    ['CUDA 真实形状冒烟', '(1, 1560, 12, 128) bfloat16 · 有限值 True · 峰值 23.6 MiB'],
    ['文件哈希', '原版 b6f57f0a… → 补丁版 d0efbca9…（差异 125 行）'],
  ], 'compact') +
  p('这是本机实验改动，不是官方支持的分支；引用它的结论时要说明。', 'observation'),
  '对照测试同时证明：原版官方回退确实会忽略 padding mask，补丁版不会。');

// 09 权重与校验
add('main', '准备', '权重：13 项 SHA-256 全部对上',
  table(['资源', '大小', '校验'], [
    ['1.3B DiT 六个分片 + index', '6.84 GB', '7 / 7 匹配'],
    ['T5 文本编码器（umt5-xxl bf16）', '11.36 GB', '匹配'],
    ['VAE（Wan2.1_VAE.pth）', '507.6 MB', '匹配'],
    ['tokenizer 四件套', '23.1 MB', '4 / 4 匹配'],
    ['合计', '18.73 GB（17.44 GiB）', '13 / 13 无缺失、无不匹配'],
  ]) +
  p('只取这条路径需要的文件，仓库里 74 GB 的 14B 分片一个都没碰。', 'note') +
  shot('einops.png', 800, '补装官方依赖清单漏掉的 einops', 'step-11b-einops.mp4 @40s') +
  p('官方 requirements.txt 里没有 einops，模型代码里却用了 5 处；不补装，generate.py 连 --help 都进不去。这是仓库自己的疏漏，不是环境问题。', 'observation'),
  '大小按字节换算：模型目录 18,729,186,304 字节；13 个文件的 SHA-256 逐个核对。');

// 10 真跑
add('main', '运行', '13 帧命令与 12.7 分钟',
  code('python generate.py --task i2v-1.3B --infer_mode causal_fast \\\n' +
    '  --size 480*832 --frame_num 13 --ckpt_dir <DiT> --assets_dir <Assets> \\\n' +
    '  --image examples/03/image.jpg --action_path examples/03 \\\n' +
    '  --prompt "<实测用的英文提示词>" --base_seed 42 \\\n' +
    '  --t5_cpu --convert_model_dtype --offload_model True \\\n' +
    '  --local_attn_size 18 --sink_size 6 --save_file <Out>') +
  shot('gen-start.png', 780, '日志里的生成起点与时间戳', 'step-12-generate.mp4 @1000s') +
  '<div class="split"><div>' + p('生成开始', 'label') + p('16:55:29', 'big') + '</div><div>' +
  p('写出文件 / 结束', 'label') + p('17:08:12 → 17:08:13', 'big') + '</div></div>' +
  p('从“开始生成”到“写完文件”共约 763 秒，也就是 12 分 43 秒；这段时间里显卡采样利用率 100%。', 'observation'),
  p('生成过程不弹预览窗口，脚本只负责把权重载入、逐帧算完、写出文件；屏幕上能看到的只有这个终端。', 'note') +
  '耗时口径＝模型日志的生成起点到写出文件，含模型加载之后的全过程；不是纯采样，也不是“能实时出片”。');

// 11 参数逐条
add('main', '运行', '命令参数逐条',
  p('下面是这次实际用的参数，按命令里的顺序。', 'note') +
  table(['参数', '作用'], [
    ['--task i2v-1.3B', '任务与模型规模：图生视频，1.3B'],
    ['--infer_mode causal_fast', '少步蒸馏的因果推理路径'],
    ['--size 480*832', '输入面积与朝向；输出按起始图宽高比改写为 832×464'],
    ['--frame_num 13', '生成帧数；这条路径最短的合法长度是 13（4n+1）'],
    ['--ckpt_dir', 'DiT 权重目录'],
    ['--assets_dir', 'T5 / VAE / tokenizer 共享资源目录'],
    ['--image', '起始图（仓库自带 examples/03/image.jpg）'],
    ['--action_path', '相机轨迹动作文件目录；causal_fast 必需'],
    ['--t5_cpu', 'T5 文本编码器放在 CPU 上'],
    ['--convert_model_dtype', '加载时把权重转成 bfloat16'],
    ['--offload_model True', '每步前向之后把模型挪回 CPU'],
    ['--local_attn_size 18', 'KV cache 的窗口长度'],
    ['--sink_size 6', 'KV cache 里固定保留的前缀帧数'],
    ['--base_seed 42', '随机种子'],
    ['--save_file', '输出文件路径'],
  ], 'compact tight mono') +
  p('按仓库代码：缺 --action_path 会在采样前退出；--frame_num 小于 13 会把时间维收成 0。', 'observation'),
  '参数名照命令原文写；作用按本次运行日志与仓库代码核对。');

// 11 结果
add('main', '结果', '结果：832×464 的 13 帧视频',
  shot('gen-done.png', 880, '写出文件与结束：17:08:12 / 17:08:13', 'step-12-generate.mp4 @1000s') +
  shot('result-frames.png', 880, '模型输出视频的第 1、6、13 帧', 'result/lingbot-13f.mp4 抽帧') +
  table(['项', '结果'], [
    ['分辨率 / 帧数', '832 × 464 · 13 帧'],
    ['帧率 / 时长', '16 fps · 0.8125 秒'],
    ['文件大小', '1,273,344 字节'],
    ['SHA-256', '897c908d04950630a89ac88f95e3831c3327f76e4be796af0d2b507cf6d66b8f'],
  ], 'compact mono') +
  p('规格：832×464 / 13 帧 / 16 fps / 0.8125 秒。这条路径用的是本机的 SDPA 回退实现，不是 flash-attn。', 'observation'),
  '成片不到 1 秒；这 13 帧不是实时生成。');

// 12 代价与边界
add('main', '边界', '代价与边界',
  table(['项', '本次'], [
    ['attention 实现', '本机 SDPA 回退补丁（非官方支持路径）'],
    ['生成段耗时', '约 763 秒（12 分 43 秒）'],
    ['显存', '运行中采样到 4996 MiB / 6144 MiB'],
    ['输出', '832×464 · 13 帧 · 16 fps · 0.8125 秒'],
  ], 'compact') +
  p('显存那格是运行中的一次采样（显卡利用率 100% 时读到 4996 MiB），不是连续峰值，采样间隔也不固定；所以只能写“这次运行中采到 4996 MiB / 6144 MiB，没有 OOM”。', 'note') +
  p('要拿连续峰值得重跑一遍并加监控；本次没有这样做。', 'note') +
  p('这份图文是候审稿：录音稿、配音、字幕、成片与公开发布都还没开始。', 'note') +
  p('官方仓库还有两处会绊人的地方，本次都遇到过：requirements.txt 没写 einops；cross-attention 硬依赖 flash-attn 且没有可用的官方回退。', 'note') +
  p('本次没有验证：720p / 60fps、多卡、其他显卡型号、更大的帧数、真正的实时生成，以及商业用途 —— 模型与代码边界包含 CC BY-NC-SA 4.0。', 'observation'),
  '另外两处缺口：录屏里的 SHA 校验命令写坏了、屏幕上只有报错（13/13 是另行重算的）；模型退出码没能从终端回读。');

// ── 写盘 ────────────────────────────────────────────────────────────────────
const panelsDir = path.join(out, 'panels');
fs.mkdirSync(panelsDir, { recursive: true });
const plan = { schema_version: 1, main_pages: pages.length, appendix_pages: 0, total_pages: pages.length, pages: [] };
pages.forEach((pg) => {
  const rel = panelsRel(pg.page);
  const file = path.join(out, rel.replace(/^.*bench-note-lingbot-deploy-windows-v1\//, ''));
  fs.writeFileSync(file, pg.html);
  plan.pages.push({ page: pg.page, title: pg.title, kind: pg.kind, path: rel, sha256: hash(file) });
});
function panelsRel(n) {
  return '02-内容工厂/output/bench-note-lingbot-deploy-windows-v1/panels/' + String(n).padStart(2, '0') + '.html';
}
const md = ['---', 'bench_note:', '  profile: kun-local-lab', '  series: LINGBOT-WORLD 1.3B / WINDOWS 原生部署',
  '  footer_left: RTX 3060 LAPTOP 6GB · WINDOWS 11 原生 · 单卡 13 帧', '---', ''];
plan.pages.forEach((pg, i) => {
  md.push('```PANEL', pg.path, '```', '');
  if (i !== plan.pages.length - 1) md.push('<!-- PAGE -->', '');
});
fs.writeFileSync(path.join(root, '02-内容工厂/output/bench-note-lingbot-deploy-windows-v1.zh.md'), md.join('\n'));
fs.writeFileSync(path.join(out, 'page-plan.json'), JSON.stringify(plan, null, 2) + '\n');
fs.writeFileSync(path.join(out, 'asset-sources.json'), JSON.stringify({ schema_version: 1, root: '07-素材/世界模型部署相关/录屏-20261005', assets }, null, 2) + '\n');

// 散文抽取：纯文本稿，给 humanizer-zh 的去 AI 味复核做前后比对（软件侧只保证结构不变）
const oneLine = (s) => String(s).replace(/\n/g, ' ');
const proseLines = [];
let prosePage = 0;
for (const rec of prose) {
  if (rec.page !== prosePage) {
    prosePage = rec.page;
    proseLines.push('', '## ' + pages[prosePage - 1].title, '');
  }
  if (rec.kind === 'p') proseLines.push(oneLine(rec.text), '');
  else if (rec.kind === 'step') proseLines.push('**' + oneLine(rec.title) + '**：' + oneLine(rec.note), '');
  else {
    proseLines.push('| ' + rec.heads.map(oneLine).join(' | ') + ' |');
    proseLines.push('|' + rec.heads.map(() => '---').join('|') + '|');
    for (const r of rec.rows) proseLines.push('| ' + r.map(oneLine).join(' | ') + ' |');
    proseLines.push('');
  }
}
fs.mkdirSync(path.join(out, 'qa'), { recursive: true });
fs.writeFileSync(path.join(out, 'qa/prose-zh.md'), proseLines.join('\n').replace(/^\n/, '') + '\n');
console.log(JSON.stringify({ pages: pages.length, assets: assets.length, prose_records: prose.length, outMp4, diffLines }, null, 1));
