@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Create .venv and install requirements first.
  exit /b 1
)
set "PORT="
for %%P in (8501 8502 8503 8504 8505) do (
  ".venv\Scripts\python.exe" -c "import socket; s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); s.bind(('127.0.0.1',%%P)); s.close()"
  if not errorlevel 1 (
    set "PORT=%%P"
    goto :launch
  )
)
echo No free localhost port was found in 8501-8505. Close a dashboard process or run:
echo .venv\Scripts\python.exe -m streamlit run dashboard.py --server.address 127.0.0.1 --server.port ^<an available port^>
exit /b 1

:launch
echo Starting the dashboard at http://127.0.0.1:%PORT%
".venv\Scripts\python.exe" -m streamlit run dashboard.py --server.address 127.0.0.1 --server.port %PORT%
endlocal
