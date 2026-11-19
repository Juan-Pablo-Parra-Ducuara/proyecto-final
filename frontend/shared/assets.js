/** Cada microfrontends carga su propia hoja de estilos al montarse. */

export function loadStyleOnce(id, href) {
  if (document.getElementById(id)) return;

  const enlace = document.createElement("link");
  enlace.id = id;
  enlace.rel = "stylesheet";
  enlace.href = href;
  document.head.append(enlace);
}
