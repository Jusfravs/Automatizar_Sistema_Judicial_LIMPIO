[CmdletBinding()]
param([string]$RutaAlmacen)

$ErrorActionPreference = 'Stop'

if (-not $RutaAlmacen) {
    $RutaAlmacen = Join-Path $env:LOCALAPPDATA 'SistemaJudicial\servidor\private\credenciales.json'
}
if (-not (Test-Path -LiteralPath $RutaAlmacen -PathType Leaf)) {
    throw 'No se encontro el almacen cifrado del portal. Configure primero las credenciales.'
}

$almacen = Get-Content -LiteralPath $RutaAlmacen -Raw | ConvertFrom-Json
$cuentaActual = [Security.Principal.WindowsIdentity]::GetCurrent().Name
if ($almacen.version -ne 1 -or $almacen.cuenta -ne $cuentaActual) {
    throw 'El almacen pertenece a otra cuenta de Windows o tiene una version desconocida. Ejecute este script con su cuenta habitual, sin elevar a Administrador.'
}
if (-not $almacen.secretos -or -not $almacen.secretos.PSObject.Properties['NVIDIA_API_KEY']) {
    throw 'El almacen no contiene la entrada NVIDIA_API_KEY.'
}

$python = (Get-Command python -ErrorAction Stop).Source
$verificador = Join-Path (Split-Path -Parent $PSScriptRoot) 'verificar_clave_nvidia.py'
$claveSegura = Read-Host -Prompt 'Nueva clave NVIDIA NIM (nvapi-)' -AsSecureString
if ($claveSegura.Length -eq 0) {
    $claveSegura.Dispose()
    throw 'No se recibio ninguna clave.'
}

$puntero = [IntPtr]::Zero
$claveTexto = $null
$claveAnteriorEntorno = [Environment]::GetEnvironmentVariable('NVIDIA_API_KEY', 'Process')
$temporal = $null
try {
    $puntero = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($claveSegura)
    $claveTexto = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($puntero)
    if ($claveTexto -ne $claveTexto.Trim()) {
        throw 'La clave contiene espacios al principio o al final. Se conserva la clave anterior.'
    }
    if (-not $claveTexto.StartsWith('nvapi-', [StringComparison]::Ordinal) -or $claveTexto.Length -lt 20) {
        throw 'Formato de clave NVIDIA no valido. Se conserva la clave anterior.'
    }

    [Environment]::SetEnvironmentVariable('NVIDIA_API_KEY', $claveTexto, 'Process')
    & $python $verificador
    if ($LASTEXITCODE -ne 0) {
        throw 'No se pudo validar la nueva clave con NVIDIA. Se conserva la clave anterior.'
    }

    $almacen.secretos.NVIDIA_API_KEY = ConvertFrom-SecureString -SecureString $claveSegura
    $carpeta = Split-Path -Parent $RutaAlmacen
    $temporal = Join-Path $carpeta (([guid]::NewGuid().ToString('N')) + '.tmp')
    $almacen | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $temporal -Encoding UTF8
    Move-Item -LiteralPath $temporal -Destination $RutaAlmacen -Force
    $temporal = $null

    Write-Host 'Clave NVIDIA validada y guardada cifrada para la cuenta actual.'
    Write-Host 'El motor del portal debe reiniciarse cuando no haya lotes activos para cargarla.'
} finally {
    [Environment]::SetEnvironmentVariable('NVIDIA_API_KEY', $claveAnteriorEntorno, 'Process')
    if ($puntero -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($puntero)
    }
    $claveSegura.Dispose()
    $claveTexto = $null
    if ($temporal -and (Test-Path -LiteralPath $temporal)) {
        Remove-Item -LiteralPath $temporal -Force
    }
}
