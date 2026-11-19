@echo off
call "%~dp0web-service.cmd" start %*
exit /b %ERRORLEVEL%
