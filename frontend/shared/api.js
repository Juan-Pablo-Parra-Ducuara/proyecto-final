/** Cliente HTTP compartido: añade credenciales y traduce los errores. */

import { emit } from "./bus.js";

export async function api(ruta, opciones = {}, manejarNoAutorizado = true) {
  const respuesta = await fetch(ruta, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(opciones.headers || {}),
    },
    ...opciones,
  });

  if (respuesta.status === 401 && manejarNoAutorizado) {
    emit("auth:unauthorized", { ruta });
    throw new Error("No autorizado");
  }

  if (!respuesta.ok) {
    let detalle = `Error ${respuesta.status}`;

    try {
      const datos = await respuesta.json();

      if (datos.detail) {
        if (Array.isArray(datos.detail)) {
          detalle = datos.detail
            .map((item) => {
              const campo = item.loc?.slice(1).join(".") || "dato";
              return `${campo}: ${item.msg || "Dato inválido"}`;
            })
            .join(" | ");
        } else if (typeof datos.detail === "object") {
          detalle = datos.detail.message || JSON.stringify(datos.detail);
        } else {
          detalle = datos.detail;
        }
      }
    } catch {
      /* respuesta sin cuerpo JSON */
    }

    throw new Error(detalle);
  }

  if (respuesta.status === 204) return null;
  return respuesta.json();
}
