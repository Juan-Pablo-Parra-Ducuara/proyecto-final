const $ = (id) => document.getElementById(id);

const state = {
  students: [],
  questions: [],
  session: null,
  chart: null,
  socket: null,
  toastTimer: null,
};

const OPCIONES = ["A", "B", "C", "D"];

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => {
    const mapa = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return mapa[char];
  });
}

function notify(message, isError = false) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.remove("hidden");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => toast.classList.add("hidden"), 3500);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });

  if (response.status === 401) {
    showLogin();
    throw new Error("No autorizado");
  }

  if (!response.ok) {
    let detalle = `Error ${response.status}`;
    try {
      const data = await response.json();
      if (data.detail) detalle = data.detail;
    } catch {
      /* sin cuerpo JSON */
    }
    throw new Error(detalle);
  }

  if (response.status === 204) return null;
  return response.json();
}

function showLogin() {
  $("dashboard-view").classList.add("hidden");
  $("login-view").classList.remove("hidden");
  if (state.socket) {
    state.socket.disconnect();
    state.socket = null;
  }
}

async function showDashboard() {
  $("login-view").classList.add("hidden");
  $("dashboard-view").classList.remove("hidden");

  await Promise.all([loadStudents(), loadQuestions()]);
  await loadActiveSession();

  connectSocket();
}

function setConnection(connected) {
  const badge = $("connection-status");
  badge.textContent = connected ? "Conectado" : "Desconectado";
  badge.classList.toggle("online", connected);
  badge.classList.toggle("offline", !connected);
}

function connectSocket() {
  if (state.socket) state.socket.disconnect();

  state.socket = io({ withCredentials: true });

  state.socket.on("connect", () => setConnection(true));
  state.socket.on("disconnect", () => setConnection(false));
  state.socket.on("connect_error", () => {
    setConnection(false);
    notify("No se pudo conectar el dashboard", true);
  });

  state.socket.on("state:sync", (data) => applyState(data));

  state.socket.on("vote:open", (data) => {
    state.session = {
      id: data.session_id,
      status: "open",
      question: data.question,
      options: data.options,
      roster: data.roster || [],
    };

    $("question-select").value = String(data.question.id);
    updateQuestionLabel();

    resetChart();
    resetFinal();
    updateSessionUi();
    renderSessionDetails();
    updateMissing(data.roster || [], []);
    $("total-votes").textContent = "0";
  });

  state.socket.on("vote:close", (data) => {
    if (state.session && data.session_id === state.session.id) {
      state.session.status = "closed";
      updateSessionUi();
    }
  });

  state.socket.on("tally:update", (data) => {
    if (state.session && data.session_id !== state.session.id) return;
    updateChart(data.counts);
    $("total-votes").textContent = data.total;
    updateMissing(state.session ? state.session.roster : [], data.missing);
  });

  state.socket.on("results:final", (data) => showFinal(data));
}

function applyState(data) {
  if (!data || !data.session_id) {
    state.session = null;
    updateSessionUi();

    const questionId = Number($("question-select").value);

    if (questionId) {
      loadSelectedQuestionResults();
    } else {
      resetChart();
      resetFinal();
      renderSessionDetails();
      updateQuestionLabel();
    }

    return;
  }

  state.session = {
    id: data.session_id,
    status: data.status,
    question: data.question,
    options: data.options,
    roster: data.roster || [],
  };

  // Seleccionar automáticamente la pregunta de la sesión activa.
  $("question-select").value = String(data.question.id);
  updateQuestionLabel();

  updateSessionUi();
  renderSessionDetails();

  if (data.counts) {
    updateChart(data.counts);
    $("total-votes").textContent = data.total ?? 0;
    updateMissing(state.session.roster, data.missing || []);
  }
}

async function loadStudents() {
  state.students = await api("/students");
  renderStudents();
}

function renderStudents() {
  const lista = $("student-list");
  lista.innerHTML = "";

  if (!state.students.length) {
    lista.innerHTML = '<li><span>Sin estudiantes registrados</span></li>';
    return;
  }

  for (const student of state.students) {
    const item = document.createElement("li");

    const nombre = document.createElement("span");
    nombre.textContent = student.name;

    const aruco = document.createElement("span");
    aruco.textContent = `ArUco #${student.aruco_id}`;

    const eliminar = document.createElement("button");
    eliminar.type = "button";
    eliminar.textContent = "Eliminar";
    eliminar.className = "danger";

    eliminar.addEventListener("click", async () => {
      const confirmar = confirm(
        `¿Estás seguro de eliminar al estudiante ${student.name}?\n\n` +
        `También se eliminarán todas sus respuestas registradas.`
      );

      if (!confirmar) return;

      try {
        const resultado = await api(
          `/students/${student.id}`,
          { method: "DELETE" }
        );

        await loadStudents();

        // Actualizar los participantes de la sesión activa.
        if (state.session && state.session.status === "open") {
          state.session.roster = state.session.roster.filter(
            (id) => Number(id) !== Number(student.aruco_id)
          );

          if (resultado.tally) {
            updateChart(resultado.tally.counts);
            $("total-votes").textContent = resultado.tally.total;

            updateMissing(
              state.session.roster,
              resultado.tally.missing
            );
          }
        }

        notify(`Estudiante ${student.name} eliminado correctamente.`);

      } catch (error) {
        notify(error.message, true);
      }
    });

    item.append(nombre, aruco, eliminar);
    lista.append(item);
  }
}

// Devuelve el número consecutivo visible de una pregunta.
function getQuestionNumber(questionId) {
  const index = state.questions.findIndex(
    (q) => Number(q.id) === Number(questionId)
  );

  return index === -1 ? null : index + 1;
}

// Actualiza el texto gris que aparece encima del selector.
function updateQuestionLabel() {
  const select = $("question-select");
  const label = $("question-label-text");

  const numero = getQuestionNumber(select.value);

  label.textContent = numero === null
    ? "Pregunta"
    : `Pregunta ${numero}`;
}

async function loadQuestions() {
  state.questions = await api("/questions");

  const select = $("question-select");
  const anterior = select.value;

  select.innerHTML = "";

  if (!state.questions.length) {
    const opcion = document.createElement("option");
    opcion.value = "";
    opcion.textContent = "Sin preguntas creadas";
    select.append(opcion);

    updateQuestionLabel();
    return;
  }

  state.questions.forEach((question) => {
    const opcion = document.createElement("option");

    // Se conserva el ID real de la base de datos.
    opcion.value = question.id;

    // Dentro del selector solo aparece el texto.
    opcion.textContent = question.text;

    select.append(opcion);
  });

  if (anterior && state.questions.some(
    (q) => String(q.id) === anterior
  )) {
    select.value = anterior;
  }

  updateQuestionLabel();
}

async function loadActiveSession() {
  const data = await api("/sessions/active");
  applyState(data);
}

// Recuperar los resultados guardados de la pregunta seleccionada.
async function loadSelectedQuestionResults() {
  const questionId = Number($("question-select").value);

  if (!questionId) return;

  updateQuestionLabel();

  // No reemplazar los resultados de una votación que sigue abierta.
  if (state.session && state.session.status === "open") {
    const activeQuestionId = Number(state.session.question?.id);

    if (activeQuestionId !== questionId) {
      notify("Primero debes cerrar la votación activa.", true);
      $("question-select").value = String(activeQuestionId);
      updateQuestionLabel();
    }

    return;
  }

  const question = state.questions.find(
    (q) => Number(q.id) === questionId
  );

  if (!question) return;

  $("current-question").textContent = question.text;

  const opciones = {
    A: question.option_a,
    B: question.option_b,
    C: question.option_c,
    D: question.option_d,
  };

  $("options-list").innerHTML = OPCIONES.map(
    (letra) =>
      `<li><strong>${letra}</strong><span>${escapeHtml(
        opciones[letra] || ""
      )}</span></li>`
  ).join("");

  resetFinal();
  resetChart();

  try {
    const results = await api(
      `/questions/${questionId}/results/latest`
    );

    showFinal(results);

    $("session-status").textContent =
      `Mostrando resultados guardados de la pregunta #${questionId}.`;

    notify("Resultados anteriores recuperados");

  } catch (error) {
    resetFinal();
    resetChart();

    $("session-status").textContent =
      `Pregunta #${questionId} seleccionada.`;

    if (error.message.includes("todavía no tiene resultados")) {
      notify("Esta pregunta todavía no tiene respuestas guardadas.");
    } else {
      notify(error.message, true);
    }
  }
}

function updateSessionUi() {
  const abierta = Boolean(
    state.session && state.session.status === "open"
  );

  $("open-button").disabled = abierta;
  $("close-button").disabled = !abierta;

  // Bloquear selector únicamente mientras se vota.
  $("question-select").disabled = abierta;

  if (!state.session) {
    $("session-status").textContent = "Sin sesión activa.";
    return;
  }

  $("session-status").textContent = abierta
    ? `Sesión #${state.session.id} abierta.`
    : `Sesión #${state.session.id} cerrada.`;
}

function renderSessionDetails() {
  if (!state.session) {
    $("current-question").textContent = "";
    $("options-list").innerHTML = "";
    return;
  }

  $("current-question").textContent =
    state.session.question?.text || "Pregunta sin texto";

  const opciones = state.session.options || {};

  $("options-list").innerHTML = OPCIONES.map(
    (letra) =>
      `<li><strong>${letra}</strong><span>${escapeHtml(
        opciones[letra] || ""
      )}</span></li>`
  ).join("");
}

function updateMissing(roster, missing) {
  const faltan = missing || [];
  $("missing-count").textContent = faltan.length;

  if (!roster || !roster.length) {
    $("missing-list").textContent = "";
    return;
  }

  if (!faltan.length) {
    $("missing-list").textContent = "Todos han votado.";
    return;
  }

  const nombres = faltan.map((arucoId) => {
    const alumno = state.students.find(
      (student) => student.aruco_id === arucoId
    );

    return alumno ? `${alumno.name} (#${arucoId})` : `#${arucoId}`;
  });

  $("missing-list").textContent = `Faltan por votar: ${nombres.join(", ")}`;
}

function createChart() {
  if (typeof Chart === "undefined") {
    notify("No se cargó Chart.js (vendor)", true);
    return;
  }

  const contexto = $("results-chart");

  state.chart = new Chart(contexto, {
    type: "bar",
    data: {
      labels: OPCIONES,
      datasets: [
        {
          label: "Votos",
          data: [0, 0, 0, 0],
          backgroundColor: ["#3056d3", "#1f8a5b", "#d98a1f", "#c73636"],
          borderRadius: 8,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
          ticks: { precision: 0 },
        },
      },
      plugins: {
        legend: { display: false },
      },
    },
  });
}

function updateChart(counts) {
  if (!state.chart || !counts) return;

  state.chart.data.datasets[0].data = OPCIONES.map(
    (letra) => counts[letra] || 0
  );

  state.chart.update();
}

function resetChart() {
  updateChart({ A: 0, B: 0, C: 0, D: 0 });
  $("total-votes").textContent = "0";
  $("missing-count").textContent = "0";
  $("missing-list").textContent = "";
}

function resetFinal() {
  $("final-card").classList.add("hidden");
  $("final-summary").textContent = "";
  $("final-table").innerHTML = "";
}

function showFinal(results) {
  const alumnos = results.per_student || [];
  const aciertos = alumnos.filter((alumno) => alumno.correct).length;
  const total = alumnos.length;

  const totalVotos = Object.values(results.counts || {}).reduce(
    (suma, cantidad) => suma + cantidad,
    0
  );

  const porcentaje = total ? Math.round((aciertos * 100) / total) : 0;

  $("total-votes").textContent = totalVotos;

  $("final-summary").textContent =
    `Aciertos: ${aciertos}/${total} (${porcentaje}%). ` +
    `Respuesta correcta: ${results.correct_option}.`;

  $("final-table").innerHTML = alumnos
    .map(
      (alumno) => `
        <tr>
          <td>${escapeHtml(alumno.name)}</td>
          <td>${escapeHtml(alumno.option)}</td>
          <td>${alumno.correct ? "Correcto" : "Incorrecto"}</td>
        </tr>`
    )
    .join("");

  $("final-card").classList.remove("hidden");
  updateChart(results.counts);
}

function bindEvents() {

  // Borrar todas las respuestas de la pregunta seleccionada.
  $("clear-answers-button").addEventListener("click", async () => {
    const questionId = Number($("question-select").value);

    if (!questionId) {
      notify("Selecciona una pregunta primero.", true);
      return;
    }

    const question = state.questions.find(
      (q) => Number(q.id) === questionId
    );

    if (!question) {
      notify("No se encontró la pregunta seleccionada.", true);
      return;
    }

    const numeroPregunta = getQuestionNumber(questionId);

    const confirmar = confirm(
      `¿Estás seguro de que deseas borrar TODAS las respuestas ` +
      `de la pregunta ${numeroPregunta}?\n\n` +
      `Esta acción no elimina la pregunta, pero sí sus respuestas ` +
      `y su historial de votaciones.`
    );

    if (!confirmar) return;

    try {
      const resultado = await api(
        `/questions/${questionId}/answers`,
        { method: "DELETE" }
      );

      resetChart();
      resetFinal();

      if (
        state.session &&
        state.session.status === "open" &&
        Number(state.session.question.id) === questionId
      ) {
        updateMissing(state.session.roster, []);
        $("session-status").textContent =
          `Sesión #${state.session.id} abierta. Respuestas reiniciadas.`;
      } else {
        $("session-status").textContent =
          `Historial de la pregunta ${numeroPregunta} eliminado.`;
      }

      notify(
        `Se eliminaron ${resultado.deleted_votes} respuestas correctamente.`
      );

    } catch (error) {
      notify(error.message, true);
    }
  });

  // Eliminar pregunta y todas sus sesiones y respuestas.
  $("delete-question-button").addEventListener("click", async () => {
    const questionId = Number($("question-select").value);

    if (!questionId) {
      notify("Selecciona una pregunta primero.", true);
      return;
    }

    const question = state.questions.find(
      (q) => Number(q.id) === questionId
    );

    if (!question) {
      notify("No se encontró la pregunta seleccionada.", true);
      return;
    }

    const numeroPregunta = getQuestionNumber(questionId);

    const confirmar = confirm(
      `¿Estás seguro de eliminar la pregunta ${numeroPregunta}?\n\n` +
      `"${question.text}"\n\n` +
      `Se eliminarán también todas sus sesiones y respuestas registradas.\n` +
      `Esta acción no se puede deshacer.`
    );

    if (!confirmar) return;

    try {
      await api(
        `/questions/${questionId}`,
        { method: "DELETE" }
      );

      // Actualizar el listado y la numeración.
      await loadQuestions();

      // Recuperar el estado de la sesión activa.
      await loadActiveSession();

      if (!state.questions.length) {
        state.session = null;
        resetChart();
        resetFinal();
        renderSessionDetails();
        updateSessionUi();
        updateQuestionLabel();

        notify("Pregunta eliminada. No quedan preguntas registradas.");
        return;
      }

      notify(`Pregunta ${numeroPregunta} eliminada correctamente.`);

    } catch (error) {
      notify(error.message, true);
    }
  });

  // Consultar el historial al cambiar la pregunta seleccionada.
  $("question-select").addEventListener("change", async () => {
    updateQuestionLabel();

    if (state.session && state.session.status === "open") {
      notify("Debes cerrar la votación antes de cambiar de pregunta.", true);
      $("question-select").value = String(state.session.question.id);
      updateQuestionLabel();
      return;
    }

    state.session = null;

    resetChart();
    resetFinal();
    updateSessionUi();

    await loadSelectedQuestionResults();
  });

  $("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    $("login-error").textContent = "";

    try {
      await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ password: $("password").value }),
      });

      $("password").value = "";
      await showDashboard();

    } catch (error) {
      $("login-error").textContent = error.message;
    }
  });

  $("logout-button").addEventListener("click", async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      showLogin();
    }
  });

  $("student-form").addEventListener("submit", async (event) => {
    event.preventDefault();

    try {
      await api("/students", {
        method: "POST",
        body: JSON.stringify({
          name: $("student-name").value.trim(),
          aruco_id: Number($("student-aruco").value),
        }),
      });

      $("student-form").reset();
      await loadStudents();
      notify("Estudiante añadido");

    } catch (error) {
      notify(error.message, true);
    }
  });

  $("question-form").addEventListener("submit", async (event) => {
    event.preventDefault();

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

      // Recargar primero para calcular la numeración correcta.
      await loadQuestions();

      // Seleccionar la pregunta recién creada usando su ID real.
      $("question-select").value = String(nueva.id);

      const numeroPregunta = getQuestionNumber(nueva.id);

      $("question-feedback").textContent =
        `Pregunta ${numeroPregunta} creada correctamente.`;

      updateQuestionLabel();

      notify("Pregunta creada");

    } catch (error) {
      notify(error.message, true);
    }
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

      resetFinal();
      await loadActiveSession();
      notify("Votación abierta");

    } catch (error) {
      notify(error.message, true);
    }
  });

  $("close-button").addEventListener("click", async () => {
    if (!state.session) return;

    try {
      const resultados = await api(
        `/sessions/${state.session.id}/close`,
        { method: "POST" }
      );

      state.session.status = "closed";
      updateSessionUi();
      showFinal(resultados);

      notify("Votación cerrada");

    } catch (error) {
      notify(error.message, true);
    }
  });
}

async function init() {
  bindEvents();
  createChart();

  try {
    await api("/auth/me");
    await showDashboard();
  } catch {
    showLogin();
  }
}

document.addEventListener("DOMContentLoaded", init);