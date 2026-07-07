@echo off
:: Beer Game CISLOG — Servidor Web
:: Execute este arquivo para iniciar o servidor na sua máquina.
:: Requer Miniconda com o ambiente "beergame" já criado.

title Beer Game Web — Servidor Local

:: ── Ativar o ambiente conda existente ──────────────────────────────────────
call conda activate beergame 2>nul
if errorlevel 1 (
    echo.
    echo [ERRO] Ambiente "beergame" nao encontrado.
    echo        Execute primeiro: conda create -n beergame python=3.12 -y
    echo.
    pause & exit /b 1
)

:: ── Instalar dependências web (só na 1ª vez) ────────────────────────────────
echo [INFO] Instalando dependencias web...
pip install -q fastapi "uvicorn[standard]" python-multipart

:: ── Verificar arquivos do jogo ──────────────────────────────────────────────
if not exist engine.py (
    echo.
    echo [ERRO] engine.py nao encontrado nesta pasta.
    echo        Certifique-se que este arquivo esta na mesma pasta que:
    echo          engine.py  ai_player.py  storage.py
    echo.
    pause & exit /b 1
)

:: ── Iniciar servidor ────────────────────────────────────────────────────────
echo.
echo ================================================
echo   Beer Game CISLOG — Servidor Web
echo   Acesse: http://localhost:8000
echo   Pressione Ctrl+C para encerrar
echo ================================================
echo.

python server_web.py

pause
