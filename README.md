# Clicker por cámara

Votación en vivo en el aula mediante tarjetas ArUco y una webcam. Los alumnos giran
su tarjeta para elegir A, B, C o D; un módulo local detecta la opción y la envía por
Socket.IO al backend. El profesor abre y cierra la votación desde un dashboard y ve
los resultados en tiempo real.

## Arquitectura

```
[Webcam + tarjetas ArUco]
        │
        ▼
[local-module] ──Socket.IO──▶ [FastAPI + python-socketio] ──▶ [PostgreSQL]
                                     │                        [Redis]
                                     └──Socket.IO──▶ [Dashboard del profesor]
```

- **PostgreSQL:** fuente de verdad (estudiantes, preguntas, sesiones, votos).
- **Redis:** estado vivo de la votación (roster, votos, sesión activa).
- **Socket.IO:** canal en tiempo real entre módulo local, servidor y dashboard.

## Requisitos

- Python 3.11+
- Node.js 20+ (solo para descargar/actualizar los vendor)
- Git
- Docker Desktop (Postgres y Redis locales)
- Webcam y tarjetas ArUco impresas (módulo local)

> En Windows, ejecuta el módulo local con Python nativo. No uses WSL para la cámara.

## Estructura del repositorio

```
backend/        FastAPI + Socket.IO + SQLAlchemy async
frontend/       Dashboard del profesor (HTML/JS plano)
local-module/   Detección ArUco + cliente Socket.IO
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

## Vendor (sin CDN)

- `frontend/vendor/socket.io.min.js` — socket.io-client **4.8.1**
- `frontend/vendor/chart.umd.min.js` — Chart.js **4.4.9**

## Despliegue

Pendiente (Fase 7): Render + Neon + Upstash.

## Licencia

Proyecto académico.
