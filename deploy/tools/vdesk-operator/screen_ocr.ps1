<#
  截图 + OCR (带坐标): 抓一块屏幕, 读出文字并给出每行的包围盒.
  用途: 在"看不见屏幕"时确认 GUI 状态, 并能按文字精确点击 (比盲点坐标稳得多)。

  用法:
    powershell -File screen_ocr.ps1 -X 2560 -Y 0 -W 1920 -H 1080 -- 只打印文字
    powershell -File screen_ocr.ps1 -X ... -W ... -H ... -Boxes -- 每行附带绝对坐标
#>
param(
  [int]$X = 2560, [int]$Y = 0, [int]$W = 1920, [int]$H = 1080,
  [string]$Image = "$env:TEMP\vdesk_ocr.png",
  [string]$Filter = "",
  [switch]$Boxes
)

$ErrorActionPreference = 'Stop'
& ffmpeg -hide_banner -loglevel error -f gdigrab -offset_x $X -offset_y $Y `
    -video_size "$($W)x$($H)" -i desktop -frames:v 1 -y $Image
if (-not (Test-Path -LiteralPath $Image)) { Write-Error "抓图失败"; exit 2 }

Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null
$null = [Windows.Media.Ocr.OcrEngine,            Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Storage.StorageFile,            Windows.Foundation, ContentType=WindowsRuntime]

$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
  $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) {
  $m = $asTask.MakeGenericMethod($type); $t = $m.Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result
}

$engine  = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) { Write-Error "没有可用的 OCR 语言包"; exit 3 }
$file    = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Image)) ([Windows.Storage.StorageFile])
$stream  = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap  = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$result  = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

$nLines = $result.Lines.Count
for ($li = 0; $li -lt $nLines; $li++) {
  $line = $result.Lines.GetAt($li)
  if ($Filter -and ($line.Text -notmatch $Filter)) { continue }
  if ($Boxes) {
    $minX = [double]::MaxValue; $minY = [double]::MaxValue; $maxX = 0; $maxY = 0
    $nWords = $line.Words.Count
    for ($wi = 0; $wi -lt $nWords; $wi++) {
      $w = $line.Words.GetAt($wi)
      $r = $w.BoundingRect
      if ($r.X -lt $minX) { $minX = $r.X }
      if ($r.Y -lt $minY) { $minY = $r.Y }
      if (($r.X + $r.Width)  -gt $maxX) { $maxX = $r.X + $r.Width }
      if (($r.Y + $r.Height) -gt $maxY) { $maxY = $r.Y + $r.Height }
    }
    $cx = [int]($X + ($minX + $maxX) / 2)
    $cy = [int]($Y + ($minY + $maxY) / 2)
    Write-Output ("{0},{1}`t{2}" -f $cx, $cy, $line.Text)
  } else {
    Write-Output $line.Text
  }
}