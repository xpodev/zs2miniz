rem @ECHO OFF

set PYTHONPATH=%PYTHONPATH%;%~dp0src\

py "%~dp0zs_main.py" c %1
