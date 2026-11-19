@echo off
call "%~dp0web-service.cmd" status %*
exit /b %ERRORLEVEL%
