@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto env_ready
echo Project Python environment was not found.
echo See web\README.md for setup instructions.
pause
exit /b 1

:env_ready
set "PORT=8765"
if /I "%~1"=="--port" set "PORT=%~2"
netstat -ano | findstr /C:":%PORT%" | findstr /C:"LISTENING" >nul
if errorlevel 1 goto start_server

echo 端口 %PORT% 已有服务监听。
echo 如果 rrplot 页面已经打开，可直接使用；如需加载最新代码，请关闭原服务窗口后重新运行本脚本。
echo 如果是其他程序占用，请更换端口，例如：start-web.cmd --port 8766
pause
exit /b 0

:start_server
echo Open http://127.0.0.1:%PORT% in your browser.
echo Keep this window open while using the editor. Press Ctrl+C to stop.
".venv\Scripts\python.exe" "server\run.py" %*
if errorlevel 1 pause
