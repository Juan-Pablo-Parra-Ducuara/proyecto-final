/**
 * Shell (host) de los microfrontends.
 *
 * Es el único dueño del ciclo de vida de la aplicación: decide qué
 * microfrontend se monta según la sesión, limpia el estado al cambiar de rol
 * y mantiene una sola conexión Socket.IO compartida.
 */

import { desktopLogin, probeRole } from "./shared/auth.js";
import { on } from "./shared/bus.js";
import { $ } from "./shared/dom.js";
import {
  mountMicrofrontend,
  unmountAllMicrofrontends,
} from "./shared/registry.js";
import { disconnectSocket } from "./shared/socket.js";
import { resetStore } from "./shared/store.js";

const MICROFRONTEND_POR_ROL = {
  teacher: "dashboard",
  student: "student",
  null: "auth",
};

let rutaActual = null;

function microfrontendParaRol(rol) {
  return MICROFRONTEND_POR_ROL[rol ?? "null"] || "auth";
}

async function navegar(destino, { reemplazar = false } = {}) {
  if (destino === rutaActual) return;

  unmountAllMicrofrontends();
  disconnectSocket();
  resetStore();

  rutaActual = destino;
  history[reemplazar ? "replaceState" : "pushState"](
    { ruta: destino },
    "",
    `#/${destino}`,
  );

  await mountMicrofrontend(destino, $("app"));
}

on("auth:changed", ({ rol }) => navegar(microfrontendParaRol(rol)));
on("auth:unauthorized", () => navegar("auth"));

// El historial se resuelve contra la cookie real, no contra la URL.
window.addEventListener("popstate", async () => {
  await navegar(microfrontendParaRol(await probeRole()), {
    reemplazar: true,
  });
});

/** El módulo local abre el dashboard con un ticket de inicio de sesión. */
async function consumirTicketDeEscritorio() {
  const parametros = new URLSearchParams(window.location.search);
  const ticket = parametros.get("desktop_ticket");

  if (!ticket) return;

  parametros.delete("desktop_ticket");
  const consulta = parametros.toString();
  const urlLimpia =
    window.location.pathname +
    (consulta ? `?${consulta}` : "") +
    window.location.hash;

  history.replaceState(history.state, "", urlLimpia);

  try {
    await desktopLogin(ticket);
  } catch (error) {
    console.error("No se pudo iniciar sesión desde el módulo local:", error);
  }
}

async function init() {
  await consumirTicketDeEscritorio();

  await navegar(microfrontendParaRol(await probeRole()), {
    reemplazar: true,
  });
}

document.addEventListener("DOMContentLoaded", init);
