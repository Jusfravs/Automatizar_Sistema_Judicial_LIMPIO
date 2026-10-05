function Importar-EntornoPortal {
    $ruta = Join-Path $env:LOCALAPPDATA 'SistemaJudicial\servidor\private\credenciales.json'
    if (-not (Test-Path -LiteralPath $ruta)) {
        throw 'Falta el almacen local. Ejecute Configurar-CredencialesPortal.ps1 con la cuenta del servicio.'
    }
    $datos = Get-Content -LiteralPath $ruta -Raw | ConvertFrom-Json
    $actual = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    if ($datos.version -ne 1 -or $datos.cuenta -ne $actual) {
        throw 'El almacen pertenece a otra cuenta de Windows o tiene una version desconocida.'
    }
    [Environment]::SetEnvironmentVariable('SUPABASE_URL', [string]$datos.supabase_url, 'Process')
    foreach ($propiedad in $datos.secretos.PSObject.Properties) {
        $seguro = ConvertTo-SecureString -String ([string]$propiedad.Value)
        $puntero = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro)
        try {
            $valor = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($puntero)
            [Environment]::SetEnvironmentVariable($propiedad.Name, $valor, 'Process')
        } finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($puntero)
            $seguro.Dispose()
        }
    }
}
