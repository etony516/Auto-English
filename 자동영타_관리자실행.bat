@echo off
cd /d "%~dp0"
powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command "Start-Process -FilePath 'pythonw.exe' -ArgumentList 'auto_eng_gui.pyw' -WorkingDirectory (Get-Location).Path -Verb RunAs"
exit /b 0
