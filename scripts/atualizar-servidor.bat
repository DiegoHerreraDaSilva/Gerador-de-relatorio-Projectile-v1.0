@echo off
setlocal

REM ============================================================
REM Atualiza o servidor com o codigo mais recente da branch main.
REM Rode este arquivo (duplo-clique) sempre que quiser aplicar uma
REM atualizacao que ja foi mergeada no GitHub.
REM
REM Precisa ser executado a partir da pasta raiz do checkout do
REM projeto no servidor (a pasta que tem "backend" e "frontend"
REM dentro) -- se voce mover esse arquivo, ajuste o "cd" abaixo.
REM
REM Ajuste SERVICE_NAME se o backend roda como Servico do Windows
REM via nssm. Deixe em branco ("") se voce roda o uvicorn na mao
REM num terminal -- nesse caso o script so avisa no final que
REM precisa reiniciar manualmente.
REM ============================================================
set SERVICE_NAME=

cd /d "%~dp0.."

echo.
echo [1/5] Baixando codigo mais recente (git pull)...
git pull origin main
if errorlevel 1 (
    echo.
    echo ERRO ao dar git pull. Verifique se ha mudancas locais nao
    echo commitadas ou conflito, e resolva antes de rodar de novo.
    goto :fim_com_erro
)

echo.
echo [2/5] Instalando dependencias do backend...
pip install -r backend\requirements.txt
if errorlevel 1 (
    echo.
    echo ERRO ao instalar dependencias do backend.
    goto :fim_com_erro
)

echo.
echo [3/5] Subindo reports-mysql e aplicando migrations...
REM Regra de ouro: NUNCA reiniciar o uvicorn com codigo novo se a migration
REM nao confirmou sucesso -- se algo falhar aqui, o processo antigo (codigo +
REM schema compativeis entre si) continua servindo normalmente.
docker compose up -d reports-mysql
if errorlevel 1 (
    echo.
    echo ERRO ao subir o container reports-mysql via Docker.
    goto :fim_com_erro
)
alembic upgrade head
if errorlevel 1 (
    echo.
    echo ERRO ao aplicar migrations do reports_db.
    goto :fim_com_erro
)

echo.
echo [4/5] Buildando o frontend...
call npm --prefix frontend install
if errorlevel 1 (
    echo.
    echo ERRO ao instalar dependencias do frontend.
    goto :fim_com_erro
)
call npm --prefix frontend run build
if errorlevel 1 (
    echo.
    echo ERRO ao buildar o frontend.
    goto :fim_com_erro
)

echo.
echo [5/5] Reiniciando o backend...
if "%SERVICE_NAME%"=="" (
    echo.
    echo Nenhum SERVICE_NAME configurado neste script.
    echo Reinicie o backend na mao: feche o terminal do uvicorn e
    echo rode de novo:
    echo   python -m uvicorn backend.app.main:app --port 8011
) else (
    nssm restart %SERVICE_NAME%
    if errorlevel 1 (
        echo.
        echo ERRO ao reiniciar o servico "%SERVICE_NAME%" via nssm.
        goto :fim_com_erro
    )
    echo Servico "%SERVICE_NAME%" reiniciado.
)

echo.
echo ============================================================
echo Atualizacao concluida com sucesso!
echo ============================================================
goto :fim

:fim_com_erro
echo.
echo ============================================================
echo A atualizacao PAROU por causa de um erro acima. Corrija e
echo rode este script de novo.
echo ============================================================

:fim
echo.
pause
