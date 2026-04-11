# =====================================================================
# Sync PRD DB: Zotto (Production -> Local)
# =====================================================================

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Iniciando Sincronizacao do Zotto DB" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

Write-Host "[1/2] Lendo credenciais do .env..." -ForegroundColor DarkGray

if (Test-Path ".env") {
    Get-Content ".env" | Where-Object { $_ -match '^[a-zA-Z_]' } | ForEach-Object {
        $name, $value = $_ -split '=', 2
        $name = $name.Trim()
        $value = $value.Trim().Trim('"').Trim("'")
        Set-Item -Path "env:$name" -Value $value
    }
} else {
    Write-Host "[ERRO] Arquivo .env nao encontrado na raiz do projeto!" -ForegroundColor Red
    exit
}

$RAILWAY_URL = $env:RAILWAY_DB_URL
$USUARIO_LOCAL = $env:DB_USER
$BANCO_LOCAL = $env:DB_NAME
$CONTAINER_LOCAL = $env:CONTAINER_LOCAL

if ([string]::IsNullOrEmpty($RAILWAY_URL) -or [string]::IsNullOrEmpty($USUARIO_LOCAL)) {
    Write-Host "[ERRO] Faltam variaveis no .env (RAILWAY_DB_URL, DB_USER ou DB_NAME)." -ForegroundColor Red
    exit
}

Write-Host "[2/2] Baixando e injetando dados na memoria..." -ForegroundColor Yellow

docker run --rm postgres:18 pg_dump $RAILWAY_URL --clean --if-exists --no-owner --no-privileges | docker exec -i $CONTAINER_LOCAL psql -U $USUARIO_LOCAL -d $BANCO_LOCAL -q

Write-Host "[SUCESSO] Sincronizacao concluida!" -ForegroundColor Green