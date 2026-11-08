param([ValidateSet('start', 'stop', 'status')][string]$Action = 'start')

$ErrorActionPreference = 'Stop'
$localRoot = Join-Path $env:LOCALAPPDATA 'NCI\PostgreSQL17'
$pgCtl = Join-Path $localRoot 'pgsql\bin\pg_ctl.exe'
$dataDir = Join-Path $localRoot 'data'
if (-not (Test-Path -LiteralPath $pgCtl)) {
    throw "PostgreSQL local não encontrado em $localRoot. Consulte README.md."
}
switch ($Action) {
    'start' {
        & $pgCtl -D $dataDir status *> $null
        if ($LASTEXITCODE -ne 0) {
            & $pgCtl -D $dataDir -l (Join-Path $localRoot 'postgres.log') -w start
        }
    }
    'stop' { & $pgCtl -D $dataDir -m fast -w stop }
    'status' { & $pgCtl -D $dataDir status }
}
if ($LASTEXITCODE -ne 0) { throw "Falha na operação PostgreSQL: $Action" }
