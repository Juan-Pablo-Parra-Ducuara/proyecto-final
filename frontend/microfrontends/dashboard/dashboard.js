/**
 * Microfrontend del docente.
 *
 * Gestiona estudiantes, preguntas y el control de la sesión. Compone los
 * microfrontends de escáner y resultados en sus propios slots y publica los
 * cambios de estado en el bus para que ambos se mantengan sincronizados.
 */

import { api } from "../../shared/api.js";
import { logout } from "../../shared/auth.js";
import { loadStyleOnce } from "../../shared/assets.js";
import { emit, on } from "../../shared/bus.js";
import { OPCIONES } from "../../shared/constants.js";
import { $, descargarHtml, escapeHtml, notify } from "../../shared/dom.js";
import {
  mountMicrofrontend,
  unmountMicrofrontend,
} from "../../shared/registry.js";
import { connectSocket } from "../../shared/socket.js";
import { store } from "../../shared/store.js";

let cancelaciones = [];

function setConnection(connected) {
  const badge = $("connection-status");

  if (!badge) return;

  badge.textContent = connected ? "Conectado" : "Desconectado";
  badge.classList.toggle("online", connected);
  badge.classList.toggle("offline", !connected);
}

function getQuestionNumber(questionId) {
  const indice = store.questions.findIndex(
    (pregunta) => Number(pregunta.id) === Number(questionId),
  );

  return indice === -1 ? null : indice + 1;
}

function updateQuestionLabel() {
  const numero = getQuestionNumber($("question-select").value);

  $("question-label-text").textContent =
    numero === null ? "Pregunta" : `Pregunta ${numero}`;
}

function renderStudents() {
  const lista = $("student-list");
  lista.innerHTML = "";

  if (!store.students.length) {
    lista.innerHTML = '<li><span>Sin estudiantes registrados</span></li>';
    return;
  }

  for (const student of store.students) {
    const item = document.createElement("li");

    const nombre = document.createElement("span");
    nombre.textContent = `${student.name} — ID #${student.id}`;

    const correo = document.createElement("span");
    correo.textContent = student.email || "Sin cuenta de acceso";

    const eliminar = document.createElement("button");
    eliminar.type = "button";
    eliminar.textContent = "Eliminar";
    eliminar.className = "danger";

    eliminar.addEventListener("click", async () => {
      const confirmar = confirm(
        `¿Estás seguro de eliminar al estudiante ${student.name}?\n\n` +
          `También se eliminarán todas sus respuestas registradas.`,
      );

      if (!confirmar) return;

      try {
        const resultado = await api(`/students/${student.id}`, {
          method: "DELETE",
        });

        await loadStudents();

        if (store.session && store.session.status === "open") {
          store.session.roster = store.session.roster.filter(
            (id) => Number(id) !== Number(student.aruco_id),
          );

          if (resultado.tally) {
            emit("session:changed", {
              session: store.session,
              counts: resultado.tally.counts,
              total: resultado.tally.total,
              missing: resultado.tally.missing,
            });
          }
        }

        notify(`Estudiante ${student.name} eliminado correctamente.`);
      } catch (error) {
        notify(error.message, true);
      }
    });

    item.append(nombre, correo, eliminar);
    lista.append(item);
  }
}

async function loadStudents() {
  store.students = await api("/students");
  renderStudents();
  emit("students:changed", { students: store.students });
}

async function loadQuestions() {
  store.questions = await api("/questions");

  const select = $("question-select");
  const anterior = select.value;

  select.innerHTML = "";

  if (!store.questions.length) {
    const opcion = document.createElement("option");
    opcion.value = "";
    opcion.textContent = "Sin preguntas creadas";
    select.append(opcion);

    updateQuestionLabel();
    emit("question:selected", { questionId: null });
    return;
  }

  store.questions.forEach((question) => {
    const opcion = document.createElement("option");
    opcion.value = question.id;
    opcion.textContent = question.text;
    select.append(opcion);
  });

  if (anterior && store.questions.some((q) => String(q.id) === anterior)) {
    select.value = anterior;
  }

  store.selectedQuestionId = Number(select.value) || null;
  updateQuestionLabel();
  emit("question:selected", { questionId: store.selectedQuestionId });
}

function updateSessionUi() {
  const abierta = Boolean(store.session && store.session.status === "open");

  $("open-button").disabled = abierta;
  $("close-button").disabled = !abierta;
  $("question-select").disabled = abierta;
  $("session-status").classList.toggle("is-open", abierta);

  if (!store.session) {
    $("session-status").textContent = "Sin sesión activa.";
    return;
  }

  $("session-status").textContent = abierta
    ? `Sesión #${store.session.id} abierta.`
    : `Sesión #${store.session.id} cerrada.`;
}

function renderSessionDetails() {
  if (!store.session) {
    $("current-question").textContent = "";
    $("options-list").innerHTML = "";
    return;
  }

  $("current-question").textContent =
    store.session.question?.text || "Pregunta sin texto";

  const opciones = store.session.options || {};

  $("options-list").innerHTML = OPCIONES.map(
    (letra) =>
      `<li><strong>${letra}</strong><span>${escapeHtml(
        opciones[letra] || "",
      )}</span></li>`,
  ).join("");
}

function applyState(datos) {
  if (!datos || !datos.session_id) {
    store.session = null;
    updateSessionUi();
    renderSessionDetails();
    emit("session:changed", { session: null });
    emit("question:selected", {
      questionId: Number($("question-select").value) || null,
    });
    return;
  }

  store.session = {
    id: datos.session_id,
    status: datos.status,
    question: datos.question,
    options: datos.options,
    roster: datos.roster || [],
  };

  $("question-select").value = String(datos.question?.id ?? "");
  store.selectedQuestionId = Number($("question-select").value) || null;
  updateQuestionLabel();
  updateSessionUi();
  renderSessionDetails();

  emit("session:changed", {
    session: store.session,
    counts: datos.counts,
    total: datos.total,
    missing: datos.missing,
  });
}

async function loadActiveSession() {
  applyState(await api("/sessions/active"));
}

function suscribirse() {
  cancelaciones.push(
    on("socket:connect", () => setConnection(true)),
    on("socket:disconnect", () => setConnection(false)),
    on("socket:error", () => setConnection(false)),
    on("state:sync", (datos) => applyState(datos)),
    on("vote:open", (datos) =>
      applyState({
        session_id: datos.session_id,
        status: "open",
        question: datos.question,
        options: datos.options,
        roster: datos.roster || [],
      }),
    ),
    on("vote:close", (datos) => {
      if (
        store.session &&
        Number(datos.session_id) === Number(store.session.id)
      ) {
        store.session.status = "closed";
        updateSessionUi();
        emit("session:changed", { session: store.session });
      }
    }),
  );
}

function enlazarEventos() {
  $("logout-button").addEventListener("click", async () => {
    try {
      await logout("teacher");
    } catch (error) {
      notify(error.message, true);
    }
  });

  $("student-form").addEventListener("submit", async (evento) => {
    evento.preventDefault();

    try {
      const resultado = await api("/students/accounts", {
        method: "POST",
        body: JSON.stringify({
          name: $("student-account-name").value.trim(),
          email: $("student-account-email").value.trim(),
          password: $("student-account-password").value,
        }),
      });

      $("student-form").reset();
      await loadStudents();

      notify(
        `Cuenta creada correctamente. ID del estudiante: ${resultado.id}`,
      );
    } catch (error) {
      notify(error.message, true);
    }
  });

  $("question-form").addEventListener("submit", async (evento) => {
    evento.preventDefault();

    try {
      const nueva = await api("/questions", {
        method: "POST",
        body: JSON.stringify({
          text: $("question-text").value.trim(),
          option_a: $("option-a").value.trim(),
          option_b: $("option-b").value.trim(),
          option_c: $("option-c").value.trim(),
          option_d: $("option-d").value.trim(),
          correct_option: $("correct-option").value,
        }),
      });

      $("question-form").reset();
      await loadQuestions();

      $("question-select").value = String(nueva.id);
      store.selectedQuestionId = nueva.id;

      const numero = getQuestionNumber(nueva.id);

      $("question-feedback").textContent =
        `Pregunta ${numero} creada correctamente.`;
      updateQuestionLabel();
      emit("question:selected", { questionId: nueva.id });
      notify("Pregunta creada");
    } catch (error) {
      notify(error.message, true);
    }
  });

  $("question-select").addEventListener("change", async () => {
    updateQuestionLabel();

    if (store.session && store.session.status === "open") {
      notify("Debes cerrar la votación antes de cambiar de pregunta.", true);
      $("question-select").value = String(store.session.question.id);
      updateQuestionLabel();
      return;
    }

    store.session = null;
    store.selectedQuestionId = Number($("question-select").value) || null;

    updateSessionUi();
    emit("session:changed", { session: null });
    emit("question:selected", { questionId: store.selectedQuestionId });
  });

  $("open-button").addEventListener("click", async () => {
    const questionId = Number($("question-select").value);

    if (!questionId) {
      notify("Crea una pregunta antes de abrir la votación", true);
      return;
    }

    try {
      await api("/sessions", {
        method: "POST",
        body: JSON.stringify({ question_id: questionId }),
      });

      await loadActiveSession();
      notify("Votación abierta");
    } catch (error) {
      notify(error.message, true);
    }
  });

  $("close-button").addEventListener("click", async () => {
    if (!store.session) return;

    try {
      const resultados = await api(
        `/sessions/${store.session.id}/close`,
        { method: "POST" },
      );

      store.session.status = "closed";
      updateSessionUi();
      emit("session:changed", { session: store.session });
      emit("results:final", resultados);
      notify("Votación cerrada");
    } catch (error) {
      notify(error.message, true);
    }
  });

  $("clear-answers-button").addEventListener("click", async () => {
    const questionId = Number($("question-select").value);

    if (!questionId) {
      notify("Selecciona una pregunta primero.", true);
      return;
    }

    const question = store.questions.find(
      (q) => Number(q.id) === questionId,
    );

    if (!question) return;

    const numero = getQuestionNumber(questionId);

    const confirmar = confirm(
      `¿Estás seguro de que deseas borrar TODAS las respuestas ` +
        `de la pregunta ${numero}?\n\n` +
        `Esta acción no elimina la pregunta, pero sí sus respuestas ` +
        `y su historial de votaciones.`,
    );

    if (!confirmar) return;

    try {
      const resultado = await api(`/questions/${questionId}/answers`, {
        method: "DELETE",
      });

      if (
        store.session &&
        store.session.status === "open" &&
        Number(store.session.question.id) === questionId
      ) {
        emit("tally:update", {
          session_id: store.session.id,
          counts: { A: 0, B: 0, C: 0, D: 0 },
          total: 0,
          missing: store.session.roster,
        });
        $("session-status").textContent =
          `Sesión #${store.session.id} abierta. Respuestas reiniciadas.`;
      } else {
        emit("question:selected", { questionId });
      }

      notify(
        `Se eliminaron ${resultado.deleted_votes} respuestas correctamente.`,
      );
    } catch (error) {
      notify(error.message, true);
    }
  });

  $("delete-question-button").addEventListener("click", async () => {
    const questionId = Number($("question-select").value);

    if (!questionId) {
      notify("Selecciona una pregunta primero.", true);
      return;
    }

    const question = store.questions.find(
      (q) => Number(q.id) === questionId,
    );

    if (!question) return;

    const numero = getQuestionNumber(questionId);

    const confirmar = confirm(
      `¿Estás seguro de eliminar la pregunta ${numero}?\n\n` +
        `"${question.text}"\n\n` +
        `Se eliminarán también todas sus sesiones y respuestas registradas.\n` +
        `Esta acción no se puede deshacer.`,
    );

    if (!confirmar) return;

    try {
      await api(`/questions/${questionId}`, { method: "DELETE" });

      await loadQuestions();
      await loadActiveSession();
      emit("question:selected", {
        questionId: Number($("question-select").value) || null,
      });

      notify(
        store.questions.length
          ? `Pregunta ${numero} eliminada correctamente.`
          : "Pregunta eliminada. No quedan preguntas registradas.",
      );
    } catch (error) {
      notify(error.message, true);
    }
  });
}

export async function mount(root) {
  loadStyleOnce("css-mfe-dashboard", "/microfrontends/dashboard/dashboard.css");
  root.innerHTML = await descargarHtml(
    "/microfrontends/dashboard/view.html",
  );

  suscribirse();
  enlazarEventos();

  await Promise.all([
    mountMicrofrontend("scanner", $("mfe-scanner-slot")),
    mountMicrofrontend("live", $("mfe-live-slot")),
    mountMicrofrontend("results", $("mfe-results-slot")),
  ]);

  // Las escuchas ya están registradas: no se pierde el `state:sync` inicial.
  connectSocket("dashboard");

  await Promise.all([loadStudents(), loadQuestions()]);
  await loadActiveSession();

  return () => {
    cancelaciones.forEach((cancelar) => cancelar());
    cancelaciones = [];
    unmountMicrofrontend("scanner");
    unmountMicrofrontend("live");
    unmountMicrofrontend("results");
  };
}
