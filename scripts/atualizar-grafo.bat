@echo off
rem Atualiza o grafo do Graphify (https://github.com/Graphify-Labs/graphify) do projeto.
rem
rem - Roda sobre uma COPIA LIMPA (git archive = so arquivos versionados), em
rem   ..\..\graphify-repo: .env, backend\data, dist e node_modules nunca entram.
rem - So a parte LOCAL (AST): sem LLM, sem chave de API. Nao use `graphify extract`
rem   nem o backend semantico aqui, e nao rode `graphify install`.
rem - Reflete o ultimo COMMIT (trabalho nao commitado nao entra).
rem
rem Requer: uv tool install graphifyy
setlocal
set "REPO=%~dp0.."
set "OUT=%REPO%\..\graphify-repo"

if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%" || exit /b 1

pushd "%REPO%"
git archive HEAD | tar -x -C "%OUT%" || (popd & exit /b 1)
popd

pushd "%OUT%"
graphify update . || (popd & exit /b 1)
graphify cluster-only . --no-label || (popd & exit /b 1)
popd

echo.
echo Grafo pronto em: %OUT%\graphify-out  (GRAPH_REPORT.md, graph.html, graph.json)
endlocal
