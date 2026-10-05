[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$app = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$configPath = Join-Path $app 'config_supabase.json'
if (-not (Test-Path -LiteralPath $configPath)) {
    throw 'Falta config_supabase.json. Configure primero la conexion a Supabase.'
}

$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$usuario = [string]$config.base_de_datos.usuario
if ($usuario -match '^postgres\.([a-z0-9]+)$') {
    $url = "https://$($Matches[1]).supabase.co"
} else {
    $url = Read-Host 'URL del proyecto Supabase (https://...supabase.co)'
}
$uri = $null
if (-not [Uri]::TryCreate($url, [UriKind]::Absolute, [ref]$uri) -or $uri.Scheme -ne 'https') {
    throw 'La URL de Supabase debe usar HTTPS.'
}

$campos = [ordered]@{
    POSTGRES_PASSWORD = 'Contrasena de PostgreSQL de Supabase'
    SUPABASE_SECRET_KEY = 'Secret API key (sb_secret_) o service_role JWT de Supabase'
    AUTOCAPTCHA_API_KEY = 'Clave de 2Captcha'
    NVIDIA_API_KEY = 'Clave de NVIDIA NIM'
}
$cifrados = [ordered]@{}
foreach ($nombre in $campos.Keys) {
    $seguro = Read-Host -Prompt $campos[$nombre] -AsSecureString
    if ($seguro.Length -eq 0) { throw "Falta $nombre." }
    $cifrados[$nombre] = ConvertFrom-SecureString -SecureString $seguro
    $seguro.Dispose()
}

$privado = Join-Path $env:LOCALAPPDATA 'SistemaJudicial\servidor\private'
New-Item -ItemType Directory -Path $privado -Force | Out-Null
$destino = Join-Path $privado 'credenciales.json'
$temporal = Join-Path $privado ('.credenciales-' + [guid]::NewGuid().ToString('N') + '.tmp')
try {
    [pscustomobject]@{
        version = 1
        cuenta = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        supabase_url = $url
        secretos = $cifrados
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $temporal -Encoding UTF8
    Move-Item -LiteralPath $temporal -Destination $destino -Force
} finally {
    if (Test-Path -LiteralPath $temporal) { Remove-Item -LiteralPath $temporal -Force }
}
Write-Host "Credenciales cifradas para la cuenta actual: $destino"
Write-Host 'No se ha guardado ninguna clave en Git.'
