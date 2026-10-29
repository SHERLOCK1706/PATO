@echo off
REM Instala o PATO em um ambiente virtual (.venv) nesta pasta. Requer Python 3.10+ (python.org).
cd /d "%~dp0"
python -m venv .venv || goto erro
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || goto erro
echo.
echo Instalacao concluida. Use iniciar.bat para abrir o painel.
pause
exit /b 0
:erro
echo Falha na instalacao. Verifique se o Python 3.10+ esta instalado e no PATH.
pause
exit /b 1
