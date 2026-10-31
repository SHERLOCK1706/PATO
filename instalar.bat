@echo off
REM Instala o PATO em um ambiente virtual (.venv) nesta pasta. Requer Python 3.10+ (python.org).
cd /d "%~dp0"
python --version >nul 2>&1 || goto sem_python
python -m venv .venv || goto erro_venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
echo.
echo Instalando os componentes essenciais...
pip install -r requirements.txt || goto erro_pip
echo.
echo Instalando os componentes opcionais (se algum falhar, o sistema funciona assim mesmo)...
for /f "usebackq eol=# tokens=*" %%p in ("requirements-opcionais.txt") do (
    pip install "%%p" >nul 2>&1 && (echo   ok: %%p) || (echo   aviso: %%p nao instalado - opcional)
)
echo.
echo Instalacao concluida. Use iniciar.bat para abrir o painel.
pause
exit /b 0
:sem_python
echo Python nao encontrado. Instale o Python 3.10 ou mais novo (python.org) marcando "Add to PATH".
pause
exit /b 1
:erro_venv
echo Nao foi possivel criar o ambiente virtual (.venv). Verifique a instalacao do Python.
pause
exit /b 1
:erro_pip
echo Falha ao instalar os componentes essenciais. Verifique a conexao com a internet e a mensagem acima.
pause
exit /b 1
