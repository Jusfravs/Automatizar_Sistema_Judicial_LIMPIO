[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ruta = Join-Path $env:LOCALAPPDATA 'SistemaJudicial\servidor\private\credenciales.json'
if (-not (Test-Path -LiteralPath $ruta)) {
    throw 'Falta el almacen de credenciales del portal.'
}
$datos = Get-Content -LiteralPath $ruta -Raw | ConvertFrom-Json
$cuenta = [Security.Principal.WindowsIdentity]::GetCurrent().Name
if ($datos.version -ne 1 -or $datos.cuenta -ne $cuenta) {
    throw 'Ejecute este script con la misma cuenta de Windows que ejecuta el motor.'
}

$endpoint = (Read-Host 'Endpoint S3 de B2 (https://s3.REGION.backblazeb2.com)').Trim().TrimEnd('/')
if ($endpoint -notmatch '^https://') { $endpoint = 'https://' + $endpoint }
if ($endpoint -notmatch '^https://s3\.[a-z0-9-]+\.backblazeb2\.com$') {
    throw 'Endpoint B2 invalido. Copie el campo Endpoint desde B2 Cloud Storage > Buckets.'
}
$bucket = (Read-Host 'Nombre del bucket privado de B2').Trim()
if ($bucket -notmatch '^[a-z0-9][a-z0-9-]{4,48}[a-z0-9]$') {
    throw 'Nombre del bucket invalido.'
}
$keyId = (Read-Host 'Key ID de la Application Key limitada al bucket').Trim()
if (-not $keyId) { throw 'Falta el Key ID.' }
$clave = Read-Host 'Application Key de B2' -AsSecureString
if ($clave.Length -eq 0) {
    $clave.Dispose()
    throw 'Configuracion B2 incompleta o con formato invalido.'
}

$puntero = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($clave)
try {
    $appKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($puntero)
    $env:B2_ENDPOINT = $endpoint
    $env:B2_BUCKET = $bucket
    $env:B2_KEY_ID = $keyId
    $env:B2_APP_KEY = $appKey
    $app = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
    $python = Join-Path $app '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        throw 'Falta el entorno Python del motor. Instale primero las dependencias del proyecto.'
    }
    Push-Location $app
    try {
        & $python -m scripts.verificar_b2
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo verificar B2; las credenciales anteriores siguen intactas.' }
    } finally {
        Pop-Location
    }

    $valores = [ordered]@{
        B2_ENDPOINT = $endpoint
        B2_BUCKET = $bucket
        B2_KEY_ID = $keyId
        B2_APP_KEY = $appKey
    }
    foreach ($nombre in $valores.Keys) {
        $seguro = ConvertTo-SecureString -String $valores[$nombre] -AsPlainText -Force
        $cifrado = ConvertFrom-SecureString -SecureString $seguro
        $seguro.Dispose()
        if ($datos.secretos.PSObject.Properties.Name -contains $nombre) {
            $datos.secretos.$nombre = $cifrado
        } else {
            $datos.secretos | Add-Member -NotePropertyName $nombre -NotePropertyValue $cifrado
        }
    }
    $temporal = Join-Path (Split-Path -Parent $ruta) ([guid]::NewGuid().ToString('N') + '.tmp')
    try {
        $datos | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $temporal -Encoding UTF8
        Move-Item -LiteralPath $temporal -Destination $ruta -Force
    } finally {
        if (Test-Path -LiteralPath $temporal) { Remove-Item -LiteralPath $temporal -Force }
    }
    Write-Host 'B2 verificado; credenciales cifradas para la cuenta actual.'
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($puntero)
    $clave.Dispose()
    $appKey = $null
    $env:B2_APP_KEY = $null
    $env:B2_KEY_ID = $null
}
