# =====================================================================
# Sync PRD DB: Zotto (Production -> Local)
# =====================================================================
#
# FIX MOJIBAKE: O PowerShell usa Windows-1252 por padrão no pipe entre processos.
# As três linhas abaixo forçam UTF-8 em ambas as direções do pipe antes de qualquer
# operação, impedindo que acentos e cedilhas sejam corrompidos no trânsito.
$OutputEncoding              = [System.Text.UTF8Encoding]::new($false)  # PowerShell → pipe (escrita)
[Console]::OutputEncoding   = [System.Text.UTF8Encoding]::new($false)  # pipe → PowerShell (leitura)
[Console]::InputEncoding    = [System.Text.UTF8Encoding]::new($false)  # stdin do processo receptor

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Iniciando Sincronizacao do Zotto DB" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

Write-Host "[1/3] Lendo credenciais do .env..." -ForegroundColor DarkGray

if (Test-Path ".env") {
    Get-Content ".env" -Encoding UTF8 | Where-Object { $_ -match '^[a-zA-Z_]' } | ForEach-Object {
        $name, $value = $_ -split '=', 2
        $name  = $name.Trim()
        $value = $value.Trim().Trim('"').Trim("'")
        Set-Item -Path "env:$name" -Value $value
    }
} else {
    Write-Host "[ERRO] Arquivo .env nao encontrado na raiz do projeto!" -ForegroundColor Red
    exit 1
}

$RAILWAY_URL      = $env:RAILWAY_DB_URL
$USUARIO_LOCAL    = $env:DB_USER
$BANCO_LOCAL      = $env:DB_NAME
$CONTAINER_LOCAL  = $env:CONTAINER_LOCAL

if ([string]::IsNullOrEmpty($RAILWAY_URL) -or
    [string]::IsNullOrEmpty($USUARIO_LOCAL) -or
    [string]::IsNullOrEmpty($BANCO_LOCAL) -or
    [string]::IsNullOrEmpty($CONTAINER_LOCAL)) {
    Write-Host "[ERRO] Faltam variaveis no .env. Necessarias: RAILWAY_DB_URL, DB_USER, DB_NAME, CONTAINER_LOCAL." -ForegroundColor Red
    exit 1
}

Write-Host "[2/3] Verificando container local '$CONTAINER_LOCAL'..." -ForegroundColor DarkGray

$containerStatus = docker inspect --format='{{.State.Running}}' $CONTAINER_LOCAL 2>$null
if ($containerStatus -ne "true") {
    Write-Host "[ERRO] Container '$CONTAINER_LOCAL' nao esta em execucao. Rode 'docker-compose up -d' primeiro." -ForegroundColor Red
    exit 1
}

Write-Host "[3/3] Baixando e injetando dados (UTF-8)..." -ForegroundColor Yellow

# PGCLIENTENCODING garante que pg_dump e psql dentro dos containers
# negociem UTF-8 com o servidor PostgreSQL, independente da configuracao do SO.
docker run --rm `
    -e PGCLIENTENCODING=UTF8 `
    postgres:18 `
    pg_dump $RAILWAY_URL `
        --clean `
        --if-exists `
        --no-owner `
        --no-privileges `
        --encoding=UTF8 |
docker exec -i `
    -e PGCLIENTENCODING=UTF8 `
    $CONTAINER_LOCAL `
    psql -U $USUARIO_LOCAL -d $BANCO_LOCAL -q

if ($LASTEXITCODE -eq 0) {
    Write-Host "[SUCESSO] Sincronizacao concluida com encoding UTF-8." -ForegroundColor Green
} else {
    Write-Host "[ERRO] Sincronizacao falhou (exit code $LASTEXITCODE)." -ForegroundColor Red
    exit $LASTEXITCODE
}