# Plan detallado: "Clicker" por cámara con OpenCode + Big Pickle

Plan para construir el proyecto de forma local usando **OpenCode** (agente de código en terminal) con el modelo gratuito **Big Pickle**, y desplegarlo a la nube al final.

> **Aviso de privacidad:** los modelos gratuitos de OpenCode pueden usar tus datos para entrenamiento. **Nunca pegues contraseñas ni el contenido de `.env` en los prompts.**

**Estrategia:** construir y probar todo en tu PC (Fases 0 a 6) y desplegar a la nube al final (Fase 7), porque el proyecto exige nube.

**Supuestos del alcance:** un solo profesor, una sola sesión de votación activa global, ≤50 alumnos y demo desde el portátil del profesor. Si el curso supera 30 alumnos o la cámara está a más de 3 m, se cambia el diccionario ArUco antes de imprimir (ver decisiones técnicas).

---

## Estado de avance

Actualizado: 2026-11-04.

| Fase | Estado | Notas |
|---|---|---|
| 0. Entorno | ✅ Completada | Python 3.14.7, Node 24.19, Git 2.55, Docker 29.9, OpenCode 1.19.3 |
| 1. Repo y reglas | ✅ Completada | Estructura, `AGENTS.md`, `.env.example`, vendor local (socket.io-client 4.8.1, Chart.js 4.4.9) y repo en GitHub |
| 2. BD locales | ✅ Completada | `docker-compose.yml`, Postgres 16 + Redis 7, `clicker_test`, modelos con checks/unique y `/health` con 503 |
| 3. Backend | ✅ Completada | Auth por cookie y `API_KEY`, endpoints REST, cierre idempotente, sockets y 31 tests |
| 4. Dashboard | ✅ Completada | Login, estudiantes, preguntas, abrir/cerrar, Chart.js en vivo, faltantes y resultados finales |
| 5. Cámara | ⏳ Pendiente | Tarjetas ArUco, detector, estabilidad y cliente local |
| 6. Integración | ⏳ Pendiente | Pruebas E2E con webcam y casos borde |
| 7. Despliegue | ⏳ Pendiente | Render + Neon + Upstash |
| 8. Entrega | ⏳ Pendiente | README final, revisión de secretos y tag `v1.0` |

### Cambios respecto al plan original

- Se añadió `backend/app/services.py` para centralizar la lógica de sesiones/votos y evitar imports circulares.
- Se añadió `backend/scripts/smoke_test.py` para probar sin cámara: siembra estudiantes/pregunta y simula votos por Socket.IO.
- `main.py` exporta un `socketio.ASGIApp` que envuelve FastAPI; el dashboard se sirve con `StaticFiles` al final de las rutas.
- Los tests de sockets corren contra uvicorn real con `socketio.AsyncClient` y `aiohttp`.
- El entorno local quedó con Python 3.14.7 (el plan pedía 3.11+; funciona por wheels `cp314`/`abi3`).

---

## Decisiones técnicas cerradas (no renegociar a mitad de proyecto)

- **Stack asíncrono:** FastAPI + `socketio.AsyncServer` + SQLAlchemy 2.x async + `asyncpg` + `redis.asyncio`. **Nunca** llamar clientes síncronos dentro de handlers de socket: bloquearían el event loop.
- **Fuente de verdad:** PostgreSQL. Redis es caché y estado vivo. Si al arrancar hay discrepancia (por ejemplo, `active_session` apunta a una sesión ya cerrada), gana Postgres y se limpia Redis.
- **Autenticación:** el módulo local se autentica con `API_KEY`; el dashboard usa un login con `DASHBOARD_PASSWORD` que emite una cookie de sesión firmada con `SECRET_KEY`. Esa cookie autentica tanto REST como Socket.IO (`withCredentials`). **No se incrusta el `API_KEY` en el HTML.**
- **Versiones de Socket.IO:** servidor `python-socketio` 5.x, cliente `socket.io-client` 4.x (son las compatibles). Ambas versiones fijadas.
- **Frontend sin CDN en producción:** `socket.io-client` 4.x y `chart.js` 4.x descargados en `frontend/vendor/`. En el aula puede no haber internet.
- **Cámara:** Python **nativo de Windows**, `opencv-contrib-python` 4.10.x. No mezclar con `opencv-python` (conflicto de paquetes). El módulo de cámara no va en WSL.
- **Diccionario ArUco:** `DICT_4X4_50` por defecto; si el curso supera 30 alumnos o la distancia es >3 m, cambiar a `DICT_5X5_100` vía variable `ARUCO_DICT` **antes** de imprimir las tarjetas.
- **Tamaño de tarjeta:** marcador de 12×12 cm con 2 cm de margen blanco, impresión mate (sin brillo).
- **Persistencia de votos:** el alumno puede cambiar de tarjeta; al cerrar se usa `INSERT ... ON CONFLICT (session_id, student_id) DO UPDATE` para que Postgres refleje el último voto, igual que Redis.

---

## Fase 0: Preparar el entorno (≈1 h)

**Instala:**
- Python 3.11+, Node 20+, Git 2.40+, VS Code y Docker Desktop (con backend WSL2, para Postgres y Redis locales).
- OpenCode: `npm i -g opencode-ai`. Comprueba con `opencode --version`.
- Una cuenta de GitHub.

> **Windows:** usa OpenCode nativo en Windows (PowerShell o Windows Terminal). **No uses WSL para el módulo de cámara**: el acceso a webcam en WSL2 es inestable. Si prefieres WSL para el agente, mantén una segunda terminal con Python de Windows para `local-module/`.

**Primer arranque de OpenCode:**
1. Abre una terminal en una carpeta vacía `clicker-camara/` y ejecuta `opencode`.
2. Escribe `/models` y elige **Big Pickle** (la lista de `/models` siempre muestra los modelos disponibles).
3. Si no aparece, actualiza con `opencode upgrade`.

**Cómo trabajar con Big Pickle (modelo gratuito, con límites):**
- Una tarea pequeña por prompt, nombrando los archivos exactos.
- Empieza siempre en **modo Plan** (se alterna con `Tab`) para que proponga antes de editar, y pasa a **Build** cuando el plan te convenza.
- Haz `git commit` al terminar cada paso. Si el modelo daña algo, vuelves atrás con `git restore` o con `/undo`.
- Pídele siempre que ejecute los tests o el comando y te muestre la salida.
- Si te limita por uso, cambia de modelo gratuito en `/models` o espera.

---

## Fase 1: Repositorio y reglas del proyecto (≈1 h)

**Estructura objetivo:**

```
PROYECTO-FINAL-ARC/   (repo: proyecto-final)
├── AGENTS.md
├── README.md
├── docker-compose.yml
├── .env.example
├── .gitignore
├── plan-clicker-camara.md
├── backend/
│   ├── app/ (main.py, config.py, db.py, redis_client.py, models.py, schemas.py, routes.py, sockets.py, auth.py, services.py)
│   ├── scripts/ (smoke_test.py)
│   ├── tests/
│   ├── pytest.ini
│   └── requirements.txt
├── frontend/
│   ├── index.html   (dashboard del profesor)
│   ├── app.js
│   ├── style.css
│   └── vendor/ (socket.io-client 4.8.1, chart.js 4.4.9)
└── local-module/
    ├── generate_cards.py
    ├── detector.py
    ├── client.py
    ├── main.py
    ├── test_assets/
    └── requirements.txt
```

**Decisión técnica:** todo en Python (FastAPI + python-socketio) para que Big Pickle trabaje en un solo lenguaje. El frontend es HTML plano con Chart.js y el cliente de Socket.IO servidos desde `frontend/vendor/`, sin build ni React.

**Prompt 1.1 (modo Plan):**

> Crea la estructura de carpetas que te describo (pego el árbol). Añade `.gitkeep` en las carpetas que puedan quedar vacías (`backend/tests/`, `local-module/test_assets/`), porque Git no versiona directorios vacíos. Crea un `.gitignore` para Python y Node que incluya `.env`, `venv/`, `__pycache__/`. Crea `.env.example` con: DATABASE_URL, REDIS_URL, API_KEY, SECRET_KEY, DASHBOARD_PASSWORD, PORT, ARUCO_DICT. No escribas código todavía.

**Prompt 1.2:** ejecuta `/init` y luego edita el `AGENTS.md` generado para que contenga:

```markdown
# Proyecto: Clicker por cámara
- Backend: FastAPI + python-socketio + SQLAlchemy async + asyncpg + redis.asyncio. Python 3.11.
- Frontend: HTML + JS plano + Chart.js + socket.io-client local en frontend/vendor. Sin frameworks.
- Módulo local: OpenCV (cv2.aruco) + python-socketio client. Python nativo de Windows.
- Bases de datos: PostgreSQL (permanente, fuente de verdad) y Redis (votos en vivo, caché).
- Reglas:
  - Nunca hardcodear secretos; usar variables de entorno validadas con pydantic-settings.
  - Nunca bloquear el event loop: SQLAlchemy async y redis.asyncio dentro de handlers de socket.
  - Un archivo por responsabilidad.
  - Al persistir votos usar INSERT ... ON CONFLICT (session_id, student_id) DO UPDATE.
  - Tests con pytest para cada endpoint y para la detección; BD clicker_test y Redis db 1 aislados.
  - Comentarios en español. Después de cada tarea correr los tests y mostrar el resultado.
- Eventos socket: ver sección "Contrato de eventos" (pegarla aquí abajo).
```

Pega ahí el contrato de eventos (Fase 3) para que el modelo no lo invente distinto cada vez.

Luego: `git init`, `git add .`, `git commit -m "estructura inicial"`, crea el repo en GitHub y `git push`. Así empiezas con GitHub desde el día 1.

**Descarga los vendor (una vez):** guarda `socket.io.min.js` (cliente 4.x) y `chart.umd.min.js` (Chart.js 4.x) en `frontend/vendor/` y fija las versiones en el README.

---

## Fase 2: Bases de datos locales (≈1 h)

**Prompt 2.1:**

> Crea `docker-compose.yml` con dos servicios: `postgres:16` (usuario, clave y base `clicker`, puerto 5432, volumen persistente) y `redis:7` (puerto 6379). Añade healthchecks a ambos servicios. Actualiza `.env.example` con las URLs correspondientes.

Comandos: `docker compose up -d`, luego `docker ps` para confirmar.

**Base de datos de test:** crea una base aparte para pytest una sola vez:

```powershell
docker exec -it <contenedor_postgres> psql -U clicker -d clicker -c "CREATE DATABASE clicker_test;"
```

Los tests usan `clicker_test` y Redis db 1 (`redis://localhost:6379/1`) para no contaminar los datos de la demo.

**Esquema PostgreSQL** (pídelo con SQLAlchemy async en `models.py`):

| Tabla | Campos |
|---|---|
| `students` | id, name, aruco_id (único), created_at |
| `questions` | id, text, option_a, option_b, option_c, option_d, correct_option, created_at |
| `voting_sessions` | id, question_id → questions, status (open/closed), opened_at, closed_at |
| `votes` | id, session_id, student_id, option, created_at, **único (session_id, student_id)** |

Restricciones obligatorias:
- `votes.option` con `CHECK (option IN ('A','B','C','D'))`.
- `questions.correct_option` con el mismo `CHECK`.
- `voting_sessions.status` con `CHECK (status IN ('open','closed'))` e índice en `status`.
- Timestamps con zona horaria (`TIMESTAMPTZ`) y `created_at` por defecto `now()`.
- `votes` se escribe con `ON CONFLICT (session_id, student_id) DO UPDATE`, porque el alumno puede cambiar de tarjeta.

**Redis (votos en vivo):**

```
active_session                    → id de la sesión abierta (caché; la verdad es Postgres)
session:{id}:votes                → hash {aruco_id: "A|B|C|D"}; si un alumno cambia de tarjeta, se sobrescribe
session:{id}:roster               → set de aruco_id registrados (se carga al abrir la sesión)
session:{id}:counts               → hash {A,B,C,D} derivado (opcional; si no, HGETALL)
session:{id}:stability:{aruco_id} → opcional, para filtrar lecturas inestables
```

Reglas de consistencia:
- Al cerrar: mapear `aruco_id → student_id` con la tabla `students`, persistir en **una transacción** y borrar las claves Redis **después del commit**.
- Cierre **idempotente**: si la sesión ya está `closed`, devolver los resultados existentes sin reescribir.
- Al arrancar el backend: si `active_session` apunta a una sesión cerrada en Postgres, borrar la clave.

**Criterio de terminado:** un script `python -m app.db` crea las tablas, un test confirma conexión a Postgres **y** Redis, y `GET /health` devuelve 503 si falla cualquiera de las dos.

---

## Fase 3: Backend (≈4 h)

**Contrato de eventos Socket.IO** (pégalo en `AGENTS.md`):

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

**Endpoints REST:**
- `POST /auth/login` y `POST /auth/logout` (cookie de sesión firmada con `SECRET_KEY`).
- `POST/GET /students` y `POST /students/bulk`: registrar estudiantes con su `aruco_id`.
- `POST/GET /questions`.
- `POST /sessions`: abre la votación (crea el registro, carga `roster` y `active_session` en Redis, emite `vote:open`).
- `POST /sessions/{id}/close`: mapea los votos de Redis a Postgres en una transacción, cierra, limpia Redis y emite `results:final`. Idempotente.
- `GET /sessions/active`: estado actual (para sincronizar clientes).
- `GET /sessions/{id}/results`: historial.
- `GET /health`: comprueba Postgres y Redis.

**Reglas de `vote:cast` (en este orden):**
1. Rechazar si `session_id != active_session` → `vote:rejected/stale_session`.
2. Rechazar si no hay sesión abierta → `vote:rejected/closed`.
3. Rechazar si `aruco_id` no está en `session:{id}:roster` → `vote:rejected/unknown`.
4. Rechazar si `option` no es A–D → `vote:rejected/invalid`.
5. Si es válido: `HSET` en `session:{id}:votes`, recalcular counts con `HGETALL` (≤50 alumnos, sobra) y emitir `tally:update` con `voted` y `missing`.

**Pasos con Big Pickle (un prompt por paso, con commit entre cada uno):**
1. `config.py` (pydantic-settings), `db.py` (motor async), `redis_client.py` (`redis.asyncio`), leyendo del `.env`.
2. `models.py` y `schemas.py` con las restricciones e índices de la Fase 2.
3. `routes.py`: primero estudiantes y preguntas, con tests.
4. `auth.py` y rutas de login/logout; cookie de sesión para el dashboard.
5. Sesiones (abrir y cerrar) con tests, incluido el cierre idempotente.
6. `sockets.py`: monta `socketio.AsyncServer` con `socketio.ASGIApp(sio, other_asgi_app=app)`, valida `api_key`/cookie en `connect`, emite `state:sync` y maneja `vote:cast` con las reglas anteriores.
7. Tests de sockets con `socketio.AsyncClient` contra uvicorn en fixture (o invocando handlers directos): auth inválida, voto válido, duplicado, sesión cerrada, `aruco_id` desconocido y `session_id` viejo.

**Criterio de terminado:** `pytest` en verde con BD `clicker_test` y Redis db 1 aislados, `uvicorn app.main:app --reload` levanta y un script de Python se conecta como "local" y envía votos falsos (uno válido y uno rechazado).

---

## Fase 4: Dashboard del profesor (≈3 h)

Funciones que debe tener `frontend/index.html`:
1. Login del profesor (contraseña → cookie de sesión) y formulario para crear una pregunta con 4 opciones y marcar la correcta.
2. Botones "Abrir votación" y "Cerrar votación".
3. Gráfico de barras de Chart.js que se actualiza con `tally:update` (usando el tally **completo**, no incrementando localmente, para tolerar reconexiones y duplicados).
4. Contador de participantes y de quiénes faltan por votar (a partir de `tally:update.missing`, alimentado por el `roster`).
5. Pantalla final con porcentaje de aciertos.
6. Gestión simple de estudiantes (nombre → `aruco_id`), leyendo `GET /students`.
7. Sincronización al abrir la página: `state:sync` / `GET /sessions/active` para reconstruir el estado si la votación ya está abierta.

**Prompt:** pide primero solo el esqueleto, el login y la conexión por socket, y luego añade el gráfico y los botones por separado. FastAPI sirve la carpeta `frontend/` con `StaticFiles` **al final de las rutas**, y `/socket.io` se atiende con `socketio.ASGIApp`, para que el estático no capture el socket. El dashboard se abre en `http://localhost:8000`.

---

## Fase 5: Módulo local de cámara (≈6 h, el más delicado)

### 5.1 Generar las tarjetas (`generate_cards.py`)
- Lee `ARUCO_DICT` (`DICT_4X4_50` por defecto; `DICT_5X5_100` si hay >30 alumnos o >3 m).
- Para cada `aruco_id`, genera un PNG con `cv2.aruco.generateImageMarker(dict, id, 600)` y añade 2 cm de borde blanco.
- Rotula las cuatro esquinas con A, B, C y D en pequeño, fuera del marcador, para que el alumno sepa qué lado poner arriba.
- Genera un PDF de 1 tarjeta por hoja para imprimir en A5 o A4. Marcador final de 12×12 cm, papel mate.
- Flag `--test-assets`: genera además los 4 PNG de prueba rotados con `cv2.rotate` (0°, 90°, 180°, 270°) en `test_assets/`, para que los tests no dependan de fotos hechas a mano.

### 5.2 Lógica de detección (`detector.py`)
Reglas que debes darle al modelo:
- Usa `cv2.aruco.ArucoDetector` (OpenCV ≥ 4.7) con el diccionario configurado.
- Para cada marcador, `corners[0]` son las 4 esquinas en orden: sup-izq, sup-der, inf-der, inf-izq del marcador.
- Calcula el ángulo del vector esquina0 → esquina1 con `atan2(c1.y-c0.y, c1.x-c0.x)` y elige el cuarto más cercano (0°, 90°, 180° o 270°).
- **Descarta la lectura si se desvía más de 15° del cuarto más cercano** (evita ambigüedad en diagonales).
- Mapeo: **0° → A, 90° → B, 180° → C, 270° → D**. Valídalo con las 4 imágenes de `test_assets/` y ajusta si la cámara real lo contradice.
- Flag `--flip` para cámaras que entregan la imagen espejada (invierte el sentido de giro).
- Función pura `detect_votes(frame) -> list[(aruco_id, option)]`, fácil de testear.

### 5.3 Estabilidad
- Un voto solo se envía si el mismo `(aruco_id, option)` se mantiene **durante 1.5 s continuos**, medidos con `time.monotonic()` (no por número de frames, que depende del FPS). Muestreo ≥10 Hz.
- Si cambia la opción, el contador se reinicia.
- No reenvíes si el alumno ya está registrado localmente con esa misma opción.
- Si cambia de opción y se estabiliza en la nueva, reenvía (el servidor sobrescribe).
- **Limpia la caché de "ya enviado" al reconectar** y al recibir `state:sync`.

### 5.4 Cliente socket (`client.py`)
- Se conecta con `python-socketio`, con `auth` y `api_key`, y reconexión automática.
- Escucha `vote:open`, `vote:close`, `state:sync` y `vote:rejected`. Solo detecta y envía mientras haya votación abierta; `state:sync` decide el estado inicial al conectar o reconectar.
- Loguea los votos rechazados para depurar en la demo.

### 5.5 Programa principal (`main.py`)
- Abre `cv2.VideoCapture(0)`, con opción `--video archivo.mp4` para probar sin cámara.
- Ventana de depuración que dibuja el recuadro, el ID, la letra detectada y el ángulo sobre cada tarjeta.
- Argumentos: `--server URL --camera 0 --show --flip`.

### Pruebas sin depender de la cámara
- Tests de `pytest` con los 4 PNG generados por `generate_cards.py --test-assets`; el mapeo de rotación debe coincidir con A/B/C/D.
- Luego prueba con la webcam real, ya con tarjetas impresas, a 1, 3 y 5 metros, con distinta luz. **Haz este spike el día 2**, antes de invertir en el dashboard.

**Consejos prácticos:** marcadores de 12 cm, mate (sin brillo), con borde blanco. Fija la resolución de la cámara a 1280×720 o más. Si hay varios estudiantes, el tamaño de la tarjeta y la distancia son lo que más limita; si a 5 m falla, cambia a `DICT_5X5_100` y reimprime.

---

## Fase 6: Integración local de punta a punta (≈2 h)

Orden para probar:
1. `docker compose up -d`
2. `uvicorn` del backend
3. Dashboard en `localhost:8000`: inicia sesión, registra 3 estudiantes y crea una pregunta
4. `python main.py --show`
5. Abre la votación, muestra las tarjetas y revisa que el gráfico se mueva
6. Cierra y verifica en Postgres (con DBeaver o `psql`) que quedaron los votos

**Casos borde a probar:**
- Alumno que cambia de respuesta (Postgres debe quedar con la última).
- Tarjeta de un ID no registrado (debe llegar `vote:rejected/unknown`).
- Dos tarjetas tapándose (se ignora la que no se ve; no debe votar mal).
- Caída y reconexión del socket a mitad de votación (el local debe resincronizar con `state:sync` y limpiar su caché).
- Voto duplicado tras reconexión (el servidor no debe duplicar).
- Voto con `session_id` viejo o votación cerrada (debe rechazarse).
- Reinicio del backend con sesión abierta (debe recuperar el estado desde Postgres y limpiar Redis huérfano).
- Cierre de sesión dos veces seguidas (idempotente).

---

## Fase 7: Despliegue en la nube (≈3 h)

| Pieza | Servicio gratuito sugerido |
|---|---|
| Backend + dashboard | Render (soporta WebSockets; alternativa: Fly.io o Koyeb) |
| PostgreSQL | Neon o Supabase |
| Redis | Upstash |

> **Railway ya no tiene plan gratuito** (solo prueba de pago). Usa Render como opción principal.

Pasos:
1. Crea las bases en Neon y Upstash y copia las URLs. En Upstash la URL es `rediss://` (TLS obligatorio); en Neon añade el SSL (`?ssl=require`, que con asyncpg se traduce en `ssl=require`).
2. En Render, crea un Web Service desde tu repo de GitHub. Comando de inicio: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, donde `app` debe ser el `ASGIApp` que envuelve Socket.IO.
3. Configura en el panel de Render (nunca en el repo): `DATABASE_URL`, `REDIS_URL`, `API_KEY`, `SECRET_KEY`, `DASHBOARD_PASSWORD`, `ARUCO_DICT`, `PORT`.
4. Ejecuta una vez `python -m app.db` desde la Shell de Render para crear las tablas y documenta el paso en el README.
5. Prueba `https://tu-app.onrender.com/health` (debe comprobar Postgres y Redis) y el login del dashboard.
6. Ejecuta el módulo local con `--server https://tu-app.onrender.com`.

> Los planes gratuitos de Render "duermen" tras ~15 min de inactividad y el WebSocket se cae. Abre la URL 5 minutos antes de presentar para despertarlo; el cliente local debe reconectar solo.

---

## Fase 8: GitHub y entrega (≈1 h)

- Cierra con un `README.md` que incluya: descripción, diagrama de arquitectura, requisitos, instalación local, variables de entorno, despliegue y capturas.
- Revisa que **no haya secretos** subidos:

```powershell
git log -p | Select-String -Pattern "password|api_key|secret|postgres://|rediss://"
```

- Haz commits claros por fase y sube todo (el requisito dice 100% en GitHub, incluidos los tres módulos).
- Etiqueta la versión final: `git tag v1.0`.

---

## Checklist contra los requisitos de la diapositiva

| Requisito | Evidencia |
|---|---|
| Desplegado en la nube | URL de Render funcionando |
| Módulo local | `local-module/` corriendo en tu PC |
| Algo con un socket | Socket.IO entre módulo local, servidor y dashboard |
| Cámara o micrófono | Webcam con detección ArUco |
| Mínimo 2 bases de datos | PostgreSQL + Redis |
| 100% en GitHub | Repo con las tres carpetas, sin secretos |

## Checklist de aceptación técnico (antes de la demo)

- [ ] `pytest` verde con BD `clicker_test` y Redis db 1 aislados.
- [ ] `vote:cast` rechaza sesión cerrada, `session_id` viejo, ID desconocido y opción inválida (evento `vote:rejected`).
- [ ] Cierre de sesión idempotente probado dos veces seguidas.
- [ ] Reconexión del local y del dashboard resincroniza estado (`state:sync`).
- [ ] `/health` devuelve 503 si cae Postgres o Redis.
- [ ] Ningún secreto en el repo (`Select-String` sin resultados).
- [ ] Detección validada a 1, 3 y 5 m con la cámara real y las tarjetas impresas.
- [ ] El dashboard funciona sin CDN externo (vendor local).

---

## Cronograma sugerido (≈7 días)

| Día | Fases |
|---|---|
| 1 | 0, 1, 2 |
| 2 | **Spike de cámara** (imprimir 2 tarjetas, validar 1/3/5 m) + inicio de Fase 3 |
| 3 | 3 (backend completo con tests) |
| 4 | 4 (dashboard) |
| 5-6 | 5 (cámara completa) y 6 (integración) |
| 7 | 7 y 8 (nube y entrega) + ensayo de la demo |

**Guion de la demo:** repartir 3–5 tarjetas, crear la pregunta en el dashboard, abrir la votación, que levanten las tarjetas, mostrar el gráfico moviéndose y cerrar para ver los resultados y el historial.


enlace de git: https://github.com/Juan-Pablo-Parra-Ducuara/proyecto-final.git