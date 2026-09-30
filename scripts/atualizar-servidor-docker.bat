@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM Atualiza o servidor na topologia de CONTAINERS (web + worker +
REM reports-mysql + redis, ver docker-compose.prod.yml).
REM
REM Diferente do atualizar-servidor.bat (NSSM + Python nativo), este e o
REM fluxo recomendado a partir da decisao de conteinerizar (2026-09-29).
REM
REM Regra de ouro mantida: NUNCA sobe a stack nova se a migration falhar --
REM o container antigo continua servindo com codigo + schema compativeis.
REM
REM Rollback: rode de novo com a tag anterior, ex:
REM   set IMAGE_TAG=2026-09-29-1830 && docker compose -f docker-compose.prod.yml up -d
REM (a tag da ultima atualizacao fica gravada em .last_image_tag)
REM ============================================================

cd /d "%~dp0.."

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd-HHmm"') do set NEW_TAG=%%I

echo.
echo [1/6] Baixando codigo mais recente (git pull)...
git pull origin main
if errorlevel 1 goto :fim_com_erro

echo.
echo [2/6] Construindo a imagem (tag %NEW_TAG%)...
set IMAGE_TAG=%NEW_TAG%
docker compose -f docker-compose.prod.yml build web
if errorlevel 1 goto :fim_com_erro

echo.
echo [3/6] Subindo banco e Redis...
docker compose -f docker-compose.prod.yml up -d reports-mysql redis
if errorlevel 1 goto :fim_com_erro

echo.
echo [4/6] Aplicando migrations do reports_db...
docker compose -f docker-compose.prod.yml run --rm --no-deps web alembic upgrade head
if errorlevel 1 goto :fim_com_erro

REM expansao tardia (!VAR!): dentro de um bloco ( ... ) o %VAR% e lido ANTES do set, e o arquivo de rollback saia vazio
set PREV_TAG=latest
if exist .last_image_tag (
    set /p PREV_TAG=<.last_image_tag
)
echo !PREV_TAG!> .last_image_tag.bak
echo %NEW_TAG%> .last_image_tag

echo.
echo [5/6] Subindo web + worker com a tag nova...
docker compose -f docker-compose.prod.yml up -d
if errorlevel 1 (
    echo.
    echo ERRO ao subir a stack. A tag anterior era !PREV_TAG! --
    echo rollback: set IMAGE_TAG=!PREV_TAG! ^&^& docker compose -f docker-compose.prod.yml up -d
    goto :fim_com_erro
)

echo.
echo [6/6] Conferindo se o web responde (ate 90 s)...
set WEB_UP=0
for /l %%I in (1,1,18) do (
    if !WEB_UP! equ 0 (
        REM qualquer resposta HTTP conta (200 ou 503): o 503 do /health pode ser so o Projectile lento,
        REM e ele NAO justifica reverter. Sem resposta nenhuma, o container novo nao subiu.
        powershell -NoProfile -Command "try { $null = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 http://localhost:8011/health; 'UP' } catch { if ($_.Exception.Response) { 'UP' } else { 'DOWN' } }" | findstr /b "UP" >nul && set WEB_UP=1
        if !WEB_UP! equ 0 timeout /t 5 /nobreak >nul
    )
)
docker compose -f docker-compose.prod.yml ps

if !WEB_UP! equ 0 (
    echo.
    echo ============================================================
    echo O web NAO respondeu em 90 s. Voltando para a tag !PREV_TAG!...
    echo ATENCAO: a migration NAO e desfeita. Se esta versao mudou o schema,
    echo confira se o codigo antigo e compativel antes de liberar o uso.
    echo ============================================================
    set IMAGE_TAG=!PREV_TAG!
    docker compose -f docker-compose.prod.yml up -d
    echo !PREV_TAG!> .last_image_tag
    goto :fim_com_erro
)

echo.
echo ============================================================
echo Atualizacao concluida (tag %NEW_TAG%).
echo Rollback guardado em .last_image_tag.bak.
echo ============================================================
goto :fim

:fim_com_erro
echo.
echo ============================================================
echo A atualizacao PAROU por causa de um erro acima. A stack que
echo estava de pe continua rodando. Corrija e rode de novo.
echo ============================================================

:fim
pause
