@echo off
REM Instala o PATO em um ambiente virtual (.venv) nesta pasta.
REM Requer Python 3.10 ou mais novo (python.org). So instala pacotes prontos (nunca compila: dispensa o Visual C++);
REM se houver o 3.13 (o mais testado), ele e preferido.
cd /d "%~dp0"

set "PY="
REM 1) lancador "py" do Windows: escolhe uma versao compativel, da mais nova para a mais antiga
for %%v in (3.13 3.12 3.11 3.10) do (
    if not defined PY (
        py -%%v --version >nul 2>&1 && set "PY=py -%%v"
    )
)
REM 2) senao, o "python" do PATH (3.10 ou mais novo, inclusive 3.14/3.15)
if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3,10) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY goto sem_python

echo Usando: %PY%
%PY% --version
if exist .venv rmdir /s /q .venv
%PY% -m venv .venv || goto erro_venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
echo.
echo Instalando os componentes essenciais...
pip install --only-binary=:all: -r requirements.txt || goto erro_pip
echo.
echo Instalando os componentes opcionais (se algum falhar, o sistema funciona assim mesmo)...
for /f "usebackq eol=# tokens=*" %%p in ("requirements-opcionais.txt") do (
    pip install --only-binary=:all: "%%p" >nul 2>&1 && (echo   ok: %%p) || (echo   aviso: %%p nao instalado - opcional)
)
echo.
echo OCR das cotacoes digitalizadas (Tesseract, opcional)...
set "TESS="
where tesseract >nul 2>&1 && set "TESS=1"
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "TESS=1"
if defined TESS echo   ok: Tesseract encontrado
if not defined TESS (
    winget install -e --id UB-Mannheim.TesseractOCR --accept-package-agreements --accept-source-agreements >nul 2>&1 && echo   ok: Tesseract instalado || echo   aviso: Tesseract nao instalado - baixe em github.com/UB-Mannheim/tesseract/wiki. Sem ele a cotacao digitalizada e preenchida a mao.
)
if not exist tessdata\por.traineddata (
    mkdir tessdata 2>nul
    powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing https://github.com/tesseract-ocr/tessdata_fast/raw/main/por.traineddata -OutFile tessdata\por.traineddata; Write-Host '  ok: idioma portugues do OCR' } catch { Write-Host '  aviso: idioma portugues do OCR nao baixado' }"
)
echo.
echo Instalacao concluida. Use iniciar.bat para abrir o painel.
pause
exit /b 0

:sem_python
echo.
echo Nao encontrei o Python 3.10 ou mais novo neste computador.
python --version 2>nul
echo.
echo Instale o Python 3.13 (python.org/downloads - "Windows installer (64-bit)") marcando "Add to PATH"
echo e rode instalar.bat de novo.
pause
exit /b 1
:erro_venv
echo Nao foi possivel criar o ambiente virtual (.venv). Verifique a instalacao do Python.
pause
exit /b 1
:erro_pip
echo.
echo Falha ao instalar os componentes essenciais. Verifique a conexao com a internet e a mensagem acima.
pause
exit /b 1
