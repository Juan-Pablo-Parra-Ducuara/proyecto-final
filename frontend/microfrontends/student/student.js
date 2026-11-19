/**
 * Microfrontend del estudiante.
 *
 * Es de solo lectura: nunca emite `vote:cast`. Muestra su QR, el estado de la
 * votación y su resultado personal usando los eventos del bus compartido.
 */

import { api } from "../../shared/api.js";
import { logout } from "../../shared/auth.js";
import { loadStyleOnce } from "../../shared/assets.js";
import { on } from "../../shared/bus.js";
import { ANGULOS, OPCIONES } from "../../shared/constants.js";
import { $, descargarHtml, escapeHtml, notify } from "../../shared/dom.js";
import { connectSocket } from "../../shared/socket.js";
import { store } from "../../shared/store.js";

let cancelaciones = [];
let preguntaActual = null;
let respuestaElegida = null;

function setStudentConnection(conectado) {
  const badge = $("student-live-status");

  if (!badge) return;

  badge.textContent = conectado ? "En vivo" : "Sin conexión";
  badge.classList.toggle("online", conectado);
  badge.classList.toggle("offline", !conectado);
}

function renderStudentQr(token) {
  const contenedor = $("student-qr-code");

  if (!contenedor) return;

  contenedor.innerHTML = "";

  if (!token) {
    contenedor.textContent = "No se encontró el código QR.";
    return;
  }

  if (typeof window.QRCode === "undefined") {
    contenedor.textContent = "No se pudo cargar el generador de códigos QR.";
    return;
  }

  new window.QRCode(contenedor, {
    text: token,
    width: 240,
    height: 240,
    colorDark: "#000000",
    colorLight: "#ffffff",
    correctLevel: window.QRCode.CorrectLevel.H,
  });
}

function renderStudentOptions(options) {
  const opciones = options || {};

  $("student-options").innerHTML = OPCIONES.map(
    (letra) => `
        <button
            type="button"
            class="student-answer-button"
            data-student-option="${letra}"
            aria-pressed="false">
            <span class="answer-letter" aria-hidden="true">${letra}</span>
            <span class="answer-text">${escapeHtml(opciones[letra] || "")}</span>
            <small>Seleccionar respuesta</small>
        </button>
    `,
  ).join("");
}

function resetStudentRotation() {
  respuestaElegida = null;

  const qr = $("student-qr-code");
  if (qr) qr.style.transform = "rotate(0deg)";

  const dial = $("rotation-dial");
  if (dial) dial.style.setProperty("--angle", "0deg");

  const etiqueta = $("rotation-label");
  if (etiqueta) etiqueta.textContent = "Sin respuesta seleccionada";

  document.querySelectorAll(".student-answer-button").forEach((boton) => {
    boton.classList.remove("selected");
    boton.setAttribute("aria-pressed", "false");

    const pista = boton.querySelector("small");
    if (pista) pista.textContent = "Seleccionar respuesta";
  });
}

function selectStudentAnswer(opcion) {
  if (!Object.prototype.hasOwnProperty.call(ANGULOS, opcion)) return;

  respuestaElegida = opcion;

  const angulo = ANGULOS[opcion];
  const qr = $("student-qr-code");
  if (qr) qr.style.transform = `rotate(${angulo}deg)`;

  const dial = $("rotation-dial");
  if (dial) dial.style.setProperty("--angle", `${angulo}deg`);

  const etiqueta = $("rotation-label");
  if (etiqueta) {
    etiqueta.textContent = `QR girado ${angulo}° · opción ${opcion}`;
  }

  document.querySelectorAll(".student-answer-button").forEach((boton) => {
    const seleccionada = boton.dataset.studentOption === opcion;

    boton.classList.toggle("selected", seleccionada);
    boton.setAttribute("aria-pressed", String(seleccionada));

    const pista = boton.querySelector("small");
    if (pista) {
      pista.textContent = seleccionada
        ? "Respuesta seleccionada"
        : "Seleccionar respuesta";
    }
  });

  $("student-voting-status").textContent =
    `Respuesta ${opcion} seleccionada. Mantén tu QR quieto frente a la cámara.`;
}

function applyStudentState(datos) {
  if (!datos) return;

  const estado = datos.voting_status || datos.status;
  const question = datos.question || null;
  const badge = $("student-vote-badge");

  if (estado !== "open" || !question) {
    $("student-voting-status").textContent =
      "Actualmente no hay ninguna votación abierta. " +
      "Se actualizará automáticamente cuando el docente la inicie.";

    $("student-question-container").classList.add("hidden");
    $("student-question-text").textContent = "";

    if (badge) {
      badge.textContent = "Sin votación";
      badge.className = "badge offline";
    }

    resetStudentRotation();
    return;
  }

  // Al cambiar de pregunta no se conserva la respuesta anterior.
  if (question.id !== preguntaActual) {
    preguntaActual = question.id;
    respuestaElegida = null;
    $("student-result").classList.add("hidden");
  }

  if (badge) {
    badge.textContent = "Votación abierta";
    badge.className = "badge online";
  }

  $("student-voting-status").textContent =
    "Selecciona una respuesta. Puedes cambiarla mientras la votación esté abierta.";

  $("student-question-text").textContent = question.text;
  renderStudentOptions(datos.options);
  $("student-question-container").classList.remove("hidden");

  if (OPCIONES.includes(datos.your_vote)) {
    selectStudentAnswer(datos.your_vote);
  } else if (respuestaElegida) {
    selectStudentAnswer(respuestaElegida);
  } else {
    resetStudentRotation();
  }
}

function markStudentVoteAccepted(datos) {
  if (!datos?.option) return;

  respuestaElegida = datos.option;
  selectStudentAnswer(datos.option);

  $("student-voting-status").textContent =
    `Voto registrado: opción ${datos.option}. ` +
    "Puedes cambiarlo mientras la votación siga abierta.";
}

function showStudentResult(datos) {
  if (!datos) return;

  const card = $("student-result");
  const contenedor = $("student-result-body");

  if (!card || !contenedor) return;

  const counts = datos.counts || {};
  const your = datos.your || {};
  const propias = OPCIONES.map(
    (letra) => `
        <li>
            <span class="answer-letter" aria-hidden="true">${letra}</span>
            ${counts[letra] ?? 0} voto(s)
        </li>
    `,
  ).join("");

  let mensaje = "No registramos tu voto en esta votación.";

  if (your.option) {
    mensaje = your.correct
      ? `Tu respuesta ${your.option} es correcta.`
      : `Tu respuesta ${your.option} no es la correcta.`;
  }

  contenedor.innerHTML = `
        <ul class="student-result-counts">${propias}</ul>
        <p class="student-result-your">${escapeHtml(mensaje)}</p>
        <p class="hint">
            Respuesta correcta: ${escapeHtml(datos.correct_option || "no definida")}.
        </p>
    `;

  card.classList.remove("hidden");

  const badge = $("student-vote-badge");

  if (badge) {
    badge.textContent = "Votación cerrada";
    badge.className = "badge offline";
  }

  $("student-voting-status").textContent = "Resultados de la votación.";
}

async function cargarPanel() {
  const datos = await api("/student-auth/panel", {}, false);

  store.student = datos.student;
  $("student-name-display").textContent = datos.student.name;

  renderStudentQr(datos.qr_token);
  applyStudentState(datos);
}

function suscribirse() {
  cancelaciones.push(
    on("socket:connect", () => setStudentConnection(true)),
    on("socket:disconnect", () => setStudentConnection(false)),
    on("socket:error", () => setStudentConnection(false)),
    on("state:sync", (datos) => applyStudentState(datos)),

    on("vote:open", (datos) => {
      preguntaActual = null;
      respuestaElegida = null;
      $("student-result").classList.add("hidden");
      applyStudentState(datos);
    }),

    on("vote:close", () => {
      const badge = $("student-vote-badge");

      if (badge) {
        badge.textContent = "Votación cerrada";
        badge.className = "badge offline";
      }

      $("student-voting-status").textContent =
        "La votación terminó. Esperando los resultados...";
    }),

    on("vote:accepted", (datos) => markStudentVoteAccepted(datos)),
    on("results:final", (datos) => showStudentResult(datos)),
  );
}

function enlazarEventos() {
  $("student-options").addEventListener("click", (evento) => {
    const boton = evento.target.closest("[data-student-option]");

    if (boton) selectStudentAnswer(boton.dataset.studentOption);
  });

  $("student-logout-button").addEventListener("click", async () => {
    try {
      await logout("student");
    } catch (error) {
      notify(error.message, true);
    }
  });

  $("student-refresh-button").addEventListener("click", async () => {
    try {
      await cargarPanel();
      notify("Estado de la votación actualizado.");
    } catch (error) {
      notify(error.message, true);
    }
  });
}

export async function mount(root) {
  loadStyleOnce("css-mfe-student", "/microfrontends/student/student.css");
  root.innerHTML = await descargarHtml(
    "/microfrontends/student/view.html",
  );

  suscribirse();
  enlazarEventos();

  // Las escuchas ya están activas antes de abrir el socket.
  connectSocket("student");

  try {
    await cargarPanel();
  } catch (error) {
    $("student-voting-status").textContent = error.message;
    $("student-question-container").classList.add("hidden");
    notify(error.message, true);
  }

  return () => {
    cancelaciones.forEach((cancelar) => cancelar());
    cancelaciones = [];
    preguntaActual = null;
    respuestaElegida = null;
  };
}
