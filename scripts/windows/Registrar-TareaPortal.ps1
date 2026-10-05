[CmdletBinding()]
param([string]$Nombre = 'SistemaJudicialPortal')

$ErrorActionPreference = 'Stop'
$identidad = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identidad)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Acceso denegado: abra PowerShell como administrador con ayuda de TI y vuelva a ejecutar este script.'
}
$app = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$runner = Join-Path $PSScriptRoot 'Iniciar-ServicioPortal.ps1'
$almacen = Join-Path (Split-Path -Parent $app) 'private\credenciales.json'
if (-not (Test-Path -LiteralPath $almacen)) {
    throw 'Configure primero las credenciales con la cuenta que ejecutara el servicio.'
}
$cuenta = (Get-Content -LiteralPath $almacen -Raw | ConvertFrom-Json).cuenta
$seguroWindows = Read-Host -Prompt "Contrasena de Windows de $cuenta (no PIN)" -AsSecureString
if ($seguroWindows.Length -eq 0) { throw 'No se recibio la contrasena de Windows.' }
$accion = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $runner) -WorkingDirectory $app
$disparador = New-ScheduledTaskTrigger -AtStartup
$ajustes = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([timespan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$puntero = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguroWindows)
try {
    $claveWindows = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($puntero)
    Register-ScheduledTask -TaskName $Nombre -Action $accion -Trigger $disparador `
        -Settings $ajustes -User $cuenta -Password $claveWindows -RunLevel Limited `
        -Description 'Motor de lotes del Portal de Gestion Judicial' -Force | Out-Null
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($puntero)
    $seguroWindows.Dispose()
    $claveWindows = $null
}
Write-Host "Tarea registrada: $Nombre"
Write-Host 'TI debe confirmar que esta maquina no se suspende y que la cuenta puede iniciar tareas por lotes.'
