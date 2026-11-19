/** Operaciones de autenticación compartidas por el shell y los microfrontends. */

import { api } from "./api.js";
import { emit } from "./bus.js";

export async function loginTeacher(password) {
  await api("/auth/login", {
    method: "POST",
    body: JSON.stringify({ password }),
  });

  emit("auth:changed", { rol: "teacher" });
}

/** Canjea el ticket del módulo local por la cookie del dashboard. */
export async function desktopLogin(ticket) {
  await api("/auth/desktop-login", {
    method: "POST",
    body: JSON.stringify({ ticket }),
  });

  emit("auth:changed", { rol: "teacher" });
}

export async function loginStudent(email, password) {
  await api(
    "/student-auth/login",
    {
      method: "POST",
      body: JSON.stringify({ email, password }),
    },
    false,
  );

  emit("auth:changed", { rol: "student" });
}

export async function logout(rol) {
  const ruta = rol === "teacher" ? "/auth/logout" : "/student-auth/logout";

  try {
    await api(ruta, { method: "POST" }, false);
  } finally {
    emit("auth:changed", { rol: null });
  }
}

/** Comprueba qué cookie de sesión existe al cargar la aplicación. */
export async function probeRole() {
  try {
    await api("/auth/me", {}, false);
    return "teacher";
  } catch {
    /* no hay sesión docente */
  }

  try {
    await api("/student-auth/me", {}, false);
    return "student";
  } catch {
    return null;
  }
}
