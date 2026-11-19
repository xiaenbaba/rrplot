@echo off
call "%~dp0web-service.cmd" restart %*
exit /b %ERRORLEVEL%
