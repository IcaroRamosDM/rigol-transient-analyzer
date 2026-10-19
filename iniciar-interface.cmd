@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0interface\iniciar-windows.ps1" %*
if errorlevel 1 pause
