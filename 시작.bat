@echo off
chcp 65001 > nul
cd /d "%~dp0"
set PYTHONUTF8=1

rem Wait for the server to answer, then open the dashboard. Opening it
rem first fails: nothing is listening on :3003 yet.
start "" /b powershell -NoProfile -Command "for($i=0;$i -lt 60;$i++){try{$c=New-Object Net.Sockets.TcpClient;$c.Connect('127.0.0.1',3003);$c.Close();Start-Process 'http://localhost:3003/web/dashboard.html';break}catch{Start-Sleep -Milliseconds 500}}"

echo.
echo  대시보드를 띄웁니다. 이 PC 에서만 열립니다.
echo.
echo      http://localhost:3003/web/dashboard.html
echo.
echo  창을 닫으면 서버가 꺼집니다.
echo.

.\.venv\Scripts\python.exe -m senior_ui.experiment.server

pause
