<#
  LingBot-World 1.3B · Windows 原生部署分步执行器

  配合 02-内容工厂/output/lingbot-world-1.3b-deployment-manual-v1.md 使用：
  手册负责口径和判据，本脚本只负责把每步的命令原样打印出来、执行并留日志。

  三个刻意的设计：
  1) 每步执行前先打印"本步命令"，执行后再打印一次"复制用命令"，方便整理教程网页；
  2) 所有输出默认脱敏（本机用户名、机器名、令牌、邮箱、MAC、SID），再进日志；
  3) 只读或可重复的步骤直接跑；会下载大量数据或长时间占卡的步骤先要确认。

  用法：
    双击 run-deploy-steps.cmd           进入菜单
    run-deploy-steps.cmd -Step 0        只跑第 0 步（便于分批录制）
    run-deploy-steps.cmd -NoRedact      关闭脱敏（默认开启，不建议）
    run-deploy-steps.cmd -Yes           跳过长步骤的确认
#>
[CmdletBinding()]
param(
  [string]$Step = '',
  [switch]$NoRedact,
  [switch]$Yes,
  [string]$LogDir = 'F:\Temp\lingbot-deploy-logs'
)

$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

# ----------------------------------------------------------------------------
# 路径与固定值（与手册一致；改这里就等于改全篇）
# ----------------------------------------------------------------------------
$Cfg = [ordered]@{
  Root       = 'F:\AI\lingbot-world-v2'
  Models     = 'F:\AI\models'
  Runtime    = 'F:\AI\runtime'
  OutputDir  = 'F:\AI\lingbot-output'
  RepoUrl    = 'https://github.com/robbyant/lingbot-world-v2.git'
  Commit     = '1895d300d8ac936401689b26389f51cbd36530eb'
  DitRepo    = 'robbyant/lingbot-world-v2-1.3b-causal-fast'
  AssetsRepo = 'robbyant/lingbot-world-v2-14b-causal-fast'
}
$Venv        = Join-Path $Cfg.Root '.venv'
$Py          = Join-Path $Venv 'Scripts\python.exe'
$DitOut      = Join-Path $Cfg.Models 'lingbot-world-v2-1.3b-causal-fast'
$DitDownload = Join-Path $Cfg.Models 'downloads\lingbot-world-v2-1.3b-causal-fast'
$Assets      = Join-Path $Cfg.Models 'lingbot-world-v2-14b-assets'
$OutFile     = Join-Path $Cfg.OutputDir 'lingbot-13f.mp4'

# 缓存目录统一落到 F:，避免 uv / pip 的下载緩存堆到 C 盘用户目录
$env:UV_CACHE_DIR  = Join-Path $Cfg.Runtime 'uv-cache'
$env:PIP_CACHE_DIR = Join-Path $Cfg.Runtime 'pip-cache'

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$script:LogFile = Join-Path $LogDir ('run-{0}.log' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))

# ----------------------------------------------------------------------------
# 脱敏
# ----------------------------------------------------------------------------
$script:Masked = 0
function Redact([string]$Text) {
  if ($NoRedact) { return $Text }
  $t = [string]$Text
  $before = $t
  $user = $env:USERNAME
  $pc = $env:COMPUTERNAME
  if ($user) { $t = $t -replace ('(?i)' + [regex]::Escape($user)), '<user>' }
  if ($pc)   { $t = $t -replace ('(?i)' + [regex]::Escape($pc)), '<pc>' }
  $t = $t -replace '(?i)([A-Za-z]:\\Users\\)[^\\\s"'']+', '$1<user>'
  $t = $t -replace '(?i)\bhf_[A-Za-z0-9]{16,}\b', 'hf_***'
  $t = $t -replace '(?i)\bgh[pousr]_[A-Za-z0-9]{16,}\b', 'gh_***'
  $t = $t -replace '(?i)\bsk-[A-Za-z0-9_\-]{16,}\b', 'sk-***'
  $t = $t -replace '(?i)\bAKIA[0-9A-Z]{12,}\b', 'AKIA***'
  $t = $t -replace '(?i)(token|api[_-]?key|password|passwd|secret|credential)(\s*[=:]\s*)\S+', '$1$2***'
  $t = $t -replace '(?i)\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b', '<email>'
  $t = $t -replace '(?i)\b([0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b', '<mac>'
  $t = $t -replace '(?i)S-1-5-21(-[0-9]+){3,4}', '<sid>'
  if ($t -ne $before) { $script:Masked++ }
  return $t
}

# ----------------------------------------------------------------------------
# 输出与日志
# ----------------------------------------------------------------------------
function Write-Line([string]$Text, [string]$Color = '') {
  if ($Color) { Write-Host $Text -ForegroundColor $Color } else { Write-Host $Text }
  Add-Content -LiteralPath $script:LogFile -Value $Text -Encoding UTF8
}

function Write-Raw([string]$Text) {
  Write-Host $Text
  Add-Content -LiteralPath $script:LogFile -Value $Text -Encoding UTF8
}

function Write-CmdBlock([string]$Title, [string[]]$Commands) {
  Write-Line ''
  Write-Line "=== $Title ===" 'Cyan'
  foreach ($c in $Commands) {
    Write-Line "  $c"
  }
}

function Invoke-Streamed([scriptblock]$Body) {
  # 逐条即时透出：文本和错误按行打印，PowerShell 对象各自渲染成小表格。
  # 这样长时间任务（pip / 生成）能实时看到进度，也不会出现 @{Name=...;Source=...} 这种原始串。
  & $Body 2>&1 | ForEach-Object {
    if ($_ -is [string] -or $_ -is [System.Management.Automation.ErrorRecord]) {
      Write-Raw (Redact ([string]$_))
    }
    else {
      $text = ($_ | Out-String -Width 200).TrimEnd()
      foreach ($l in ($text -split "`r?`n")) { Write-Raw (Redact $l) }
    }
  }
}

# 说明：uv 建的 venv 里解释器路径固定；核到实际存在的 hf 入口
function Get-Hf {
  $c = @(
    (Join-Path $Venv 'Scripts\hf.exe'),
    (Join-Path $Venv 'Scripts\huggingface-cli.exe')
  )
  return ($c | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1)
}

# 1.3B 权重的落盘层级取决于 HF CLI 版本：优先认 transformers 子目录存在的那一层
function Get-DitDir {
  foreach ($c in @($DitOut, $DitDownload)) {
    if (Test-Path -LiteralPath (Join-Path $c 'transformers\model.safetensors.index.json')) { return $c }
  }
  if (Test-Path -LiteralPath $DitOut) { return $DitOut }
  return $DitOut
}

# ----------------------------------------------------------------------------
# 各步骤定义
# ----------------------------------------------------------------------------
$Steps = @(
  [pscustomobject]@{
    Id = '0'; Title = '环境自检（基础工具 + uv）'; Manual = '§2.1'; Long = $false
    Cmds = @(
      'Get-Command nvidia-smi,git,ffmpeg,ffprobe -ErrorAction SilentlyContinue | Select-Object Name,Source',
      'nvidia-smi',
      'py --list',
      'py --version',
      'python --version',
      'python -m pip --version',
      'git --version',
      'ffmpeg -version',
      'ffprobe -version',
      'uv --version',
      'uv python find 3.12'
    )
    Body = {
      Get-Command nvidia-smi, git, ffmpeg, ffprobe -ErrorAction SilentlyContinue |
        Select-Object Name, Source
      Write-Output ''
      nvidia-smi
      Write-Output ''
      Write-Output '[i] 本机不装系统级 Python：下面 py / python 的报错是预期结果（手册 §2.0）'
      try { py --list } catch { Write-Output '[i] py 启动器不存在（预期）' }
      try { py --version } catch { Write-Output '[i] py 启动器不存在（预期）' }
      python --version
      python -m pip --version
      git --version
      Write-Output ''
      ffmpeg -version
      ffprobe -version
      Write-Output ''
      uv --version
      uv python find 3.12
    }
  }

  [pscustomobject]@{
    Id = '1'; Title = '硬件与系统记录'; Manual = '§2.2'; Long = $false
    Cmds = @(
      'Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,OSArchitecture,LastBootUpTime',
      "Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model,@{Name='TotalRAM_GiB';Expression={[math]::Round(`$_.TotalPhysicalMemory / 1GB, 2)}}",
      'Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,AdapterRAM',
      'Get-PSDrive -PSProvider FileSystem | Select-Object Name,Root,Used,Free'
    )
    Body = {
      Get-CimInstance Win32_OperatingSystem |
        Select-Object Caption, Version, OSArchitecture, LastBootUpTime
      Write-Output ''
      Get-CimInstance Win32_ComputerSystem |
        Select-Object Manufacturer, Model,
          @{ Name = 'TotalRAM_GiB'; Expression = { [math]::Round($_.TotalPhysicalMemory / 1GB, 2) } }
      Write-Output ''
      Get-CimInstance Win32_VideoController |
        Select-Object Name, DriverVersion, AdapterRAM
      Write-Output ''
      Get-PSDrive -PSProvider FileSystem |
        Select-Object Name, Root, Used, Free
    }
  }

  [pscustomobject]@{
    Id = '2'; Title = '获取代码并固定 commit'; Manual = '§3'; Long = $false
    Cmds = @(
      "`$Root = '$($Cfg.Root)'",
      "git clone $($Cfg.RepoUrl)",
      "git checkout $($Cfg.Commit)",
      'git rev-parse HEAD',
      'git status --short'
    )
    Body = {
      $parent = Split-Path $Cfg.Root -Parent
      New-Item -ItemType Directory -Force -Path $parent | Out-Null
      if (Test-Path -LiteralPath (Join-Path $Cfg.Root '.git')) {
        Write-Output '[i] 仓库已存在：按手册不覆盖现场，只核对当前版本'
        Set-Location $Cfg.Root
        git rev-parse HEAD
        git status --short
      }
      else {
        Set-Location $parent
        git clone $Cfg.RepoUrl
        Set-Location $Cfg.Root
        git checkout $Cfg.Commit
        Write-Output 'repo_commit='
        git rev-parse HEAD
        git status --short
      }
    }
  }

  [pscustomobject]@{
    Id = '3'; Title = '建立 Python 虚拟环境（uv，零安装）'; Manual = '§4.1'; Long = $false
    Cmds = @(
      "`$env:UV_CACHE_DIR  = '$($Cfg.Runtime)\uv-cache'",
      "`$env:PIP_CACHE_DIR = '$($Cfg.Runtime)\pip-cache'",
      '`$Py312 = (uv python find 3.12).Trim()',
      '`$Py312 --version',
      "uv venv --python 3.12 --seed '$Venv'",
      '`$Py -m pip --version'
    )
    Body = {
      Set-Location $Cfg.Root
      $py312 = (uv python find 3.12).Trim()
      Write-Output "python312=$py312"
      & $py312 --version
      if (Test-Path -LiteralPath $Py) {
        Write-Output '[i] venv 已存在，跳过创建'
      }
      else {
        uv venv --python 3.12 --seed $Venv
      }
      & $Py --version
      & $Py -m pip --version
    }
  }

  [pscustomobject]@{
    Id = '4'; Title = '安装官方依赖（requirements.txt）'; Manual = '§4.2'; Long = $true
    Cmds = @(
      'Set-Location $Root',
      '& $Py -m pip install --upgrade pip',
      "& `$Py -m pip install -r (Join-Path `$Root 'requirements.txt')"
    )
    Body = {
      Set-Location $Cfg.Root
      & $Py -m pip install --upgrade pip
      & $Py -m pip install -r (Join-Path $Cfg.Root 'requirements.txt')
      Write-Output "[i] pip 退出码=$LASTEXITCODE（flash_attn 在这里失败是预期分支，见手册 §4.4）"
    }
  }

  [pscustomobject]@{
    Id = '5'; Title = 'PyTorch CUDA gate'; Manual = '§4.3'; Long = $false
    Cmds = @(
      '& $Py -c "import torch; print(''torch:'', torch.__version__); print(''cuda_available:'', torch.cuda.is_available()); print(''torch_cuda:'', torch.version.cuda); print(''gpu:'', torch.cuda.get_device_name(0) if torch.cuda.is_available() else ''no CUDA'')"'
    )
    Body = {
      & $Py -c "import torch; print('torch:', torch.__version__); print('cuda_available:', torch.cuda.is_available()); print('torch_cuda:', torch.version.cuda); print('gpu:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no CUDA')"
      Write-Output "torch_cuda_check_exit=$LASTEXITCODE"
    }
  }

  [pscustomobject]@{
    Id = '6'; Title = '安装 flash-attn（预编译 wheel，分支 A）'; Manual = '§4.4'; Long = $false
    Cmds = @(
      '& $Py -c "import torch;print(torch.__version__, torch.version.cuda)"',
      'Get-FileHash <wheel> -Algorithm SHA256',
      "& `$Py -m pip install '<wheel 绝对路径>'",
      '& $Py -c "import flash_attn; print(getattr(flash_attn, ''__version__'', ''unknown''))"'
    )
    Body = {
      & $Py -c "import torch;print(torch.__version__, torch.version.cuda)"
      Write-Output ''
      Write-Output '[i] wheel 必须与上面的 torch 次版本 + CUDA + cp312 三者全对，否则会退回源码编译'
      $wheel = Read-Host 'wheel 文件的完整路径'
      if (-not (Test-Path -LiteralPath $wheel)) {
        Write-Warning "找不到文件：$wheel"
        return
      }
      Get-FileHash -LiteralPath $wheel -Algorithm SHA256
      & $Py -m pip install $wheel
      & $Py -c "import flash_attn; print('flash_attn:', getattr(flash_attn,'__version__','unknown'))"
      Write-Output "flash_attn_import_exit=$LASTEXITCODE"
    }
  }

  [pscustomobject]@{
    Id = '7'; Title = '安装 Hugging Face CLI'; Manual = '§5.2'; Long = $false
    Cmds = @(
      'Set-Location $Root',
      "& `$Py -m pip install 'huggingface_hub[cli]'",
      '& $Hf --version'
    )
    Body = {
      Set-Location $Cfg.Root
      & $Py -m pip install 'huggingface_hub[cli]'
      $hf = Get-Hf
      if (-not $hf) { Write-Warning 'venv 里没找到 hf.exe / huggingface-cli.exe'; return }
      Write-Output "hf_cli=$hf"
      & $hf --version
    }
  }

  [pscustomobject]@{
    Id = '8'; Title = '下载 1.3B DiT 权重'; Manual = '§5.3'; Long = $true
    Cmds = @(
      "& `$Hf download $($Cfg.DitRepo) --local-dir '$DitDownload'",
      "Get-ChildItem -LiteralPath '$DitDownload' -Recurse -File | Select-Object Length,FullName"
    )
    Body = {
      $hf = Get-Hf
      if (-not $hf) { Write-Warning '先跑第 7 步安装 Hugging Face CLI'; return }
      New-Item -ItemType Directory -Force -Path $DitDownload | Out-Null
      & $hf download $Cfg.DitRepo --local-dir $DitDownload
      Write-Output ''
      Write-Output "[i] ckpt_dir 实际取：$(Get-DitDir)"
      Get-ChildItem -LiteralPath $DitDownload -Recurse -File |
        Select-Object Length, FullName
    }
  }

  [pscustomobject]@{
    Id = '9'; Title = '下载共享 T5 / VAE / tokenizer'; Manual = '§5.4'; Long = $true
    Cmds = @(
      "& `$Hf download $($Cfg.AssetsRepo) --local-dir '$Assets' ``",
      "  --include 'Wan2.1_VAE.pth' --include 'models_t5_umt5-xxl-enc-bf16.pth' --include 'google/umt5-xxl/*'"
    )
    Body = {
      $hf = Get-Hf
      if (-not $hf) { Write-Warning '先跑第 7 步安装 Hugging Face CLI'; return }
      New-Item -ItemType Directory -Force -Path $Assets | Out-Null
      & $hf download $Cfg.AssetsRepo --local-dir $Assets `
        --include 'Wan2.1_VAE.pth' `
        --include 'models_t5_umt5-xxl-enc-bf16.pth' `
        --include 'google/umt5-xxl/*'
      Get-ChildItem -LiteralPath $Assets -Recurse -File |
        Sort-Object FullName | Select-Object Length, FullName
    }
  }

  [pscustomobject]@{
    Id = '10'; Title = '资源目录与 SHA-256 核对'; Manual = '§5.5'; Long = $false
    Cmds = @(
      'Test-Path <6 个 DiT 分片 + index.json + VAE + T5>',
      'Get-FileHash -LiteralPath <file> -Algorithm SHA256   # 与手册的期望值逐一比对'
    )
    Body = {
      $dit = Get-DitDir
      $ditTransformers = Join-Path $dit 'transformers'
      Write-Output "dit_dir=$dit"

      $expected = [ordered]@{
        'model.safetensors.index.json'      = 'b0409d663b57810af19443c9e8d8dde43320193c8dbb979d86f6618102922e42'
        'model-00001-of-00006.safetensors'  = '4169eaf504fc63c235f4b66c95887951ecd71ba4ca9492e8528b6709d63ed9b2'
        'model-00002-of-00006.safetensors'  = 'e6745d1e600f697f2285ca435de09c49d2082303b7f9a2bb39003fc87b354d2f'
        'model-00003-of-00006.safetensors'  = '20f9b226fcfcfb4dead5c1e3ff1b77da182787442ebabfdaf23d3c68aca44ceb'
        'model-00004-of-00006.safetensors'  = '5b5c18cc18a4de976002f45777f59b4d27d30786c6db94e134d0af5a031f5272'
        'model-00005-of-00006.safetensors'  = '089575f86c3c62e12566a79c5e0afd663415aa4376e193b45ee2bb2ac65a9cbe'
        'model-00006-of-00006.safetensors'  = 'c0d3d8643d07b6d6e26d614f80cf3538a562f575937a759c64a71d5575f2f915'
      }
      $paths = [ordered]@{}
      foreach ($n in $expected.Keys) { $paths[$n] = Join-Path $ditTransformers $n }

      $tokenizer = @('special_tokens_map.json', 'spiece.model', 'tokenizer.json', 'tokenizer_config.json')
      $tokenizerDir = Join-Path $Assets 'google\umt5-xxl'

      $rows = foreach ($n in $expected.Keys) {
        $p = $paths[$n]
        if (-not (Test-Path -LiteralPath $p)) {
          [pscustomobject]@{ File = $n; Exists = $false; Match = $null; SHA256 = '' }
          continue
        }
        $h = (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()
        [pscustomobject]@{ File = $n; Exists = $true; Match = ($h -eq $expected[$n]); SHA256 = $h }
      }
      $rows | Format-Table -AutoSize

      foreach ($n in @('Wan2.1_VAE.pth', 'models_t5_umt5-xxl-enc-bf16.pth')) {
        $p = Join-Path $Assets $n
        [pscustomobject]@{ File = $n; Exists = (Test-Path -LiteralPath $p) } | Format-Table -AutoSize
      }
      foreach ($n in $tokenizer) {
        $p = Join-Path $tokenizerDir $n
        [pscustomobject]@{ File = "google\umt5-xxl\$n"; Exists = (Test-Path -LiteralPath $p) } | Format-Table -AutoSize
      }
      Write-Output '[i] 任何 Exists=False 或 Match=False 都不要进入生成；先按手册 §5.6 停在 07_error'
    }
  }

  [pscustomobject]@{
    Id = '11'; Title = '检查输入动作文件（examples\03）'; Manual = '§6.1'; Long = $false
    Cmds = @(
      "`$Image = Join-Path `$Root 'examples\03\image.jpg'",
      "`$ActionPath = Join-Path `$Root 'examples\03'",
      'Get-Item -LiteralPath $Image',
      'Get-ChildItem -LiteralPath $ActionPath -File | Select-Object Name,Length,FullName'
    )
    Body = {
      $image = Join-Path $Cfg.Root 'examples\03\image.jpg'
      $actionPath = Join-Path $Cfg.Root 'examples\03'
      Get-Item -LiteralPath $image
      Get-ChildItem -LiteralPath $actionPath -File |
        Select-Object Name, Length, FullName
      Write-Output '[i] 动作目录里应能看到 poses.npy 和 intrinsics.npy'
    }
  }

  [pscustomobject]@{
    Id = '12'; Title = '执行 13 帧单卡生成'; Manual = '§6.3'; Long = $true
    Cmds = @(
      "& `$Py generate.py --task i2v-1.3B --infer_mode causal_fast --size 480*832 --frame_num 13 ``",
      "  --ckpt_dir '<实际 ckpt_dir>' --assets_dir '$Assets' ``",
      "  --image `$Root\examples\03\image.jpg --action_path `$Root\examples\03 ``",
      "  --t5_cpu --convert_model_dtype --offload_model True --local_attn_size 18 --sink_size 6 --base_seed 42 ``",
      "  --prompt 'A serene lakeside scene with a lone tree standing in calm water, surrounded by distant snow-capped mountains under a bright blue sky with drifting white clouds.' ``",
      "  --save_file '$OutFile'"
    )
    Body = {
      $dit = Get-DitDir
      $image = Join-Path $Cfg.Root 'examples\03\image.jpg'
      $actionPath = Join-Path $Cfg.Root 'examples\03'
      New-Item -ItemType Directory -Force -Path $Cfg.OutputDir | Out-Null
      Set-Location $Cfg.Root
      $runArgs = @(
        'generate.py'
        '--task', 'i2v-1.3B'
        '--infer_mode', 'causal_fast'
        '--size', '480*832'
        '--frame_num', '13'
        '--ckpt_dir', $dit
        '--assets_dir', $Assets
        '--image', $image
        '--action_path', $actionPath
        '--t5_cpu'
        '--convert_model_dtype'
        '--offload_model', 'True'
        '--local_attn_size', '18'
        '--sink_size', '6'
        '--base_seed', '42'
        '--prompt', 'A serene lakeside scene with a lone tree standing in calm water, surrounded by distant snow-capped mountains under a bright blue sky with drifting white clouds.'
        '--save_file', $OutFile
      )
      Write-Output "ckpt_dir=$dit"
      & $Py @runArgs
      Write-Output "model_exit_code=$LASTEXITCODE"
    }
  }

  [pscustomobject]@{
    Id = '13'; Title = '输出验收（文件 + SHA-256 + ffprobe）'; Manual = '§6.5'; Long = $false
    Cmds = @(
      "Test-Path -LiteralPath '$OutFile'",
      "Get-Item -LiteralPath '$OutFile' | Format-List FullName,Length,LastWriteTime",
      "Get-FileHash -LiteralPath '$OutFile' -Algorithm SHA256",
      "ffprobe -v error -select_streams v:0 -show_entries stream=width,height,nb_frames,avg_frame_rate,duration -of json '$OutFile'"
    )
    Body = {
      Write-Output "out_file=$OutFile"
      if (-not (Test-Path -LiteralPath $OutFile)) {
        Write-Warning '输出文件不存在：不要把它说成成功'
        return
      }
      Get-Item -LiteralPath $OutFile | Format-List FullName, Length, LastWriteTime
      Get-FileHash -LiteralPath $OutFile -Algorithm SHA256
      ffprobe -v error -select_streams v:0 `
        -show_entries stream=width,height,nb_frames,avg_frame_rate,duration `
        -of json $OutFile
      Write-Output '[i] file exists 不等于生成成功；退出码、文件大小、哈希和 ffprobe 一起看'
    }
  }

  [pscustomobject]@{
    Id = '99'; Title = '自检：脱敏与日志'; Manual = '附录'; Long = $false
    Cmds = @(
      '# 把样例字符串过一遍脱敏规则，确认写教程前不会带出本机信息'
    )
    Body = {
      # 说明：脚本可见的输出都会先脱敏再打印，所以这里不能"打印原样再打印脱敏"，
      # 只能对每条规则做断言，再把脱敏后的结果打出来。
      $cases = @(
        [pscustomobject]@{ Name = '用户目录';   Raw = ('C:\Users\{0}\work' -f $env:USERNAME);            Expect = 'C:\Users\<user>\work' }
        [pscustomobject]@{ Name = '机器名';     Raw = ('{0} 上的输出' -f $env:COMPUTERNAME);              Expect = '<pc> 上的输出' }
        [pscustomobject]@{ Name = 'HF 令牌';    Raw = 'token=hf_abcdefghijklmnopqrstuvwxyz0123';        Expect = 'token=***' }
        [pscustomobject]@{ Name = 'OpenAI 令牌'; Raw = 'Authorization: Bearer sk-abcdefghijklmnopqrstuvwxyz'; Expect = 'Authorization: Bearer sk-***' }
        [pscustomobject]@{ Name = '邮箱';       Raw = '邮箱: someone@example.com';                      Expect = '邮箱: <email>' }
        [pscustomobject]@{ Name = 'MAC';        Raw = 'MAC: 3C-7C-3F-1A-2B-9D';                         Expect = 'MAC: <mac>' }
        [pscustomobject]@{ Name = 'SID';        Raw = 'SID: S-1-5-21-1111111111-2222222222-3333333333-1001'; Expect = 'SID: <sid>' }
        [pscustomobject]@{ Name = '通用 key';   Raw = 'api_key: AIzaSyD-abcdefghijklmnopqrstuvwxyz';    Expect = 'api_key: ***' }
      )
      $pass = 0
      foreach ($c in $cases) {
        $got = Redact $c.Raw
        $ok = ($got -eq $c.Expect)
        if ($ok) { $pass++ }
        $flag = 'FAIL'
        if ($ok) { $flag = 'PASS' }
        Write-Output ("{0}  {1,-10} 脱敏结果: {2}" -f $flag, $c.Name, $got)
      }
      Write-Output ''
      Write-Output ("自检结果: {0}/{1} 条通过（用 -NoRedact 运行时全部显示 FAIL 属预期）" -f $pass, $cases.Count)
    }
  }
)

# ----------------------------------------------------------------------------
# 执行单步
# ----------------------------------------------------------------------------
function Invoke-Step([object]$S) {
  Write-Line ''
  Write-Line ('------------------------------------------------------------') 'DarkGray'
  Write-Line ("[{0}] {1}   （手册 {2}）" -f $S.Id, $S.Title, $S.Manual) 'Yellow'

  if ($S.Long -and -not $Yes) {
    Write-Line '[!] 这一步耗时长或下载量大，确认后才会执行。' 'Yellow'
    $a = Read-Host '    继续？(y/N)'
    if ($a -notmatch '^(?i)y') {
      Write-Line '[i] 已跳过'
      return
    }
  }

  Write-CmdBlock '本步命令（可抄进教程）' $S.Cmds
  Write-Line ''
  Write-Line '=== 命令输出 ===' 'Cyan'
  $before = $script:Masked
  Invoke-Streamed $S.Body
  $masked = $script:Masked - $before
  Write-Line ''
  Write-Line ("=== 本步结束（脱敏命中 {0} 处）===" -f $masked) 'Cyan'
  Write-CmdBlock '复制用命令（同前）' $S.Cmds
}

# ----------------------------------------------------------------------------
# 菜单
# ----------------------------------------------------------------------------
function Show-Header {
  Write-Line ''
  Write-Line 'LingBot-World 1.3B · Windows 原生部署分步执行器' 'Green'
  Write-Line ('  仓库   : {0}' -f $Cfg.Root)
  Write-Line ('  模型   : {0}' -f $Cfg.Models)
  Write-Line ('  输出   : {0}' -f $OutFile)
  Write-Line ('  日志   : {0}' -f $script:LogFile)
  Write-Line ('  脱敏   : {0}' -f $(if ($NoRedact) { '关闭' } else { '开启（用户名/机器名/令牌/邮箱/MAC）' }))
}

function Show-Menu {
  Write-Line ''
  foreach ($s in $Steps) {
    Write-Line ("  [{0,2}] {1,-34} {2}" -f $s.Id, $s.Title, $s.Manual)
  }
  Write-Line '  [ q] 退出'
  Write-Line ''
}

if ($Step -ne '') {
  $sel = $Steps | Where-Object { $_.Id -eq $Step }
  if (-not $sel) { Write-Warning "没有第 $Step 步"; exit 1 }
  Show-Header
  Invoke-Step $sel
  Write-Line ''
  Write-Line ('日志：{0}' -f $script:LogFile)
  exit 0
}

Show-Header
while ($true) {
  Show-Menu
  $choice = (Read-Host '选择步骤编号').Trim()
  if ($choice -match '^(?i)q$') { break }
  $sel = $Steps | Where-Object { $_.Id -eq $choice }
  if (-not $sel) {
    Write-Line '[x] 没有这个编号'
    continue
  }
  Invoke-Step $sel
}

Write-Line ''
Write-Line ('本次会话日志：{0}' -f $script:LogFile) 'Green'
