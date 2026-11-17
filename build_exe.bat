@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Сборка IslandLauncher.exe

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python не найден. Установите Python 3.10+ с python.org ^(галочка "tcl/tk and IDLE" и "Add to PATH"^) и запустите снова.
  pause
  exit /b 1
)
echo Использую: %PY%
echo.
%PY% -m pip install --upgrade pyinstaller || goto :fail
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed --version-file version_info.txt --name IslandLauncher launcher.py || goto :fail
copy /y "dist\IslandLauncher.exe" "IslandLauncher.exe" >nul || goto :fail
rmdir /s /q build dist 2>nul
del /q IslandLauncher.spec 2>nul
echo.
echo Готово: %~dp0IslandLauncher.exe
echo Положите его рядом с main.py ^(можно оставить здесь^) и запускайте двойным кликом.
pause
exit /b 0

:fail
echo.
echo Сборка не удалась, смотрите сообщения выше.
pause
exit /b 1
