@echo off
chcp 65001 >nul
title m4s2mp4
cd /d "%~dp0"

where python >nul 2>nul
if not errorlevel 1 (
    python m4s2mp4.py
) else (
    py -3 m4s2mp4.py
)

if errorlevel 1 pause
