@echo off
chcp 65001 > nul
cd /d "%~dp0"
set PYTHONUTF8=1

echo.
echo  파이프라인 대시보드와 실험 서버를 띄웁니다.
echo  창을 닫으면 서버가 꺼집니다.
echo.

start "" http://localhost:3003/tools/dashboard.html
.\.venv\Scripts\python.exe tools\session_server.py

pause
