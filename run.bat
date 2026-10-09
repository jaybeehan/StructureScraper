@echo off
rem Launches Structure Scraper in the default browser. Close this window to stop.
cd /d "%~dp0"
where py >nul 2>nul && (py structure_scraper.py & goto :end)
where python >nul 2>nul && (python structure_scraper.py & goto :end)
echo Python was not found. Install Python 3 from python.org.
:end
pause
