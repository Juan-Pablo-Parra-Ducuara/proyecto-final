const $ = (id) => document.getElementById(id);

const state = {
  students: [],
  questions: [],
  session: null,
  selectedAnswer: null,
  chart: null,
  socket: null,
  toastTimer: null,
  student: null,
  studentQuestionId: null,
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

async function api(path, options = {}, handleUnauthorized = true) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (response.status === 401 && handleUnauthorized) {
    showLogin();
    throw new Error("No autorizado");
  }

  if (!response.ok) {
    let detalle = `Error ${response.status}`;

    try {
      const data = await response.json();
      if (data.detail) {
    if (Array.isArray(data.detail)) {
        detalle = data.detail
            .map((item) => {
                const campo = item.loc?.slice(1).join(".") || "dato";
                return `${campo}: ${item.msg || "Dato inválido"}`;
            })
            .join(" | ");
    } else if (typeof data.detail === "object") {
        detalle = data.detail.message || JSON.stringify(data.detail);
    } else {
        detalle = data.detail;
    }
}
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
  $("student-view").classList.add("hidden");
  $("login-view").classList.remove("hidden");

  $("role-selection").classList.remove("hidden");
  $("teacher-login").classList.add("hidden");
  $("student-login").classList.add("hidden");

  $("password").value = "";
  $("student-email").value = "";
  $("student-password").value = "";

  $("login-error").textContent = "";
  $("student-login-error").textContent = "";

  state.student = null;
  state.studentQuestionId = null;
  state.selectedAnswer = null;

  if (state.socket) {
    state.socket.disconnect();
    state.socket = null;
  }
}

async function showDashboard() {
  $("login-view").classList.add("hidden");
  $("student-view").classList.add("hidden");
  $("dashboard-view").classList.remove("hidden");

  await Promise.all([loadStudents(), loadQuestions()]);
  await loadActiveSession();

  connectSocket();
}

function renderStudentQr(token) {
    const container = document.getElementById("student-qr-code");

    if (!container) return;

    // Limpiar el QR anterior.
    container.innerHTML = "";

    if (!token) {
        container.textContent = "No se encontró el código QR.";
        return;
    }

    if (typeof QRCode === "undefined") {
        container.textContent = "No se pudo cargar el generador de códigos QR.";
        return;
    }

    new QRCode(container, {
        text: token,
        width: 240,
        height: 240,
        colorDark: "#000000",
        colorLight: "#ffffff",
        correctLevel: QRCode.CorrectLevel.H
    });
}


async function showStudentPanel() {
    $("login-view").classList.add("hidden");
    $("dashboard-view").classList.add("hidden");
    $("student-view").classList.remove("hidden");

    try {
        const data = await api("/student-auth/panel", {}, false);

        state.student = data.student;

        // Al cambiar de pregunta no se conserva la respuesta anterior.
        const preguntaId = data.question?.id ?? null;

        if (preguntaId !== state.studentQuestionId) {
            state.studentQuestionId = preguntaId;
            state.selectedAnswer = null;
        }

        $("student-name-display").textContent = data.student.name;

        renderStudentQr(data.qr_token);

        const badge = $("student-vote-badge");

        if (data.voting_status !== "open" || !data.question) {
            $("student-voting-status").textContent =
                "Actualmente no hay ninguna votación abierta. " +
                "Actualiza cuando el docente la inicie.";

            $("student-question-container").classList.add("hidden");

            if (badge) {
                badge.textContent = "Sin votación";
                badge.className = "badge offline";
            }

            resetStudentRotation();
            return;
        }

        if (badge) {
            badge.textContent = "Votación abierta";
            badge.className = "badge online";
        }

        $("student-voting-status").textContent =
            "Selecciona una respuesta. Puedes cambiarla mientras la votación esté abierta.";

        $("student-question-text").textContent = data.question.text;

        const opciones = data.options || {};

        $("student-options").innerHTML = OPCIONES.map((letra) => `
            <button
                type="button"
                class="student-answer-button"
                data-student-option="${letra}"
                aria-pressed="false">
                <span class="answer-letter" aria-hidden="true">${letra}</span>
                <span class="answer-text">${escapeHtml(opciones[letra] || "")}</span>
                <small>Seleccionar respuesta</small>
            </button>
        `).join("");

        $("student-question-container").classList.remove("hidden");

        if (state.selectedAnswer) {
            selectStudentAnswer(state.selectedAnswer);
        } else {
            resetStudentRotation();
        }

    } catch (error) {
        $("student-voting-status").textContent = error.message;
        $("student-question-container").classList.add("hidden");
        notify(error.message, true);
    }
}


function resetStudentRotation() {
    state.selectedAnswer = null;

    const qr = $("student-qr-code");

    if (qr) qr.style.transform = "rotate(0deg)";

    const dial = $("rotation-dial");

    if (dial) dial.style.setProperty("--angle", "0deg");

    const etiqueta = $("rotation-label");

    if (etiqueta) etiqueta.textContent = "Sin respuesta seleccionada";

    document.querySelectorAll(".student-answer-button").forEach((button) => {
        button.classList.remove("selected");
        button.setAttribute("aria-pressed", "false");

        const pista = button.querySelector("small");

        if (pista) pista.textContent = "Seleccionar respuesta";
    });
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
        `También se eliminarán todas sus respuestas registradas.`
      );

      if (!confirmar) return;

      try {
        const resultado = await api(
          `/students/${student.id}`,
          { method: "DELETE" }
        );

        await loadStudents();

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

   item.append(nombre, correo, eliminar);
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
    opcion.value = question.id;
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

  $("question-select").disabled = abierta;

  $("session-status").classList.toggle("is-open", abierta);

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

// Nombre visible de un alumno a partir de su identificador de cámara.
function nombreAlumno(arucoId) {
  const alumno = state.students.find(
    (student) => String(student.aruco_id) === String(arucoId)
  );

  return alumno ? alumno.name : `Estudiante #${arucoId}`;
}

function updateMissing(roster, missing) {
  const ids = (roster || []).map(String);
  const faltan = (missing || []).map(String);

  const total = ids.length;
  const votaron = Math.max(0, total - faltan.length);
  const porcentaje = total ? Math.round((votaron * 100) / total) : 0;

  $("missing-count").textContent = faltan.length;

  const relleno = $("participation-fill");
  if (relleno) relleno.style.width = `${porcentaje}%`;

  const porcentajeTexto = $("participation-percent");
  if (porcentajeTexto) porcentajeTexto.textContent = `${porcentaje}%`;

  const barra = $("participation-progress");
  if (barra) barra.setAttribute("aria-valuenow", String(porcentaje));

  const contenedor = $("roster-chips");

  if (contenedor) {
    if (!total) {
      contenedor.innerHTML =
        '<p class="hint">Sin estudiantes inscritos en esta votación.</p>';
    } else {
      contenedor.innerHTML = ids
        .map((id) => {
          const voto = !faltan.includes(id);

          return (
            `<span class="chip ${voto ? "voted" : "missing"}" ` +
            `title="${voto ? "Ya votó" : "Falta por votar"}">` +
            `${escapeHtml(nombreAlumno(id))}</span>`
          );
        })
        .join("");
    }
  }

  if (!total) {
    $("missing-list").textContent = "";
    return;
  }

  if (!faltan.length) {
    $("missing-list").textContent = "Todos los estudiantes han votado.";
    return;
  }

  $("missing-list").textContent =
    `Faltan por votar: ${faltan.map((id) => nombreAlumno(id)).join(", ")}`;
}

// Colores del gráfico según el tema activo.
function coloresTema() {
  const estilos = getComputedStyle(document.documentElement);

  return {
    texto: estilos.getPropertyValue("--muted").trim() || "#6b7a94",
    linea: estilos.getPropertyValue("--line").trim() || "#e1e8f3",
  };
}

function aplicarTemaGrafica() {
  if (!state.chart) return;

  const { texto, linea } = coloresTema();

  state.chart.options.scales.x.ticks.color = texto;
  state.chart.options.scales.y.ticks.color = texto;
  state.chart.options.scales.x.grid.color = linea;
  state.chart.options.scales.y.grid.color = linea;
  state.chart.update("none");
}

function createChart() {
  if (typeof Chart === "undefined") {
    notify("No se cargó Chart.js (vendor)", true);
    return;
  }

  const { texto, linea } = coloresTema();
  const contexto = $("results-chart");

  state.chart = new Chart(contexto, {
    type: "bar",
    data: {
      labels: OPCIONES,
      datasets: [
        {
          label: "Votos",
          data: [0, 0, 0, 0],
          backgroundColor: [
            "#5b7cfa",
            "#22b07d",
            "#e9a53a",
            "#ef5b5b",
          ],
          borderRadius: 10,
          maxBarThickness: 72,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 350 },
      scales: {
        x: {
          grid: { display: false, color: linea },
          ticks: { color: texto },
        },
        y: {
          beginAtZero: true,
          grid: { color: linea },
          ticks: { precision: 0, color: texto },
        },
      },
      plugins: {
        legend: { display: false },
      },
    },
  });

  aplicarTemaGrafica();
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

  const relleno = $("participation-fill");
  if (relleno) relleno.style.width = "0%";

  const porcentajeTexto = $("participation-percent");
  if (porcentajeTexto) porcentajeTexto.textContent = "0%";

  const barra = $("participation-progress");
  if (barra) barra.setAttribute("aria-valuenow", "0");

  const roster = $("roster-chips");
  if (roster) roster.innerHTML = "";
}

function resetFinal() {
  $("final-card").classList.add("hidden");
  $("final-summary").textContent = "";
  $("final-table").innerHTML = "";
}

function showFinal(results) {
  const alumnos = results.per_student || [];
  const aciertos = alumnos.filter(
    (alumno) => alumno.correct
  ).length;

  const total = alumnos.length;

  const totalVotos = Object.values(results.counts || {}).reduce(
    (suma, cantidad) => suma + cantidad,
    0
  );

  const porcentaje = total
    ? Math.round((aciertos * 100) / total)
    : 0;

  $("total-votes").textContent = totalVotos;

  $("final-summary").textContent =
    `Aciertos: ${aciertos}/${total} (${porcentaje}%). ` +
    `Respuesta correcta: ${results.correct_option}.`;

  $("final-table").innerHTML = alumnos
    .map(
      (alumno) => `
        <tr>
          <td>${escapeHtml(alumno.name)}</td>
          <td><span class="letter">${escapeHtml(alumno.option)}</span></td>
          <td>
            <span class="tag ${alumno.correct ? "correct" : "wrong"}">
              ${alumno.correct ? "Correcto" : "Incorrecto"}
            </span>
          </td>
        </tr>`
    )
    .join("");

  $("final-card").classList.remove("hidden");
  updateChart(results.counts);
}


function selectStudentAnswer(option) {
    const angles = {
        A: 0,
        B: 90,
        C: 180,
        D: 270
    };

    if (!Object.prototype.hasOwnProperty.call(angles, option)) return;

    state.selectedAnswer = option;

    const angle = angles[option];
    const qr = $("student-qr-code");

    if (qr) {
        qr.style.transform = `rotate(${angle}deg)`;
    }

    const dial = $("rotation-dial");

    if (dial) {
        dial.style.setProperty("--angle", `${angle}deg`);
    }

    const etiqueta = $("rotation-label");

    if (etiqueta) {
        etiqueta.textContent = `QR girado ${angle}° · opción ${option}`;
    }

    document.querySelectorAll(".student-answer-button").forEach((button) => {
        const selected = button.dataset.studentOption === option;

        button.classList.toggle("selected", selected);
        button.setAttribute("aria-pressed", String(selected));

        const pista = button.querySelector("small");

        if (pista) {
            pista.textContent = selected
                ? "Respuesta seleccionada"
                : "Seleccionar respuesta";
        }
    });

    $("student-voting-status").textContent =
        `Respuesta ${option} seleccionada. Mantén tu QR quieto frente a la cámara.`;
}


function bindEvents() {

  // Seleccionar respuesta del estudiante.
  $("student-options").addEventListener("click", (event) => {
    const button = event.target.closest("[data-student-option]");

    if (!button) return;

    selectStudentAnswer(button.dataset.studentOption);
  });


  // Selección del tipo de usuario.
  $("teacher-access").addEventListener("click", () => {
    $("role-selection").classList.add("hidden");
    $("teacher-login").classList.remove("hidden");
  });

  $("student-access").addEventListener("click", () => {
    $("role-selection").classList.add("hidden");
    $("student-login").classList.remove("hidden");
  });

  // Regresar al selector de roles.
  $("back-to-roles").addEventListener("click", () => {
    $("teacher-login").classList.add("hidden");
    $("role-selection").classList.remove("hidden");
    $("login-error").textContent = "";
    $("password").value = "";
  });

  $("back-to-roles-student").addEventListener("click", () => {
    $("student-login").classList.add("hidden");
    $("role-selection").classList.remove("hidden");
    $("student-login-error").textContent = "";
    $("student-email").value = "";
    $("student-password").value = "";
  });

  // Inicio de sesión del estudiante.
 
$("student-login-form").addEventListener("submit", async (event) => {
    event.preventDefault();

    const email = $("student-email").value.trim().toLowerCase();
    const password = $("student-password").value;

    $("student-login-error").textContent = "";

    try {
        await api("/student-auth/login", {
            method: "POST",
            body: JSON.stringify({
                email: email,
                password: password
            })
        }, false);

        $("student-login-form").reset();

        await showStudentPanel();

    } catch (error) {
        $("student-login-error").textContent =
            error.message || "No fue posible iniciar sesión.";
    }
});


  // Cierre de sesión del estudiante.
  $("student-logout-button").addEventListener("click", async () => {
    try {
      await api("/student-auth/logout", {
        method: "POST",
      }, false);
    } catch (error) {
      notify(error.message, true);
    } finally {
      showLogin();
    }
  });

  // Volver a consultar el estado de la votación.
  $("student-refresh-button").addEventListener("click", async () => {
    await showStudentPanel();
    notify("Estado de la votación actualizado.");
  });

  // La gráfica debe seguir los colores del tema activo.
  document.addEventListener("tema:cambiado", aplicarTemaGrafica);

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

      await loadQuestions();
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
      notify(
        "Debes cerrar la votación antes de cambiar de pregunta.",
        true
      );

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

  // Inicio de sesión del docente.
  $("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    $("login-error").textContent = "";

    try {
      await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          password: $("password").value,
        }),
      });

      $("password").value = "";
      await showDashboard();

    } catch (error) {
      $("login-error").textContent = error.message;
    }
  });

  // Cierre de sesión del docente.
  $("logout-button").addEventListener("click", async () => {
    try {
      await api("/auth/logout", {
        method: "POST",
      });
    } finally {
      showLogin();
    }
  });

  // Crear cuenta de estudiante desde el dashboard.
$("student-form").addEventListener("submit", async (event) => {
    event.preventDefault();

    try {
        const resultado = await api("/students/accounts", {
            method: "POST",
            body: JSON.stringify({
                name: $("student-account-name").value.trim(),
                email: $("student-account-email").value.trim(),
                password: $("student-account-password").value
            })
        });

        $("student-form").reset();

        await loadStudents();

        notify(
            `Cuenta creada correctamente. ID del estudiante: ${resultado.id}`
        );

    } catch (error) {
        notify(error.message, true);
    }
});

  // Crear pregunta.
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

      await loadQuestions();

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

  // Abrir votación.
  $("open-button").addEventListener("click", async () => {
    const questionId = Number($("question-select").value);

    if (!questionId) {
      notify("Crea una pregunta antes de abrir la votación", true);
      return;
    }

    try {
      await api("/sessions", {
        method: "POST",
        body: JSON.stringify({
          question_id: questionId,
        }),
      });

      resetFinal();
      await loadActiveSession();
      notify("Votación abierta");

    } catch (error) {
      notify(error.message, true);
    }
  });

  // Cerrar votación.
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

  // Primero comprobar si existe una sesión docente.
  try {
    await api("/auth/me");
    await showDashboard();
    return;
  } catch {
    // Si no hay sesión docente, comprobar la del estudiante.
  }

  // Comprobar si existe una sesión estudiantil.
  try {
    await api("/student-auth/me", {}, false);
    await showStudentPanel();
  } catch {
    showLogin();
  }
}

document.addEventListener("DOMContentLoaded", init);