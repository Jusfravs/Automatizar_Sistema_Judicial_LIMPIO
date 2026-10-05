[CmdletBinding()]
param([string]$Nombre = 'SistemaJudicialPortal')

$ErrorActionPreference = 'Stop'
$app = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$logs = Join-Path $env:LOCALAPPDATA 'SistemaJudicial\servidor\logs'
foreach ($nombreTarea in @($Nombre, 'SistemaJudicialPortalAlEntrar') | Select-Object -Unique) {
    $tarea = Get-ScheduledTask -TaskName $nombreTarea -ErrorAction SilentlyContinue
    if ($null -eq $tarea) {
        Write-Host "Tarea ${nombreTarea}: no registrada"
    } else {
        $info = Get-ScheduledTaskInfo -TaskName $nombreTarea
        Write-Host "Tarea ${nombreTarea}: $($tarea.State)"
        Write-Host "Ultima ejecucion: $($info.LastRunTime)"
        Write-Host "Ultimo codigo de Windows: $($info.LastTaskResult)"
    }
}

. (Join-Path $PSScriptRoot 'Cargar-EntornoPortal.ps1')
$resultado = 1
try {
    Importar-EntornoPortal
    & (Join-Path $app '.venv\Scripts\python.exe') (Join-Path $app 'scripts\verificar_servicio_portal.py') `
        --config (Join-Path $app 'config_supabase.json')
    $resultado = $LASTEXITCODE
} catch {
    Write-Warning 'No se pudo completar la comprobacion: falta configuracion o el almacen no pertenece a esta cuenta.'
}

$motorLog = Join-Path $logs 'motor.log'
if (Test-Path -LiteralPath $motorLog) {
    Write-Host 'Ultimas entradas del motor:'
    Get-Content -LiteralPath $motorLog -Tail 8
}
exit $resultado
