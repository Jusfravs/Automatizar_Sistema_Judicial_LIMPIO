[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$app = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $app '.venv\Scripts\python.exe'
$configPath = Join-Path $app 'config_supabase.json'
$runtime = Join-Path $env:LOCALAPPDATA 'SistemaJudicial\servidor'
$logs = Join-Path $runtime 'logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
if (-not (Test-Path -LiteralPath $python)) { throw 'Falta el entorno Python .venv.' }
if (-not (Test-Path -LiteralPath $configPath)) { throw 'Falta config_supabase.json.' }

. (Join-Path $PSScriptRoot 'Cargar-EntornoPortal.ps1')
Importar-EntornoPortal
$env:SISTEMA_JUDICIAL_SERVICE_MODE = '1'
$env:SISTEMA_JUDICIAL_LOG_FILE = Join-Path $logs 'motor.log'
$env:PYTHONUNBUFFERED = '1'

# El bloqueo impide que otro arranque cierre como FALLIDA una solicitud en curso.
$bloqueo = Join-Path $runtime 'servicio.lock'
try {
    $candado = [IO.File]::Open($bloqueo, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
} catch [IO.IOException] {
    throw 'Ya existe un motor del portal activo en esta maquina.'
}

function Escribir-Estado([string]$mensaje) {
    $ruta = Join-Path $logs 'arranque.log'
    if ((Test-Path -LiteralPath $ruta) -and (Get-Item -LiteralPath $ruta).Length -gt 5MB) {
        Move-Item -LiteralPath $ruta -Destination (Join-Path $logs 'arranque.anterior.log') -Force
    }
    $linea = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $mensaje
    Add-Content -LiteralPath $ruta -Value $linea -Encoding UTF8
}

try {
    $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    $hostDb = [string]$config.base_de_datos.host
    $puertoDb = [int]$config.base_de_datos.puerto
    Set-Location -LiteralPath $app
    while ($true) {
        $cliente = New-Object Net.Sockets.TcpClient
        try {
            $conexion = $cliente.BeginConnect($hostDb, $puertoDb, $null, $null)
            $listo = $conexion.AsyncWaitHandle.WaitOne(5000)
            if ($listo) { $cliente.EndConnect($conexion) }
        } catch {
            $listo = $false
        } finally {
            $cliente.Close()
        }
        if (-not $listo) {
            Escribir-Estado 'Esperando conexion a PostgreSQL.'
            Start-Sleep -Seconds 30
            continue
        }
        Escribir-Estado 'Iniciando motor del portal.'
        $errorLog = Join-Path $logs 'errores-arranque.log'
        if ((Test-Path -LiteralPath $errorLog) -and (Get-Item -LiteralPath $errorLog).Length -gt 5MB) {
            Move-Item -LiteralPath $errorLog -Destination (Join-Path $logs 'errores-arranque.anterior.log') -Force
        }
        $preferenciaAnterior = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            & $python -u (Join-Path $app 'consola.py') servicio --config $configPath 2>&1 |
                ForEach-Object { Add-Content -LiteralPath $errorLog -Value $_ -Encoding UTF8 }
        } finally {
            $ErrorActionPreference = $preferenciaAnterior
        }
        $codigo = $LASTEXITCODE
        Escribir-Estado "Motor detenido (codigo $codigo). Reintento en 30 segundos."
        Start-Sleep -Seconds 30
    }
} finally {
    $candado.Dispose()
}
