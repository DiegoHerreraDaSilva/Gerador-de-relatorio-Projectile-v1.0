<#
.SYNOPSIS
Restaura um backup do reports_db gerado por backup-reports-db.ps1.

.DESCRIPTION
- Aceita .sql.gz ou .sql.
- Restaura para -TargetDb (padrao reports_db), criando o banco se nao
  existir.
- Se o banco de destino JA TIVER tabelas, exige -Force E a confirmacao
  digitada "RESTAURAR" — porque o -Force APAGA o banco atual antes de
  restaurar.
- No fim mostra a contagem de linhas das tabelas principais, para conferir
  contra o esperado.
- Opcionalmente copia os artefatos do backup de volta para
  backend\data\report_artifacts (-ArtifactsSource).

IMPORTANTE: pare o backend antes de restaurar o reports_db em producao —
restaurar com o sistema no ar perde o que for gravado no meio do caminho.

EXEMPLO
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\restore-reports-db.ps1 -DumpFile "D:\Backups\relatorio\reports_db_2026-09-29_060000.sql.gz"
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\restore-reports-db.ps1 -DumpFile "...\reports_db_2026-09-29_060000.sql.gz" -ArtifactsSource "D:\Backups\relatorio\artifacts"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$DumpFile,
    [string]$TargetDb = 'reports_db',
    [string]$ContainerName = '',
    [string]$ArtifactsSource = '',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Resolve-Container {
    if ($ContainerName) { return $ContainerName }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker nao encontrado no PATH. Instale/abra o Docker Desktop.'
    }
    $found = @(docker ps --filter 'label=com.docker.compose.service=reports-mysql' --format '{{.Names}}' 2>$null)
    if ($LASTEXITCODE -ne 0) { throw 'Docker nao respondeu. O Docker esta rodando?' }
    if ($found.Count -eq 0) {
        throw "Container 'reports-mysql' nao encontrado. Suba com: docker compose up -d reports-mysql"
    }
    return $found[0]
}

function Invoke-InContainer {
    # Mesma tecnica do backup-reports-db.ps1: o script viaja como ARQUIVO
    # (docker cp), nao como argumento — evita o inferno de aspas do
    # PowerShell 5.1 e a senha so existe dentro do container.
    param([string]$Container, [string]$ScriptText, [switch]$Capture)

    $hostTmp = Join-Path $env:TEMP ('relatorio_sh_' + [Guid]::NewGuid().ToString('N') + '.sh')
    $insideTmp = '/tmp/relatorio_sh_' + [Guid]::NewGuid().ToString('N') + '.sh'
    [IO.File]::WriteAllText($hostTmp, $ScriptText, [Text.Encoding]::ASCII)
    try {
        docker cp $hostTmp "${Container}:$insideTmp" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao copiar o script para o container (docker cp).' }
        $output = @(docker exec $Container sh $insideTmp)
        $code = $LASTEXITCODE
        if ($Capture) { return @{ Output = $output; ExitCode = $code } }
        if ($output.Count -gt 0) { $output | Write-Host }
        if ($code -ne 0) { throw "Script no container falhou (exit $code)." }
    } finally {
        Remove-Item -LiteralPath $hostTmp -Force -ErrorAction SilentlyContinue
        docker exec $Container rm -f $insideTmp 2>$null | Out-Null
    }
}

if ($TargetDb -notmatch '^[A-Za-z0-9_]+$') { throw "Nome de banco invalido: $TargetDb" }
if (-not (Test-Path -LiteralPath $DumpFile)) { throw "Arquivo de backup nao encontrado: $DumpFile" }
$dumpItem = Get-Item -LiteralPath $DumpFile
if ($dumpItem.Length -le 0) { throw "Arquivo de backup vazio: $DumpFile" }
$isGz = $DumpFile.ToLower().EndsWith('.gz')

$container = Resolve-Container

Write-Host "Conferindo o banco de destino '$TargetDb' no container '$container'..."
$checkScript = @'
MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = '{0}'"
'@ -f $TargetDb
$checkScript = $checkScript -replace "`r`n", "`n"
$res = Invoke-InContainer -Container $container -ScriptText $checkScript -Capture
if ($res.ExitCode -ne 0) {
    throw "Nao consegui consultar o banco de destino (exit $($res.ExitCode)): $($res.Output -join ' ')"
}
$tableCount = [int]($res.Output | Select-Object -First 1)
$exists = $tableCount -gt 0

if ($exists) {
    if (-not $Force) {
        throw "O banco '$TargetDb' ja tem $tableCount tabela(s). Para substituir o conteudo rode de novo com -Force (isso APAGA o banco atual)."
    }
    Write-Host ''
    Write-Host "ATENCAO: -Force vai APAGAR o banco '$TargetDb' atual e restaurar o dump por cima." -ForegroundColor Yellow
    Write-Host 'Pare o backend antes de continuar, se ele estiver rodando.' -ForegroundColor Yellow
    $answer = Read-Host 'Digite RESTAURAR para confirmar'
    if ($answer -ne 'RESTAURAR') {
        Write-Host 'Cancelado. Nada foi alterado.'
        exit 1
    }
}

$insideDump = if ($isGz) { '/tmp/relatorio_restore.sql.gz' } else { '/tmp/relatorio_restore.sql' }
$decompress = if ($isGz) { 'gunzip -f /tmp/relatorio_restore.sql.gz' } else { ':' }

if ($exists -and $Force) {
    $reset = "DROP DATABASE IF EXISTS $TargetDb; CREATE DATABASE $TargetDb CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
} else {
    $reset = "CREATE DATABASE IF NOT EXISTS $TargetDb CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
}

Write-Host "Copiando $($dumpItem.Name) para o container..."
docker cp $DumpFile "${container}:$insideDump" | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Falha ao copiar o dump para o container (docker cp).' }

$importScript = @'
set -e
MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -e "{0}"
{1}
MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot {2} < /tmp/relatorio_restore.sql
echo 'Restaurado. Contagens (tabela=linhas):'
for t in reports report_versions report_generation mgmt_kpi_samples auto_reports; do
  n=$(MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B -e "SELECT COUNT(*) FROM {2}.$t" 2>&1) || n="nao existe neste dump"
  echo "  $t=$n"
done
'@ -f $reset, $decompress, $TargetDb
$importScript = $importScript -replace "`r`n", "`n"

try {
    Write-Host 'Restaurando...'
    Invoke-InContainer -Container $container -ScriptText $importScript
} finally {
    docker exec $container rm -f /tmp/relatorio_restore.sql /tmp/relatorio_restore.sql.gz 2>$null | Out-Null
}

if ($ArtifactsSource) {
    if (-not (Test-Path -LiteralPath $ArtifactsSource)) {
        throw "Pasta de artefatos nao encontrada: $ArtifactsSource"
    }
    $artifactsDst = Join-Path $root 'backend\data\report_artifacts'
    New-Item -ItemType Directory -Path $artifactsDst -Force | Out-Null
    Write-Host "Restaurando artefatos para $artifactsDst..."
    robocopy $ArtifactsSource $artifactsDst /E /R:2 /W:5 /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy falhou (exit $LASTEXITCODE)." }
    Write-Host 'Artefatos restaurados.'
}

Write-Host ''
Write-Host "Restore concluido no banco '$TargetDb'." -ForegroundColor Green
