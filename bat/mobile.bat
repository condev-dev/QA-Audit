@echo off
cd /d "%~dp0"

set QA_HOST=0.0.0.0
set QA_PORT=5000

start "QA Server" cmd /k "cd QA-Audit && python app.py"

start "QA Tunnel" cmd /k "for /l %%i in (0,0,1) do (ssh -p 443 -i %USERPROFILE%\.ssh\id_ed25519 -o StrictHostKeyChecking=no -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -R qa.condev.ir:80:127.0.0.1:5000 serveo.net & timeout /t 5 /nobreak)"

start chrome http://127.0.0.1:5000/