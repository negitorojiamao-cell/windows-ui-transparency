@echo off
cd /d "%~dp0"
py -3 windows_ui_transparency.py
if errorlevel 1 pause
