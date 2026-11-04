# Proyecto: Clicker por cámara

Votación en vivo para el aula: los alumnos levantan tarjetas ArUco con una opción
(A/B/C/D) y un módulo local con webcam detecta y envía los votos por Socket.IO.
El profesor controla la sesión desde un dashboard web y ve los resultados en vivo.

## Stack

- **Backend:** FastAPI + `python-socketio` 5.x + SQLAlchemy 2.x async + `asyncpg` +
  `redis.asyncio`. Python 3.11+.
- **Frontend:** HTML + JS plano + Chart.js 4.x + socket.io-client 4.x servidos desde
  `frontend/vendor/`. Sin frameworks ni build.
- **Módulo local:** OpenCV (`cv2.aruco`) + `python-socketio` client. Python nativo de
  Windows (no WSL).
- **Bases de datos:** PostgreSQL (permanente, fuente de verdad) y Redis (votos en vivo,
  caché).

## Estructura

```
.
├── AGENTS.md
├── README.md
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── app/ (main.py, config.py, db.py, redis_client.py, models.py, schemas.py, routes.py, sockets.py, auth.py, services.py)
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── vendor/ (socket.io-client 4.x, chart.js 4.x)
└── local-module/
    ├── generate_cards.py
    ├── detector.py
    ├── client.py
    ├── main.py
    ├── test_assets/
    └── requirements.txt
```

## Reglas

- Nunca hardcodear secretos; usar variables de entorno validadas con `pydantic-settings`.
- Nunca bloquear el event loop: SQLAlchemy async y `redis.asyncio` dentro de handlers de socket.
- Un archivo por responsabilidad.
- Al persistir votos usar `INSERT ... ON CONFLICT (session_id, student_id) DO UPDATE`.
- Tests con `pytest` para cada endpoint y para la detección; BD `clicker_test` y Redis db 1 aislados.
- Comentarios en español. Después de cada tarea correr los tests y mostrar el resultado.
- El módulo local de cámara se ejecuta con Python nativo de Windows, nunca en WSL.
- `frontend/vendor/` es local: no usar CDN en producción (puede no haber internet en el aula).
- No incrustar `API_KEY` en el HTML; el dashboard usa cookie de sesión firmada con `SECRET_KEY`.

## Contrato de eventos Socket.IO

| Evento | Dirección | Payload |
|---|---|---|
| `connect` con `auth: {role, api_key}` (local) o cookie de sesión (dashboard) | cliente → servidor | rechazar con `ConnectionRefusedError` si no autorizado |
| `state:sync` | servidor → cliente al conectar | `{session_id o null, status, question?, roster?, counts?}` |
| `vote:open` | servidor → local y dashboard | `{session_id, question, options, roster}` |
| `vote:cast` | local → servidor | `{session_id, aruco_id, option}` |
| `vote:rejected` | servidor → local | `{aruco_id, reason: "unknown"\|"closed"\|"invalid"\|"stale_session"}` |
| `tally:update` | servidor → dashboard | `{session_id, counts:{A,B,C,D}, total, voted:[aruco_id], missing:[aruco_id]}` |
| `vote:close` | servidor → todos | `{session_id}` |
| `results:final` | servidor → dashboard y local | `{session_id, counts, correct_option, per_student:[{student_id,name,option,correct}]}` |

### Reglas de `vote:cast` (en este orden)

1. Rechazar si `session_id != active_session` → `vote:rejected/stale_session`.
2. Rechazar si no hay sesión abierta → `vote:rejected/closed`.
3. Rechazar si `aruco_id` no está en `session:{id}:roster` → `vote:rejected/unknown`.
4. Rechazar si `option` no es A–D → `vote:rejected/invalid`.
5. Si es válido: `HSET` en `session:{id}:votes`, recalcular counts con `HGETALL`
   (≤50 alumnos) y emitir `tally:update` con `voted` y `missing`.

## Esquema PostgreSQL

| Tabla | Campos |
|---|---|
| `students` | id, name, aruco_id (único), created_at |
| `questions` | id, text, option_a, option_b, option_c, option_d, correct_option, created_at |
| `voting_sessions` | id, question_id → questions, status (open/closed), opened_at, closed_at |
| `votes` | id, session_id, student_id, option, created_at, único (session_id, student_id) |

Restricciones obligatorias:

- `votes.option` con `CHECK (option IN ('A','B','C','D'))`.
- `questions.correct_option` con el mismo `CHECK`.
- `voting_sessions.status` con `CHECK (status IN ('open','closed'))` e índice en `status`.
- Timestamps con zona horaria (`TIMESTAMPTZ`) y `created_at` por defecto `now()`.
- `votes` se escribe con `ON CONFLICT (session_id, student_id) DO UPDATE`.

## Claves Redis

```
active_session                    → id de la sesión abierta (caché; la verdad es Postgres)
session:{id}:votes                → hash {aruco_id: "A|B|C|D"}
session:{id}:roster               → set de aruco_id registrados
session:{id}:counts               → hash {A,B,C,D} derivado (opcional)
session:{id}:stability:{aruco_id} → opcional, para filtrar lecturas inestables
```

Reglas de consistencia:

- Al cerrar: mapear `aruco_id → student_id` con la tabla `students`, persistir en **una
  transacción** y borrar las claves Redis **después del commit**.
- Cierre **idempotente**: si la sesión ya está `closed`, devolver los resultados
  existentes sin reescribir.
- Al arrancar el backend: si `active_session` apunta a una sesión cerrada en Postgres,
  borrar la clave.

## Comandos

```powershell
# Bases de datos locales
docker compose up -d

# Backend (desde backend/)
uvicorn app.main:app --reload --port 8000

# Tests (desde backend/)
pytest

# Módulo local (desde local-module/)
python main.py --show
```

## Versiones fijadas

- `python-socketio` 5.x (servidor) y `socket.io-client` 4.x (cliente).
- `opencv-contrib-python` 4.10.x (no instalar `opencv-python` en paralelo).
- `socket.io-client` 4.8.1 y `chart.js` 4.4.9 en `frontend/vendor/`.
