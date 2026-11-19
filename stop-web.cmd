@echo off
call "%~dp0web-service.cmd" stop %*
exit /b %ERRORLEVEL%
