Add-Type -Namespace H -Name Win -MemberDefinition @"
[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
[DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
"@
$h = [H.Win]::GetConsoleWindow()
[H.Win]::SetWindowPos($h, [IntPtr]::Zero, 2560, 0, 1920, 1080, 0x0040) | Out-Null
$Host.UI.RawUI.WindowTitle = 'LingBotDeploy - Windows PowerShell'
Write-Host 'Windows PowerShell'
Write-Host 'Copyright (C) Microsoft Corporation. All rights reserved.'
Write-Host ''