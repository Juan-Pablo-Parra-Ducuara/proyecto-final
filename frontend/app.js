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
    resetChart();
    resetFinal();
    updateSessionUi();
    renderSessionDetails();
    return;
  }

  state.session = {
    id: data.session_id,
    status: data.status,
    question: data.question,
    options: data.options,
    roster: data.roster || [],
  };

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
    item.append(nombre, aruco);
    lista.append(item);
  }
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
    return;
  }

  for (const question of state.questions) {
    const opcion = document.createElement("option");
    opcion.value = question.id;
    opcion.textContent = `#${question.id} · ${question.text}`;
    select.append(opcion);
  }

  if (anterior && state.questions.some((q) => String(q.id) === anterior)) {
    select.value = anterior;
  }
}

async function loadActiveSession() {
  const data = await api("/sessions/active");
  applyState(data);
}

function updateSessionUi() {
  const abierta = state.session && state.session.status === "open";
  $("open-button").disabled = Boolean(abierta);
  $("close-button").disabled = !abierta;

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
  const porcentaje = total ? Math.round((aciertos * 100) / total) : 0;

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
      $("question-feedback").textContent = `Pregunta #${nueva.id} creada.`;
      await loadQuestions();
      $("question-select").value = String(nueva.id);
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
