@echo off
rem ---------------------------------------------------------------------------
rem LingBot-World 1.3B Windows native deployment - step runner (entry point)
rem Keep this file ASCII-only: cmd.exe parses batch files by byte, and non-ASCII
rem text inside a batch file breaks depending on the active code page.
rem All Chinese text and the real logic live in deploy-steps.ps1.
rem -ExecutionPolicy Bypass applies to this process only; it does not change the
rem machine or user execution policy.
rem ---------------------------------------------------------------------------
setlocal
chcp 65001 >nul
set "PS1=%~dp0deploy-steps.ps1"
if not exist "%PS1%" (
  echo [x] deploy-steps.ps1 not found next to this file
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo [x] exit code %RC%
echo Press any key to close this window.
pause >nul
exit /b %RC%
