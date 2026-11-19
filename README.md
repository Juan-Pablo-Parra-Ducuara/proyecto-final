# Clicker por cámara

Votación en vivo en el aula mediante códigos QR y una webcam. Los alumnos giran
su tarjeta para elegir A, B, C o D; el módulo local y el escáner web detectan la
opción con la misma lógica y la envían por Socket.IO al backend. El profesor abre
y cierra la votación desde un dashboard y ve los resultados en tiempo real.

## Arquitectura

```
[Webcam + tarjetas]                  [Teléfono: cámara + escáner QR]
         │                                      │
         ▼                                      ▼
[local-module] ──Socket.IO──▶ [FastAPI + python-socketio] ──▶ [PostgreSQL]
   (módulo local)                    │  │                    [Redis]
                                     │  └──Socket.IO──▶ [Shell del frontend]
                                     │                       │
                                     │         ┌──────────────┴───────────────┐
                                     │         ▼                              ▼
                                     │   [MFE dashboard]               [MFE estudiante]
                                     │     ├─ MFE en vivo (KPIs + chart)
                                      │     ├─ MFE resultados finales
                                     │     └─ MFE escáner QR
                                     └──── Socket.IO para todos los clientes autenticados
```

- **PostgreSQL:** fuente de verdad (estudiantes, preguntas, sesiones, votos).
- **Redis:** estado vivo de la votación (roster, votos, sesión activa).
- **Socket.IO:** canal en tiempo real entre módulo local, escáner, servidor, dashboard
  y panel del estudiante (este último recibe el estado en vivo sin datos de otros alumnos).
- **Microfrontends:** el navegador carga un shell que compone unidades independientes
  (acceso, dashboard, en vivo, resultados, escáner y estudiante) sin frameworks ni build.

## Requisitos

- Python 3.11+
- Node.js 20+ (solo para descargar/actualizar los vendor)
- Git
- Docker Desktop (Postgres y Redis locales)
- Webcam y tarjetas impresas (módulo local)
- Opcional: `mkcert` para HTTPS local y usar la cámara del teléfono

> En Windows, ejecuta el módulo local con Python nativo. No uses WSL para la cámara.

## Estructura del repositorio

```
backend/        FastAPI + Socket.IO + SQLAlchemy async
frontend/
  index.html    shell: carga el vendor y arranca el host
  shell.js      host: enrutado, ciclo de vida y socket compartido
  shared/       api, auth, bus, socket, store, registry, utilidades de DOM
  microfrontends/
    auth/       acceso docente y estudiante
    dashboard/  gestión y control de la votación; compone los tres siguientes
    live/       sección "En vivo": KPIs, participación y gráfica Chart.js
    results/    resumen y tabla de resultados finales
    scanner/    escáner QR con la cámara del dispositivo
    student/    QR personal, estado del voto y resultado individual
  vendor/       librerías locales (sin CDN)
local-module/   Detección QR/ArUco + cliente Socket.IO (módulo local)
scripts/        Utilidades de desarrollo (HTTPS local con mkcert)
```

## Microfrontends

El frontend está dividido en seis microfrontends independientes, cargados con
`import()` nativo del navegador (sin bundler ni framework):

| Microfrontend | Responsabilidad | Se monta en |
|---|---|---|
| `auth` | selector de rol y formularios de acceso | `#app` (ruta `#/auth`) |
| `dashboard` | estudiantes, preguntas y apertura/cierre | `#app` (ruta `#/dashboard`) |
| `live` | sección "En vivo": KPIs, participación y gráfica | `#mfe-live-slot` del dashboard |
| `results` | resumen y tabla del cierre | `#mfe-results-slot` del dashboard |
| `scanner` | cámara y envío de `vote:cast` | `#mfe-scanner-slot` del dashboard |
| `student` | panel de solo lectura del alumno | `#app` (ruta `#/student`) |

Contratos:

- Cada microfrontend vive en su carpeta con `view.html`, `<nombre>.js` y `<nombre>.css`.
- Cada módulo exporta `async function mount(root)` y devuelve una función de limpieza.
- Se comunican únicamente mediante `frontend/shared/bus.js` (eventos
  `auth:changed`, `session:changed`, `students:changed`, `question:selected`,
  `tally:update`, `results:final`, `results:history`, `vote:*`, `socket:*`).
  `live` publica `results:history` y `results` solo presenta. No se importan entre sí.
- `frontend/shared/socket.js` mantiene **una sola conexión** Socket.IO y publica
  los eventos del servidor en el bus. El módulo local se conecta por separado con
  la **misma cookie firmada del dashboard**, obtenida con la contraseña del
  profesor; el estudiante usa su propia cookie.
- `frontend/style.css` es el sistema de diseño compartido; cada microfrontend
  añade su propia hoja con estilos scopeados a su contenedor.

Para añadir uno nuevo: crear la carpeta, exportar `mount(root)`, registrar el
nombre en `frontend/shared/registry.js` y decidir qué evento del bus lo monta.

## Módulo local (cámara)

Es un programa de Python que corre **en el PC del profesor con Python nativo de
Windows** (nunca en WSL, porque el acceso a la webcam en WSL2 es inestable).
No vive en el navegador: es un cliente Socket.IO más. Al arrancar pide la
**contraseña del dashboard**, hace `POST /auth/login` y conecta con la misma
cookie `clicker_session` que usa la web (rol `dashboard`). Ya no necesita
`API_KEY`; el backend la conserva solo por compatibilidad con clientes antiguos.

### Archivos y responsabilidades

| Archivo | Función |
|---|---|
| `generate_cards.py` | Genera las **mismas tarjetas QR** que muestra la web: PNG/PDF A4/A5 con el `qr_token` del estudiante, QR de 12×12 cm y 2 cm de margen con guías A/B/C/D. Opciones: `--ids`, `--students-csv` (columnas `name,qr_token`), `--test-assets`, `--test-token`. |
| `detector.py` | `QRDetector` abre `cv2.VideoCapture` (1280×720), detecta hasta 2 QR por fotograma con `cv2.QRCodeDetector`, calcula el ángulo del primer lado y lo clasifica: 0°→A, 90°→B, 180°→C, 270°→D (tolerancia 35°). Un voto solo se emite si la misma opción se mantiene 0,5 s; se recuerda el último voto enviado por token para no repetirlo. |
| `client.py` | `LocalSocketClient` hace login con `POST /auth/login`, guarda la cookie `clicker_session` y conecta con `headers={"Cookie": ...}` como `dashboard`, con reconexión automática. Mantiene `voting_open`, `session_id` y `roster` protegidos con `threading.Lock` porque los callbacks de `python-socketio` corren en otro hilo. Escucha `state:sync`, `vote:open`, `vote:close`, `vote:accepted`, `vote:rejected` y `results:final`; al cambiar de estado limpia la memoria del detector (`on_state_reset`). |
| `main.py` | Punto de entrada: carga `.env`, pide la contraseña del dashboard (o la toma de `--password`), crea detector y cliente, conecta, **abre el dashboard web en el navegador ya autenticado**, abre la cámara y en bucle hace `read_frame() → detect_votes() → send_vote()`. Opciones: `--server`, `--camera`, `--password`, `--show` (ventana de depuración) y `--no-browser` (no abrir el navegador). |

### Inicio de sesión en consola

```powershell
cd local-module
python main.py --show
# Contraseña del dashboard: ********
```

La contraseña se pide de forma interactiva (no se muestra al escribir). Para
automatizar el arranque se puede pasar `--password ...`, pero en ese caso queda
en el historial de la terminal; en producción es preferible el prompt interactivo.
Si la contraseña es incorrecta, el programa muestra `Contraseña incorrecta.` y
termina. No hay que configurar `API_KEY` en el módulo local.

Al iniciar sesión, el módulo pide un ticket de un solo uso a
`POST /auth/desktop-ticket` y abre `http://127.0.0.1:8000/?desktop_ticket=...`.
El shell del frontend canjea ese ticket en `POST /auth/desktop-login`, limpia la
URL y monta directamente el microfrontend `dashboard`. Es la **misma interfaz
web**: login, estudiantes, preguntas, botones de abrir/cerrar, KPIs, gráfica en
vivo, escáner QR y resultados finales. La cámara del módulo sigue detectando en
segundo plano mientras el profesor usa el navegador.

Si no quieres que se abra el navegador:

```powershell
python main.py --show --no-browser
```

En ese caso el módulo sigue conectado y votando; el dashboard se abre manualmente
en otro dispositivo o pestaña.

### Tarjetas iguales que en la web

El QR impreso contiene exactamente el `qr_token` que el alumno ve en su panel
(`#/student`). Al girar la tarjeta se elige la respuesta, igual que en la web:

| Giro | Opción |
|---|---|
| 0° | A |
| 90° | B |
| 180° | C |
| 270° | D |

Para generar las tarjetas de un curso, exporta un CSV con `name,qr_token` y
ejecuta:

```powershell
cd local-module
python generate_cards.py --students-csv estudiantes.csv --paper A4
```

Ese mismo QR funciona con el módulo local y con el escáner del dashboard.
También puedes generar QRs sueltos con `--ids 1 2 3` o las cuatro imágenes
rotadas de prueba con `--test-assets --test-token token-de-prueba`.

### Flujo de un voto

1. El docente abre la sesión: el backend guarda el `roster` en Redis y emite
   `vote:open` al módulo local con `session_id`, pregunta y opciones.
2. El alumno levanta su tarjeta girada. El detector lee el QR, obtiene el token
   del estudiante y la letra según el ángulo; si se mantiene estable 0,5 s,
   `main.py` llama a `send_vote(token, opcion)`.
3. El cliente comprueba que hay sesión abierta y envía
   `vote:cast {session_id, qr_token, option}` por el socket (WebSocket).
4. El backend valida en orden: sesión vigente → abierta → token en el roster →
   opción A–D. Si algo falla, responde `vote:rejected` con el motivo.
5. Si es válido, hace `HSET` en `session:{id}:votes`, recalcula los conteos y
   emite `tally:update`. El microfrontend `live` mueve la gráfica en tiempo real.
6. Al cerrar, el backend persiste los votos en PostgreSQL en una transacción
   (`ON CONFLICT (session_id, student_id) DO UPDATE`) y emite `results:final`;
   los microfrontends `live` y `results` muestran el cierre.

La contraseña del docente solo se usa en el login; la sesión viaja en la cookie
firmada `clicker_session`, nunca se incrusta en el HTML. Tanto el módulo local
como la cámara del navegador (microfrontend `scanner`) emiten `vote:cast` con esa
misma cookie. El backend sigue aceptando `auth={role:"local", api_key:...}` como
compatibilidad legacy, pero el módulo local ya no lo utiliza.

## Instalación local

```powershell
# 1. Variables de entorno
Copy-Item .env.example .env
# Edita .env y cambia SECRET_KEY y DASHBOARD_PASSWORD
# (API_KEY queda solo como compatibilidad legacy del backend)

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
# Te pedirá la contraseña definida en DASHBOARD_PASSWORD.
# Alternativa: python main.py --show --password "tu-contraseña"
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
| `API_KEY` | Clave legacy para clientes antiguos; el módulo local actual ya no la usa |
| `SECRET_KEY` | Clave para firmar la cookie de sesión del dashboard |
| `DASHBOARD_PASSWORD` | Contraseña del dashboard del profesor |
| `PORT` | Puerto del servidor (8000 en local) |

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
