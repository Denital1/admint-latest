@echo off
setlocal
cd /d "%~dp0"
if not exist backend\.venv\Scripts\python.exe goto setup_first
if not exist node_modules\next\dist\bin\next goto setup_first
pushd backend
start "AdMint API" cmd /k .venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
popd
start "AdMint Web" cmd /k npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
echo Open http://127.0.0.1:3000 in Chrome after both servers are ready.
exit /b 0
:setup_first
echo Run SETUP-WINDOWS.cmd first.
pause
exit /b 1
