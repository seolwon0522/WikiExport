@echo off
chcp 65001 > nul
cls
echo.
echo ========================================
echo    Redmine Wiki Export Tool
echo ========================================
echo.

cd /d "%~dp0"

if not exist config.json (
    echo ❌ Error: config.json not found!
    echo Please create config.json first with your Redmine credentials.
    pause
    exit /b 1
)

echo 🚀 Starting wiki export...
echo.

python mirror_wiki.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo ✅ Export completed successfully!
    echo ========================================
    echo.
    echo 📂 Output file: wikiexport.html
    echo 📁 Images folder: images\
    echo.
    echo Opening file explorer...
    explorer "%~dp0"
) else (
    echo.
    echo ❌ Export failed!
    echo Please check the error messages above.
)

pause
