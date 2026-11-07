@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === PB Store: populando o MongoDB com produtos de exemplo ===
echo.

REM ---------- 1. Python + dependencias ----------
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Criando ambiente virtual...
    python -m venv .venv || goto erro_python
)
echo [1/3] Verificando dependencias (na primeira vez demora alguns minutos)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto erro_pip

REM ---------- 2. Servidor MongoDB ----------
echo [2/3] Verificando o servidor MongoDB...
sc query MongoDB >nul 2>nul
if not errorlevel 1 (
    sc query MongoDB | find "RUNNING" >nul || (
        echo       Servico MongoDB parado. Tentando iniciar...
        net start MongoDB >nul 2>nul
    )
)
docker info >nul 2>nul
if not errorlevel 1 (
    echo       Docker aberto: subindo container do MongoDB...
    docker compose up -d mongo >nul
)
".venv\Scripts\python.exe" -m scripts.checar_mongo || goto erro_mongo

REM ---------- 3. Seed ----------
echo [3/3] Populando o banco...
".venv\Scripts\python.exe" -m scripts.seed --reset || goto erro_seed

echo.
set /p ABRIR=Abrir o Streamlit agora? (S/N): 
if /i "%ABRIR%"=="S" ".venv\Scripts\python.exe" -m streamlit run app.py
goto fim

:erro_python
echo.
echo ERRO: Python nao encontrado. Instale em python.org e marque "Add python.exe to PATH".
goto fim

:erro_pip
echo.
echo ERRO: falha ao instalar as dependencias. Verifique sua internet e rode de novo.
goto fim

:erro_mongo
echo.
echo O Compass sozinho NAO e o banco: ele so se conecta a um servidor MongoDB.
echo Opcoes:
echo   a) Instale o "MongoDB Community Server" (.msi) marcando "Install as a Service"
echo      https://www.mongodb.com/try/download/community
echo   b) Ou abra o Docker Desktop e rode este arquivo de novo
echo   c) Ou use o MongoDB Atlas e coloque MONGO_URI no arquivo .env
goto fim

:erro_seed
echo.
echo ERRO ao popular o banco. Veja a mensagem acima.

:fim
echo.
pause
