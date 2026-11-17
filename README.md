# Clicker por cámara

Votación en vivo en el aula mediante tarjetas ArUco y una webcam. Los alumnos giran
su tarjeta para elegir A, B, C o D; un módulo local detecta la opción y la envía por
Socket.IO al backend. El profesor abre y cierra la votación desde un dashboard y ve
los resultados en tiempo real.

## Arquitectura

```
[Webcam + tarjetas ArUco]            [Teléfono: cámara + escáner QR]
        │                                      │
        ▼                                      ▼
[local-module] ──Socket.IO──▶ [FastAPI + python-socketio] ──▶ [PostgreSQL]
                                     │  │                    [Redis]
                                     │  └──Socket.IO──▶ [Dashboard del profesor]
                                     └─────Socket.IO──▶ [Panel del estudiante]
```

- **PostgreSQL:** fuente de verdad (estudiantes, preguntas, sesiones, votos).
- **Redis:** estado vivo de la votación (roster, votos, sesión activa).
- **Socket.IO:** canal en tiempo real entre módulo local, escáner, servidor, dashboard
  y panel del estudiante (este último recibe el estado en vivo sin datos de otros alumnos).

## Requisitos

- Python 3.11+
- Node.js 20+ (solo para descargar/actualizar los vendor)
- Git
- Docker Desktop (Postgres y Redis locales)
- Webcam y tarjetas ArUco impresas (módulo local)
- Opcional: `mkcert` para HTTPS local y usar la cámara del teléfono

> En Windows, ejecuta el módulo local con Python nativo. No uses WSL para la cámara.

## Estructura del repositorio

```
backend/        FastAPI + Socket.IO + SQLAlchemy async
frontend/       Dashboard + panel del estudiante + escáner QR (HTML/JS plano)
local-module/   Detección ArUco + cliente Socket.IO
scripts/        Utilidades de desarrollo (HTTPS local con mkcert)
```

## Instalación local

```powershell
# 1. Variables de entorno
Copy-Item .env.example .env
# Edita .env y cambia API_KEY, SECRET_KEY y DASHBOARD_PASSWORD

# 2. Bases de datos
docker compose up -d

# 2b. Base de datos aislada para tests (una sola vez)
docker exec clicker-postgres psql -U clicker -d clicker -c "CREATE DATABASE clicker_test;"

# 3. Backend
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.db
uvicorn app.main:app --reload --port 8000

# 4. Dashboard
# Abre http://localhost:8000

# 5. Módulo local (otra terminal, Python de Windows)
cd local-module
pip install -r requirements.txt
python main.py --show
```

## Probar sin cámara

Con el backend levantado, un script siembra estudiantes, crea una pregunta y simula
votos por Socket.IO:

```powershell
cd backend
.\venv\Scripts\Activate.ps1
python scripts/smoke_test.py --keep-open --delay 1.5
```

Abre `http://localhost:8000`, inicia sesión con `DASHBOARD_PASSWORD` y verás la
sesión abierta y el gráfico moviéndose (con `--delay 1.5` los votos llegan uno a
uno). Sin `--keep-open`, el script cierra la votación y muestra los resultados
finales.

## Variables de entorno

| Variable | Descripción |
|---|---|
| `DATABASE_URL` | URL async de PostgreSQL (`postgresql+asyncpg://...`) |
| `REDIS_URL` | URL de Redis (`redis://...` o `rediss://...` en producción) |
| `API_KEY` | Clave del módulo local de cámara |
| `SECRET_KEY` | Clave para firmar la cookie de sesión del dashboard |
| `DASHBOARD_PASSWORD` | Contraseña del dashboard del profesor |
| `PORT` | Puerto del servidor (8000 en local) |
| `ARUCO_DICT` | `DICT_4X4_50` (por defecto) o `DICT_5X5_100` (>30 alumnos o >3 m) |

## Escanear QR con la cámara del teléfono

La cámara del navegador solo funciona en **contexto seguro** (`https://` o
`localhost`). Para abrir el panel desde un teléfono en la misma red del aula:

```powershell
# 1. Instala mkcert una sola vez
winget install FiloSottile.mkcert
mkcert -install

# 2. Arranca el backend con HTTPS para la IP local
powershell -ExecutionPolicy Bypass -File scripts/https-local.ps1
```

El script muestra la URL `https://<IP-del-PC>:8000`. Instala la CA raíz de mkcert
en el teléfono (Android: *Certificado de CA*; iOS: perfil + *confianza total*) y
abre esa URL. En el dashboard aparece la tarjeta **Escanear QR con este dispositivo**:
inicia la cámara, muestra cada QR quieto medio segundo y el voto se envía por el
socket del dashboard. No requiere Internet, solo la red local.

Si cambia la IP del PC, el script regenera el certificado automáticamente; vuelve a
instalar la CA solo si cambió el equipo o el almacén de certificados.

## Vendor (sin CDN)

- `frontend/vendor/socket.io.min.js` — socket.io-client **4.8.1**
- `frontend/vendor/chart.umd.min.js` — Chart.js **4.4.9**
- `frontend/vendor/qrcode.min.js` — qrcodejs **1.0.0** (QR del estudiante, sin CDN)
- `frontend/vendor/jsQR.js` — jsQR **1.4.0** (respaldo del escáner en Safari/iOS)

## Despliegue

Pendiente (Fase 7): Render + Neon + Upstash.

## Licencia

Proyecto académico.
