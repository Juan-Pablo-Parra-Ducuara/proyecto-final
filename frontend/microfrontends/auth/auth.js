/**
 * Microfrontend de autenticación.
 * No conoce el dashboard ni el panel del estudiante: solo avisa al shell
 * mediante el evento `auth:changed` cuando la sesión cambia.
 */

import { loadStyleOnce } from "../../shared/assets.js";
import { loginStudent, loginTeacher } from "../../shared/auth.js";
import { $, descargarHtml } from "../../shared/dom.js";

export async function mount(root) {
  loadStyleOnce("css-mfe-auth", "/microfrontends/auth/auth.css");
  root.innerHTML = await descargarHtml("/microfrontends/auth/view.html");

  const mostrarRol = () => {
    $("role-selection").classList.remove("hidden");
    $("teacher-login").classList.add("hidden");
    $("student-login").classList.add("hidden");
  };

  $("teacher-access").addEventListener("click", () => {
    $("role-selection").classList.add("hidden");
    $("teacher-login").classList.remove("hidden");
  });

  $("student-access").addEventListener("click", () => {
    $("role-selection").classList.add("hidden");
    $("student-login").classList.remove("hidden");
  });

  $("back-to-roles").addEventListener("click", () => {
    $("login-error").textContent = "";
    $("password").value = "";
    mostrarRol();
  });

  $("back-to-roles-student").addEventListener("click", () => {
    $("student-login-error").textContent = "";
    $("student-email").value = "";
    $("student-password").value = "";
    mostrarRol();
  });

  $("login-form").addEventListener("submit", async (evento) => {
    evento.preventDefault();
    $("login-error").textContent = "";

    try {
      await loginTeacher($("password").value);
      $("password").value = "";
    } catch (error) {
      $("login-error").textContent = error.message;
    }
  });

  $("student-login-form").addEventListener("submit", async (evento) => {
    evento.preventDefault();
    $("student-login-error").textContent = "";

    try {
      await loginStudent(
        $("student-email").value.trim().toLowerCase(),
        $("student-password").value,
      );
      $("student-login-form").reset();
    } catch (error) {
      $("student-login-error").textContent = error.message;
    }
  });

  return () => {
    /* El shell elimina el DOM al desmontar; no hay escuchas globales. */
  };
}
