param([int]$X,[int]$Y,[int]$W,[int]$H,[string]$Image)
$ErrorActionPreference='Stop'
& ffmpeg -hide_banner -loglevel error -f gdigrab -offset_x $X -offset_y $Y -video_size "$($W)x$($H)" -i desktop -frames:v 1 -y $Image
Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null
$null=[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$null=[Windows.Graphics.Imaging.BitmapDecoder,Windows.Foundation,ContentType=WindowsRuntime]
$null=[Windows.Storage.StorageFile,Windows.Foundation,ContentType=WindowsRuntime]
$asTask=([System.WindowsRuntimeSystemExtensions].GetMethods()|Where-Object{$_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'})[0]
function Await($op,$type){$m=$asTask.MakeGenericMethod($type);$t=$m.Invoke($null,@($op));$t.Wait(-1)|Out-Null;$t.Result}
$engine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
$file=Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Image)) ([Windows.Storage.StorageFile])
$stream=Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder=Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap=Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$res=Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
foreach($line in $res.Lines){
  $sz = $line.Words.Size
  $w0 = $line.Words.GetAt(0)
  $r = $w0.BoundingRect
  $wl = $line.Words.GetAt($sz-1)
  $rl = $wl.BoundingRect
  $x1=[int]($X+$r.X); $y1=[int]($Y+$r.Y)
  $x2=[int]($X+$rl.X+$rl.Width); $y2=[int]($Y+$rl.Y+$rl.Height)
  Write-Output ("[{0},{1} - {2},{3}] {4}" -f $x1,$y1,$x2,$y2,$line.Text)
}