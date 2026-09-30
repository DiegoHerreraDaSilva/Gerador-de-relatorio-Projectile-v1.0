<#
.SYNOPSIS
Backup do reports_db (MySQL em Docker) e dos artefatos de relatorio.

.DESCRIPTION
- Dump logico do banco com mysqldump --single-transaction, comprimido com
  gzip DENTRO do container. A senha do banco nunca sai do container: o
  script usa a propria variavel MYSQL_ROOT_PASSWORD que o Docker injeta no
  container (docker-compose.yml) junto com MYSQL_PWD, nunca argumento de
  linha de comando.
- O dump cai em <Dest>\reports_db_<data-hora>.sql.gz.
- Os artefatos (backend\data\report_artifacts) vao para <Dest>\artifacts
  por copia incremental (robocopy /E): artefato apagado no servidor NAO e
  apagado do backup (protege contra apagar por engano).
- Retencao: remove dumps .sql.gz mais antigos que -RetentionDays; os
  artefatos nunca sao removidos por este script.

EXEMPLO
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\backup-reports-db.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\backup-reports-db.ps1 -Dest "D:\Backups\relatorio" -RetentionDays 60

AGENDADOR DE TAREFAS (Windows): crie uma tarefa diaria com
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<repo>\scripts\backup-reports-db.ps1" -Dest "<pasta>"
Rode como um usuario com acesso ao Docker e a pasta de destino. Nao use a
conta SYSTEM sem informar -Dest explicitamente (o padrao usa %USERPROFILE%).
#>
[CmdletBinding()]
param(
    # Pasta de destino. Padrao: %USERPROFILE%\Backups\relatorio-horas
    [string]$Dest = (Join-Path $env:USERPROFILE 'Backups\relatorio-horas'),
    # Dias de retencao dos dumps .sql.gz (artefatos nao entram na retencao)
    [int]$RetentionDays = 30,
    # Nome do container; vazio = detecta pelo label do docker compose
    [string]$ContainerName = '',
    [string]$DbName = 'reports_db',
    [switch]$SkipArtifacts
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
    # Roda um script sh dentro do container. O script viaja como ARQUIVO
    # (docker cp), nao como argumento de linha de comando: evita o inferno
    # de aspas do PowerShell 5.1 no Windows e mantem a senha resolvida so
    # no ambiente do container.
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

if ($DbName -notmatch '^[A-Za-z0-9_]+$') { throw "Nome de banco invalido: $DbName" }

New-Item -ItemType Directory -Path $Dest -Force | Out-Null
$stamp = Get-Date -Format 'yyyy-MM-dd_HHmmss'
$container = Resolve-Container
$insideDump = "/tmp/reports_db_backup_$stamp.sql"
$outFile = Join-Path $Dest "reports_db_$stamp.sql.gz"
$logFile = Join-Path $Dest 'backup.log'

function Write-Log([string]$msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Write-Host $line
    Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}

Write-Log "Inicio do backup de '$DbName' (container '$container')"

# set -e: qualquer comando que falhe aborta o script. O dump vai para
# arquivo e so depois e comprimido, de proposito: num pipeline o exit code
# do mysqldump poderia ser mascarado pelo do gzip.
$script = @'
set -e
MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --routines --triggers {0} > {1}
gzip -f {1}
gzip -t {1}.gz
'@ -f $DbName, $insideDump
$script = $script -replace "`r`n", "`n"

Invoke-InContainer -Container $container -ScriptText $script

docker cp "${container}:$insideDump.gz" $outFile | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Falha ao copiar o dump do container (docker cp).' }
docker exec $container rm -f "$insideDump.gz" 2>$null | Out-Null

$size = (Get-Item -LiteralPath $outFile).Length
if ($size -le 0) { throw "Arquivo de backup vazio: $outFile" }
Write-Log ("OK dump: {0} ({1:N1} MB)" -f $outFile, ($size / 1MB))

if (-not $SkipArtifacts) {
    $artifactsSrc = Join-Path $root 'backend\data\report_artifacts'
    $artifactsDst = Join-Path $Dest 'artifacts'
    if (Test-Path -LiteralPath $artifactsSrc) {
        Write-Log "Copiando artefatos para $artifactsDst (incremental, sem apagar)"
        robocopy $artifactsSrc $artifactsDst /E /R:2 /W:5 /NFL /NDL /NJH /NJS /NP | Out-Null
        # robocopy usa 0-7 como sucesso (1 = copiou, 2 = extras, 3 = ambos);
        # a partir de 8 e erro de verdade.
        if ($LASTEXITCODE -ge 8) { throw "robocopy falhou (exit $LASTEXITCODE)." }
        Write-Log 'OK artefatos copiados'
    } else {
        Write-Log "AVISO: pasta de artefatos nao existe ainda: $artifactsSrc"
    }
}

if ($RetentionDays -gt 0) {
    $limite = (Get-Date).AddDays(-$RetentionDays)
    $antigos = @(Get-ChildItem -LiteralPath $Dest -Filter 'reports_db_*.sql.gz' -File | Where-Object { $_.LastWriteTime -lt $limite })
    foreach ($f in $antigos) {
        Remove-Item -LiteralPath $f.FullName -Force
        Write-Log "Retencao: removido $($f.Name) (mais antigo que $RetentionDays dias)"
    }
}

Write-Log "Backup concluido. Destino: $Dest"
Write-Host ''
Write-Host 'Backup concluido com sucesso.' -ForegroundColor Green
Write-Host "Destino: $Dest"
