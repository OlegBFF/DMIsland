@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title Island Pro — запуск
echo.
echo   Island Pro: проверяю, всё ли готово к запуску...
echo.

if not exist "main.py" (
  echo   Не найден main.py. Распакуйте архив целиком в папку и запустите этот файл оттуда.
  echo.
  pause
  exit /b 1
)

set "PYC="
call :probe py -3
if not defined PYC call :probe python
if not defined PYC call :probe_paths
if defined PYC goto :have_python

echo   Python не найден — ставлю автоматически ^(нужен один раз, права администратора не требуются^).
where winget >nul 2>nul
if not errorlevel 1 (
  echo   Способ 1: winget...
  winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
  call :probe_paths
)
if not defined PYC (
  echo   Способ 2: официальный установщик с python.org...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install_python.ps1"
  call :probe_paths
)
if not defined PYC (
  echo.
  echo   Не получилось поставить Python автоматически.
  echo   Установите Python 3.12 ^(64-бит^) с https://www.python.org/downloads/windows/
  echo   и отметьте галочку "Add python.exe to PATH", затем запустите этот файл снова.
  echo.
  pause
  exit /b 1
)

:have_python
for /f "delims=" %%i in ('%PYC% -c "import sys;print(sys.executable)"') do set "PYEXE=%%i"
set "PYW=%PYEXE:python.exe=pythonw.exe%"
if not exist "%PYW%" set "PYW=%PYEXE%"
echo   Python: %PYEXE%
echo   Запускаю лаунчер: он сам создаст окружение, скачает библиотеки ^(при первом запуске — несколько минут^)
echo   и запустит остров. Это окно можно закрыть.
start "" "%PYW%" "%~dp0launcher.py"
timeout /t 4 >nul
exit /b 0

:probe
%* -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 8) else 1)" >nul 2>nul
if not errorlevel 1 set "PYC=%*"
exit /b 0

:probe_paths
for /f "delims=" %%d in ('dir /b /ad /o-n "%LOCALAPPDATA%\Programs\Python\Python3*" 2^>nul') do (
  if not defined PYC call :probe "%LOCALAPPDATA%\Programs\Python\%%d\python.exe"
)
exit /b 0
