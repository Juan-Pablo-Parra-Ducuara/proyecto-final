/**
 * Microfrontend del escáner QR del navegador.
 *
 * Replica la lógica de `local-module/detector.py`: el ángulo del primer lado
 * del QR define la opción y la lectura debe mantenerse estable 0,5 s.
 * Envía los votos por el socket compartido del dashboard, sin conocer al
 * microfrontend que lo compone.
 */

import { loadStyleOnce } from "../../shared/assets.js";
import { on } from "../../shared/bus.js";
import { $, descargarHtml } from "../../shared/dom.js";
import { getSocket } from "../../shared/socket.js";
import { store } from "../../shared/store.js";

const ORIENTACIONES = { A: 0, B: 90, C: 180, D: 270 };
const TOLERANCIA_GRADOS = 35;
const ESTABILIDAD_MS = 500;
const INTERVALO_MS = 120;

const MOTIVOS = {
  unknown: "QR no registrado en esta sesión",
  closed: "La votación está cerrada",
  invalid: "Opción inválida",
  stale_session: "La sesión cambió; vuelve a abrir la votación",
};

const state = {
  stream: null,
  detector: null,
  canvas: null,
  ctx: null,
  video: null,
  running: false,
  timer: null,
  estados: new Map(),
};

let cancelaciones = [];
let alOcultarPagina = null;

function setStatus(texto, enLinea) {
  const badge = $("scanner-status");

  if (!badge) return;

  badge.textContent = texto;
  badge.classList.toggle("online", Boolean(enLinea));
  badge.classList.toggle("offline", !enLinea);
}

function log(mensaje, error = false) {
  const lista = $("scanner-log");

  if (!lista) return;

  const item = document.createElement("li");
  item.textContent = mensaje;

  if (error) item.classList.add("error");

  lista.prepend(item);

  while (lista.children.length > 12) {
    lista.removeChild(lista.lastChild);
  }
}

function mostrarLectura(texto) {
  const salida = $("scanner-detected");

  if (salida) salida.textContent = texto;
}

async function start() {
  if (state.running) return;

  if (!navigator.mediaDevices?.getUserMedia) {
    log(
      "Este navegador no permite usar la cámara. Abre el panel con HTTPS.",
      true,
    );
    return;
  }

  setStatus("Iniciando…", false);

  try {
    state.stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        facingMode: { ideal: "environment" },
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
    });

    state.video.srcObject = state.stream;
    await state.video.play();

    state.running = true;
    $("scanner-start").disabled = true;
    $("scanner-stop").disabled = false;
    setStatus("Leyendo QR", true);

    prepararDetector();
    programarLectura();
  } catch (error) {
    setStatus("Detenido", false);
    log(describirErrorCamara(error), true);
    detenerStream();
  }
}

function stop() {
  state.running = false;
  clearTimeout(state.timer);
  state.timer = null;
  state.estados.clear();

  detenerStream();

  const botonIniciar = $("scanner-start");
  const botonDetener = $("scanner-stop");

  if (botonIniciar) botonIniciar.disabled = false;
  if (botonDetener) botonDetener.disabled = true;

  setStatus("Detenido", false);
}

function detenerStream() {
  if (state.stream) {
    state.stream.getTracks().forEach((track) => track.stop());
    state.stream = null;
  }

  if (state.video) state.video.srcObject = null;
}

function describirErrorCamara(error) {
  if (window.isSecureContext === false) {
    return (
      "La cámara exige HTTPS. Abre el panel con https:// o desde localhost " +
      "(ver scripts/https-local.ps1)."
    );
  }

  if (error?.name === "NotAllowedError") {
    return "Permiso de cámara denegado. Habilítalo en el navegador.";
  }

  if (error?.name === "NotFoundError") {
    return "No se encontró ninguna cámara en este dispositivo.";
  }

  return `No se pudo abrir la cámara: ${error?.message || error}`;
}

function prepararDetector() {
  state.detector = null;

  if (!("BarcodeDetector" in window)) return;

  try {
    state.detector = new window.BarcodeDetector({ formats: ["qr_code"] });
  } catch {
    state.detector = null;
  }
}

function programarLectura() {
  if (!state.running) return;

  state.timer = setTimeout(async () => {
    try {
      await leerFotograma();
    } catch (error) {
      log(`Error al leer la cámara: ${error?.message || error}`, true);
    }

    programarLectura();
  }, INTERVALO_MS);
}

async function leerFotograma() {
  const video = state.video;

  if (!video || video.readyState < 2) return;

  const ancho = video.videoWidth;
  const alto = video.videoHeight;

  if (!ancho || !alto) return;

  const ahora = performance.now();
  const lecturas = await detectar(video, ancho, alto);
  const presentes = new Set();

  for (const lectura of lecturas) {
    const token = String(lectura.token || "").trim();

    if (!token) continue;

    presentes.add(token);

    const angulo = calcularAngulo(lectura.corners);
    const orientacion = clasificar(angulo);

    mostrarLectura(
      `Ángulo ${angulo.toFixed(0)}° · ` +
        (orientacion ? `opción ${orientacion}` : "sin opción reconocida"),
    );

    const confirmado = actualizarEstado(token, orientacion, ahora);

    if (confirmado) enviarVoto(token, confirmado);
  }

  limpiarEstados(presentes, ahora);
}

async function detectar(video, ancho, alto) {
  if (state.detector) {
    try {
      const codigos = await state.detector.detect(video);

      return codigos
        .filter((codigo) => codigo.rawValue)
        .map((codigo) => ({
          token: codigo.rawValue,
          corners: codigo.cornerPoints || [],
        }));
    } catch {
      /* se intenta con jsQR */
    }
  }

  return detectarConJsQr(video, ancho, alto);
}

function detectarConJsQr(video, ancho, alto) {
  if (typeof window.jsQR !== "function" || !state.ctx) return [];

  const canvas = state.canvas;

  if (canvas.width !== ancho || canvas.height !== alto) {
    canvas.width = ancho;
    canvas.height = alto;
  }

  state.ctx.drawImage(video, 0, 0, ancho, alto);

  const imagen = state.ctx.getImageData(0, 0, ancho, alto);
  const resultado = window.jsQR(
    imagen.data,
    imagen.width,
    imagen.height,
    { inversionAttempts: "dontInvert" },
  );

  if (!resultado || !resultado.data) return [];

  const ubicacion = resultado.location || {};

  return [
    {
      token: resultado.data,
      corners: [
        ubicacion.topLeftCorner,
        ubicacion.topRightCorner,
        ubicacion.bottomRightCorner,
        ubicacion.bottomLeftCorner,
      ].filter(Boolean),
    },
  ];
}

function calcularAngulo(corners) {
  if (!corners || corners.length < 2) return 0;

  const [p1, p2] = corners;
  const angulo = (Math.atan2(p2.y - p1.y, p2.x - p1.x) * 180) / Math.PI;

  return (angulo + 360) % 360;
}

function clasificar(angulo) {
  let mejor = null;
  let menorDiferencia = Infinity;

  for (const [letra, objetivo] of Object.entries(ORIENTACIONES)) {
    const diferencia = Math.abs(angulo - objetivo);
    const minima = Math.min(diferencia, 360 - diferencia);

    if (minima < menorDiferencia) {
      menorDiferencia = minima;
      mejor = letra;
    }
  }

  return menorDiferencia <= TOLERANCIA_GRADOS ? mejor : null;
}

function actualizarEstado(token, orientacion, ahora) {
  let estado = state.estados.get(token);

  if (!estado) {
    estado = {
      candidato: null,
      desde: ahora,
      ultimoEnviado: null,
    };

    state.estados.set(token, estado);
  }

  if (orientacion === null) {
    estado.candidato = null;
    estado.desde = ahora;
    return null;
  }

  if (orientacion !== estado.candidato) {
    estado.candidato = orientacion;
    estado.desde = ahora;
  }

  if (ahora - estado.desde < ESTABILIDAD_MS) return null;
  if (orientacion === estado.ultimoEnviado) return null;

  estado.ultimoEnviado = orientacion;
  return orientacion;
}

function limpiarEstados(presentes, ahora) {
  for (const [token, estado] of state.estados) {
    if (!presentes.has(token) && ahora - estado.desde > 1500) {
      state.estados.delete(token);
    }
  }
}

function enviarVoto(token, opcion) {
  const socket = getSocket();
  const sesion = store.session;

  if (!socket?.connected) {
    log("Sin conexión con el servidor; no se envió el voto.", true);
    return;
  }

  if (!sesion || sesion.status !== "open") {
    log("No hay una votación abierta; no se envió el voto.", true);
    return;
  }

  socket.emit("vote:cast", {
    session_id: sesion.id,
    qr_token: token,
    option: opcion,
  });

  log(`Enviado: QR ${token.slice(0, 8)}… → opción ${opcion}`);
}

function handleAccepted(datos) {
  log(`Voto registrado: opción ${datos.option}`);
  mostrarLectura(`Voto registrado para la opción ${datos.option}.`);
}

function handleRejected(datos) {
  const motivo = MOTIVOS[datos.reason] || datos.reason || "desconocido";
  log(`Voto rechazado: ${motivo}`, true);
}

export async function mount(root) {
  loadStyleOnce("css-mfe-scanner", "/microfrontends/scanner/scanner.css");
  root.innerHTML = await descargarHtml(
    "/microfrontends/scanner/view.html",
  );

  state.video = $("scanner-video");
  state.canvas = $("scanner-canvas");

  if (state.canvas) {
    state.ctx = state.canvas.getContext("2d", { willReadFrequently: true });
  }

  $("scanner-start")?.addEventListener("click", start);
  $("scanner-stop")?.addEventListener("click", stop);

  // El escáner no debe seguir encendido al cerrar la pestaña.
  alOcultarPagina = () => stop();
  window.addEventListener("pagehide", alOcultarPagina);

  cancelaciones.push(
    on("vote:accepted", handleAccepted),
    on("vote:rejected", handleRejected),
  );

  return () => {
    stop();
    cancelaciones.forEach((cancelar) => cancelar());
    cancelaciones = [];
    window.removeEventListener("pagehide", alOcultarPagina);
    alOcultarPagina = null;
  };
}
