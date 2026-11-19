/** Utilidades de DOM y notificaciones compartidas por los microfrontends. */

let temporizadorToast = null;

export const $ = (id) => document.getElementById(id);

export function escapeHtml(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (caracter) => {
    const mapa = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return mapa[caracter];
  });
}

export function notify(mensaje, esError = false) {
  const toast = $("toast");

  if (!toast) return;

  toast.textContent = mensaje;
  toast.classList.toggle("error", esError);
  toast.classList.remove("hidden");

  clearTimeout(temporizadorToast);
  temporizadorToast = setTimeout(
    () => toast.classList.add("hidden"),
    3500,
  );
}

export function descargarHtml(url) {
  return fetch(url).then((respuesta) => {
    if (!respuesta.ok) {
      throw new Error(`No se pudo cargar la vista ${url}`);
    }
    return respuesta.text();
  });
}
