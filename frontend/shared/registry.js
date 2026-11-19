/**
 * Registro de microfrontends.
 *
 * El shell (y el dashboard, para sus microfrontends anidados) usa este
 * registro para montar y desmontar unidades desplegables de forma aislada.
 * No hay bundler: se usan importaciones dinámicas nativas del navegador.
 */

import { loadStyleOnce } from "./assets.js";

const definiciones = {
  auth: () => import("../microfrontends/auth/auth.js"),
  dashboard: () => import("../microfrontends/dashboard/dashboard.js"),
  live: () => import("../microfrontends/live/live.js"),
  results: () => import("../microfrontends/results/results.js"),
  scanner: () => import("../microfrontends/scanner/scanner.js"),
  student: () => import("../microfrontends/student/student.js"),
};

const activos = new Map();

export async function mountMicrofrontend(nombre, root) {
  if (!definiciones[nombre]) {
    throw new Error(`Microfrontend desconocido: ${nombre}`);
  }

  unmountMicrofrontend(nombre);

  const modulo = await definiciones[nombre]();
  const limpieza = await modulo.mount(root);

  activos.set(nombre, { limpieza, root });
  return limpieza;
}

export function unmountMicrofrontend(nombre) {
  const activo = activos.get(nombre);

  if (!activo) return;

  activo.limpieza?.();
  activos.delete(nombre);

  if (activo.root) activo.root.innerHTML = "";
}

export function unmountAllMicrofrontends() {
  // Los anidados se desmontan antes que el contenedor que los creó.
  const orden = [
    "results",
    "live",
    "scanner",
    "student",
    "dashboard",
    "auth",
  ];

  for (const nombre of orden) {
    unmountMicrofrontend(nombre);
  }
}
