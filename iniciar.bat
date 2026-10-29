@echo off
REM Abre o painel do PATO no navegador (http://127.0.0.1:8000).
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python -m pato_app
