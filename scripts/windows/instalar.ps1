# Deja el servidor de ClaseAIdia arrancando solo cada vez que el usuario inicia sesion en Windows (no pide administrador).
#   .\instalar.ps1            instala (o actualiza) el inicio automatico y arranca el servidor ahora
#   .\instalar.ps1 -Quitar    lo desinstala y detiene el servidor
# Para que tambien vuelva solo despues de un corte de luz, Windows debe iniciar sesion solo (ver README, "Servidor 24/7").
param([switch]$Quitar)
$ErrorActionPreference = 'Stop'
$nombre = 'ClaseAIdia-servidor'

function Procesos-Del-Servidor {
    Get-CimInstance Win32_Process |
        Where-Object { ($_.CommandLine -match 'scripts[\\/]windows[\\/]servidor\.ps1' -or $_.CommandLine -match 'uvicorn api:app') -and $_.ProcessId -ne $PID }
}

function Detener-Servidor {
    try { Stop-ScheduledTask -TaskName $nombre -ErrorAction Stop } catch { }
    # Detener la tarea no cierra al servidor que lanzo: se buscan el supervisor y uvicorn por su linea de comando.
    # Primero el supervisor (si no, levantaria otro uvicorn al ver caer el primero) y luego lo que haya quedado.
    for ($i = 0; $i -lt 3; $i++) {
        $procesos = @(Procesos-Del-Servidor | Sort-Object { $_.Name -ne 'powershell.exe' })
        if ($procesos.Count -eq 0) { break }
        foreach ($p in $procesos) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Seconds 1
    }
}

if ($Quitar) {
    Detener-Servidor
    Unregister-ScheduledTask -TaskName $nombre -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host 'Listo: el servidor ya no arranca solo.'
    exit 0
}

$script = Join-Path $PSScriptRoot 'servidor.ps1'
$accion = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
$disparador = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$config = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
Detener-Servidor
Register-ScheduledTask -TaskName $nombre -Action $accion -Trigger $disparador -Settings $config -Force `
    -Description 'Mantiene encendido el servidor de ClaseAIdia (se reinicia solo si se cae).' | Out-Null

# Con corriente conectada, que el equipo no se suspenda ni hiberne (cambia el plan de energia actual del usuario).
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0

Start-ScheduledTask -TaskName $nombre
Write-Host 'Listo: el servidor arranca solo al iniciar sesion y se levanta si se cae. Ya esta corriendo.'
Write-Host 'Registros en la carpeta logs\ . Para desinstalar: instalar.ps1 -Quitar'
