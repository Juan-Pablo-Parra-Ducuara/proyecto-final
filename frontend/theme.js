/* Tema claro/oscuro persistente para el dashboard y el panel del estudiante.
   Se carga antes que el CSS para evitar el destello del tema por defecto. */

(function () {
  const CLAVE = "clicker-tema";
  const raiz = document.documentElement;
  const preferencia = window.matchMedia("(prefers-color-scheme: dark)");

  function leerTemaGuardado() {
    try {
      return localStorage.getItem(CLAVE);
    } catch {
      return null;
    }
  }

  function guardarTema(tema) {
    try {
      localStorage.setItem(CLAVE, tema);
    } catch {
      /* almacenamiento no disponible: el tema solo dura la sesión */
    }
  }

  function sincronizarBotones(tema) {
    const esOscuro = tema === "dark";

    document.querySelectorAll("[data-theme-toggle]").forEach((boton) => {
      boton.setAttribute("aria-pressed", String(esOscuro));
      boton.title = esOscuro
        ? "Cambiar a tema claro"
        : "Cambiar a tema oscuro";
    });
  }

  function aplicarTema(tema, persistir = false) {
    const definitivo = tema === "dark" ? "dark" : "light";

    raiz.dataset.theme = definitivo;
    raiz.style.colorScheme = definitivo;

    if (persistir) guardarTema(definitivo);

    sincronizarBotones(definitivo);

    document.dispatchEvent(
      new CustomEvent("tema:cambiado", { detail: { tema: definitivo } })
    );
  }

  function temaInicial() {
    return leerTemaGuardado() || (preferencia.matches ? "dark" : "light");
  }

  // Aplica el tema cuanto antes, antes de que se pinte el body.
  aplicarTema(temaInicial());

  document.addEventListener("DOMContentLoaded", () => {
    aplicarTema(raiz.dataset.theme);

    document.querySelectorAll("[data-theme-toggle]").forEach((boton) => {
      boton.addEventListener("click", () => {
        aplicarTema(
          raiz.dataset.theme === "dark" ? "light" : "dark",
          true
        );
      });
    });
  });

  // Si el usuario no ha elegido tema, sigue la preferencia del sistema.
  preferencia.addEventListener("change", (evento) => {
    if (!leerTemaGuardado()) {
      aplicarTema(evento.matches ? "dark" : "light");
    }
  });

  // Expone el estado actual por si otro script lo necesita.
  window.temaActual = () => raiz.dataset.theme;
})();
