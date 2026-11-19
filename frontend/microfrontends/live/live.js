/**
 * Microfrontend "En vivo".
 *
 * Es dueño exclusivo de los KPIs, la participación y la gráfica Chart.js.
 * Escucha el bus y, cuando no hay sesión abierta, recupera el historial de la
 * pregunta seleccionada y lo publica como `results:history` para que el
 * microfrontend de resultados finales muestre la tabla.
 */

import { api } from "../../shared/api.js";
import { loadStyleOnce } from "../../shared/assets.js";
import { emit, on } from "../../shared/bus.js";
import { OPCIONES } from "../../shared/constants.js";
import { $, descargarHtml, escapeHtml, notify } from "../../shared/dom.js";
import { store } from "../../shared/store.js";

let cancelaciones = [];
let chart = null;
let ultimoRoster = [];
let ultimosFaltan = [];

function nombreAlumno(arucoId) {
  const alumno = store.students.find(
    (estudiante) => String(estudiante.aruco_id) === String(arucoId),
  );

  return alumno ? alumno.name : `Estudiante #${arucoId}`;
}

function updateMissing(roster, missing) {
  const ids = (roster || []).map(String);
  const faltan = (missing || []).map(String);

  ultimoRoster = ids;
  ultimosFaltan = faltan;

  const total = ids.length;
  const votaron = Math.max(0, total - faltan.length);
  const porcentaje = total ? Math.round((votaron * 100) / total) : 0;

  $("missing-count").textContent = faltan.length;

  const relleno = $("participation-fill");
  if (relleno) relleno.style.width = `${porcentaje}%`;

  const texto = $("participation-percent");
  if (texto) texto.textContent = `${porcentaje}%`;

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

function coloresTema() {
  const estilos = getComputedStyle(document.documentElement);

  return {
    texto: estilos.getPropertyValue("--muted").trim() || "#6b7a94",
    linea: estilos.getPropertyValue("--line").trim() || "#e1e8f3",
  };
}

function aplicarTemaGrafica() {
  if (!chart) return;

  const { texto, linea } = coloresTema();

  chart.options.scales.x.ticks.color = texto;
  chart.options.scales.y.ticks.color = texto;
  chart.options.scales.x.grid.color = linea;
  chart.options.scales.y.grid.color = linea;
  chart.update("none");
}

function createChart() {
  if (typeof window.Chart === "undefined") {
    notify("No se cargó Chart.js (vendor)", true);
    return;
  }

  const { texto, linea } = coloresTema();

  chart = new window.Chart($("results-chart"), {
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
  if (!chart || !counts) return;

  chart.data.datasets[0].data = OPCIONES.map(
    (letra) => counts[letra] || 0,
  );
  chart.update();
}

function resetChart() {
  updateChart({ A: 0, B: 0, C: 0, D: 0 });
  $("total-votes").textContent = "0";
  updateMissing([], []);
}

function totalDe(counts) {
  return Object.values(counts || {}).reduce(
    (suma, cantidad) => suma + cantidad,
    0,
  );
}

async function cargarHistorial(questionId) {
  if (!questionId) {
    resetChart();
    emit("results:history", null);
    return;
  }

  if (store.session && store.session.status === "open") return;

  resetChart();

  try {
    const resultados = await api(
      `/questions/${questionId}/results/latest`,
    );

    updateChart(resultados.counts);
    $("total-votes").textContent = totalDe(resultados.counts);
    emit("results:history", resultados);
  } catch (error) {
    emit("results:history", null);

    if (!error.message.includes("todavía no tiene resultados")) {
      notify(error.message, true);
    }
  }
}

function aplicarSesion(detalle) {
  const sesion = detalle?.session || null;

  if (!sesion || sesion.status !== "open") return;

  resetChart();
  updateMissing(sesion.roster || [], detalle?.missing || []);

  if (detalle?.counts) {
    updateChart(detalle.counts);
    $("total-votes").textContent =
      detalle.total ?? totalDe(detalle.counts);
  }
}

function suscribirse() {
  const alCambiarTema = () => aplicarTemaGrafica();
  document.addEventListener("tema:cambiado", alCambiarTema);

  cancelaciones.push(
    () => document.removeEventListener("tema:cambiado", alCambiarTema),

    on("session:changed", aplicarSesion),

    on("students:changed", () =>
      updateMissing(ultimoRoster, ultimosFaltan),
    ),

    on("tally:update", (datos) => {
      if (
        store.session &&
        Number(datos.session_id) !== Number(store.session.id)
      ) {
        return;
      }

      updateChart(datos.counts);
      $("total-votes").textContent = datos.total;
      updateMissing(store.session?.roster || [], datos.missing || []);
    }),

    on("results:final", (datos) => {
      updateChart(datos.counts);
      $("total-votes").textContent = totalDe(datos.counts);
    }),

    on("question:selected", ({ questionId }) =>
      cargarHistorial(questionId),
    ),
  );
}

export async function mount(root) {
  loadStyleOnce("css-mfe-live", "/microfrontends/live/live.css");
  root.innerHTML = await descargarHtml("/microfrontends/live/view.html");

  createChart();
  suscribirse();

  return () => {
    cancelaciones.forEach((cancelar) => cancelar());
    cancelaciones = [];
    chart?.destroy();
    chart = null;
    ultimoRoster = [];
    ultimosFaltan = [];
  };
}
