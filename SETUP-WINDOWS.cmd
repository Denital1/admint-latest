@echo off
setlocal
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 goto missing_node
where npm.cmd >nul 2>nul
if errorlevel 1 goto missing_node
if exist backend\.venv\Scripts\python.exe goto python_ready
where py >nul 2>nul
if errorlevel 1 (set "ADMINT_PY=python") else (set "ADMINT_PY=py -3.12")
%ADMINT_PY% -c "import sys; assert sys.version_info[:2] == (3, 12), 'Use Python 3.12'"
if errorlevel 1 goto missing_python
:python_ready
node -e "if(Number(process.versions.node.split('.')[0])<22)process.exit(1)"
if errorlevel 1 goto missing_node
call npm.cmd ci
if errorlevel 1 goto failed
pushd backend
if not exist .venv\Scripts\python.exe %ADMINT_PY% -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe manage.py migrate --noinput
if errorlevel 1 goto failed
.venv\Scripts\python.exe manage.py check
if errorlevel 1 goto failed
popd
echo Setup complete. Run START-WINDOWS.cmd.
pause
exit /b 0
:missing_node
echo Install Node.js 22 LTS, then reopen this script.
pause
exit /b 1
:missing_python
echo Install Python 3.12 with Add to PATH, then reopen this script.
pause
exit /b 1
:failed
echo Setup did not finish. Read the error above before starting the site.
pause
exit /b 1
