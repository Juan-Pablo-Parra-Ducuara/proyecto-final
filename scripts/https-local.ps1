# ============================================================
# HTTPS local para el escáner QR del navegador.
#
# La cámara del teléfono solo funciona en contexto seguro. Este script:
#   1. Detecta la IP del PC en la red local.
#   2. Genera un certificado con mkcert para esa IP y localhost.
#   3. Arranca uvicorn con HTTPS.
#
# Requisitos:
#   winget install FiloSottile.mkcert
#   mkcert -install
#
# Uso (desde la raíz del proyecto):
#   powershell -ExecutionPolicy Bypass -File scripts/https-local.ps1
# ============================================================

param(
    [int]$Port = 8000,
    [string]$BindHost = "0.0.0.0"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$certsDir = Join-Path $repoRoot "certs"

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

# 1. Comprobar mkcert.
Write-Step "Comprobando mkcert"

$mkcert = Get-Command mkcert -ErrorAction SilentlyContinue

if (-not $mkcert) {
    Write-Host "mkcert no está instalado." -ForegroundColor Yellow
    Write-Host "Instálalo con: winget install FiloSottile.mkcert"
    Write-Host "Después ejecuta una vez: mkcert -install"
    exit 1
}

# 2. Detectar la IP de la red local (la primera IPv4 privada).
Write-Step "Detectando la IP del equipo en la red local"

$ip = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object {
        $_.IPAddress -notlike "127.*" -and
        $_.IPAddress -notlike "169.254.*" -and
        $_.PrefixOrigin -ne "WellKnown" -and
        $_.InterfaceAlias -notmatch "vEthernet|WSL|Docker|Loopback|Virtual"
    } |
    Sort-Object -Property InterfaceIndex |
    Select-Object -First 1 -ExpandProperty IPAddress

if (-not $ip) {
    Write-Host "No se encontró una IP local. Conéctate a la red del aula." -ForegroundColor Yellow
    exit 1
}

Write-Host "IP detectada: $ip"

# 3. Generar el certificado si no existe.
New-Item -ItemType Directory -Force -Path $certsDir | Out-Null

$keyFile = Join-Path $certsDir "local-key.pem"
$certFile = Join-Path $certsDir "local-cert.pem"
$ipFile = Join-Path $certsDir "last-ip.txt"

$ipAnterior = ""

if (Test-Path $ipFile) {
    $ipAnterior = (Get-Content $ipFile -Raw).Trim()
}

if (
    -not (Test-Path $keyFile) -or
    -not (Test-Path $certFile) -or
    $ipAnterior -ne $ip
) {
    Write-Step "Generando certificado para $ip y localhost"

    & mkcert -key-file $keyFile -cert-file $certFile `
        $ip localhost 127.0.0.1 ::1

    if ($LASTEXITCODE -ne 0) {
        Write-Host "No se pudo generar el certificado." -ForegroundColor Red
        exit 1
    }

    Set-Content -Path $ipFile -Value $ip -Encoding ASCII
} else {
    Write-Host "Reutilizando el certificado existente en certs/" -ForegroundColor DarkGray
}

# La CA raíz de mkcert se instala en el teléfono para que confíe en el sitio.
$caRoot = & mkcert -CAROOT
$caFile = Join-Path $caRoot "rootCA.pem"

Write-Step "Arrancando el servidor con HTTPS"

Write-Host @"
Abre el panel desde el teléfono en:

    https://${ip}:${Port}

Para que el teléfono confíe en el certificado, instala la CA raíz:

  Archivo: $caFile

  Android:
    Ajustes > Seguridad > Cifrado y credenciales > Instalar certificado
    > Certificado de CA > selecciona rootCA.pem

  iOS:
    AirDrop o correo el archivo rootCA.pem al iPhone, instala el perfil en
    Ajustes > General > VPN y administración del dispositivo y luego activa
    la confianza total en Ajustes > General > Información > Ajustes de
    confianza de certificados.

  Windows/PC del docente:
    mkcert -install  (ya deja la CA en el almacén del sistema)

Si cambia la IP del PC, el script genera un certificado nuevo automáticamente.

"@ -ForegroundColor Green

Push-Location $backendDir
try {
    & python -m uvicorn app.main:app `
        --host $BindHost `
        --port $Port `
        --ssl-keyfile $keyFile `
        --ssl-certfile $certFile
} finally {
    Pop-Location
}
