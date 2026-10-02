# Mantiene el servidor de ClaseAIdia encendido sin que nadie lo atienda:
#  - lo vuelve a levantar si se cae (con espera creciente si se cae enseguida, para no girar en vacio),
#  - le pide a Windows que no suspenda el equipo mientras este script viva,
#  - guarda lo que escribe el servidor en logs\ y lo rota para que no llene el disco.
# Lo lanza instalar.ps1 al iniciar sesion; para probarlo a mano: scripts\windows\iniciar_servidor.bat
$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $raiz

$py = Join-Path $raiz 'transcriptor-env\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = (Get-Command python -ErrorAction Stop).Source }
New-Item -ItemType Directory -Force logs | Out-Null

# ES_CONTINUOUS | ES_SYSTEM_REQUIRED: el equipo no entra en suspension mientras este proceso siga vivo.
Add-Type -Namespace Win -Name Energia -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint f);'
try { [void][Win.Energia]::SetThreadExecutionState([uint32]2147483649) } catch { Add-Content 'logs\supervisor.log' "[$(Get-Date -Format s)] no se pudo evitar la suspension: $_" }

$maxBytes = 10MB
$copias = 5
function Rotar($ruta) {
    if (-not (Test-Path $ruta) -or (Get-Item $ruta).Length -le $maxBytes) { return }
    for ($i = $copias; $i -ge 1; $i--) {
        $de = if ($i -eq 1) { $ruta } else { "$ruta.$($i - 1)" }
        if (Test-Path $de) { Move-Item -Force $de "$ruta.$i" }
    }
}

# https si hay certificado propio (la grabacion desde el celular lo exige); si no, http en el 8000.
if ((Test-Path 'certs\cert.pem') -and (Test-Path 'certs\key.pem')) {
    $argumentos = @('-m', 'uvicorn', 'api:app', '--host', '0.0.0.0', '--port', '8443', '--ssl-keyfile', 'certs/key.pem', '--ssl-certfile', 'certs/cert.pem', '--no-access-log')
} else {
    $argumentos = @('-m', 'uvicorn', 'api:app', '--host', '0.0.0.0', '--port', '8000', '--no-access-log')
}

$espera = 5
while ($true) {
    Rotar 'logs\servidor.log'
    Rotar 'logs\servidor-errores.log'
    $inicio = Get-Date
    Add-Content 'logs\supervisor.log' "[$(Get-Date -Format s)] iniciando el servidor"
    $p = Start-Process $py -ArgumentList $argumentos -WorkingDirectory $raiz -WindowStyle Hidden -Wait -PassThru `
        -RedirectStandardOutput 'logs\servidor.log' -RedirectStandardError 'logs\servidor-errores.log'
    $segundos = [int]((Get-Date) - $inicio).TotalSeconds
    Add-Content 'logs\supervisor.log' "[$(Get-Date -Format s)] el servidor termino (codigo $($p.ExitCode)) tras $segundos s; se reinicia en $espera s"
    Rotar 'logs\supervisor.log'
    Start-Sleep -Seconds $espera
    $espera = if ($segundos -lt 60) { [Math]::Min($espera * 2, 300) } else { 5 }
}
