/**
 * Microfrontend de resultados finales.
 *
 * No consulta la API ni dibuja la gráfica: solo presenta el resumen y la tabla
 * cuando llega `results:final` (cierre de la sesión) o `results:history`
 * (historial publicado por el microfrontend "En vivo").
 */

import { loadStyleOnce } from "../../shared/assets.js";
import { on } from "../../shared/bus.js";
import { $, descargarHtml, escapeHtml } from "../../shared/dom.js";

let cancelaciones = [];

function resetFinal() {
  $("final-card").classList.add("hidden");
  $("final-summary").textContent = "";
  $("final-table").innerHTML = "";
}

function showFinal(resultados) {
  if (!resultados) {
    resetFinal();
    return;
  }

  const alumnos = resultados.per_student || [];
  const aciertos = alumnos.filter((alumno) => alumno.correct).length;
  const total = alumnos.length;
  const porcentaje = total ? Math.round((aciertos * 100) / total) : 0;

  $("final-summary").textContent =
    `Aciertos: ${aciertos}/${total} (${porcentaje}%). ` +
    `Respuesta correcta: ${resultados.correct_option}.`;

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
        </tr>`,
    )
    .join("");

  $("final-card").classList.remove("hidden");
}

function suscribirse() {
  cancelaciones.push(
    on("session:changed", ({ session }) => {
      if (session?.status === "open") resetFinal();
    }),

    on("results:final", (datos) => showFinal(datos)),
    on("results:history", (datos) => showFinal(datos)),
  );
}

export async function mount(root) {
  loadStyleOnce("css-mfe-results", "/microfrontends/results/results.css");
  root.innerHTML = await descargarHtml(
    "/microfrontends/results/view.html",
  );

  suscribirse();

  return () => {
    cancelaciones.forEach((cancelar) => cancelar());
    cancelaciones = [];
  };
}
