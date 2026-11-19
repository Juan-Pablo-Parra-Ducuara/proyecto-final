/**
 * Socket.IO compartido.
 *
 * El shell decide qué rol abre la conexión (dashboard o estudiante) y este
 * módulo publica todos los eventos del servidor en el bus de la aplicación.
 * Así los microfrontends solo escuchan, sin duplicar conexiones.
 */

import { emit } from "./bus.js";

const EVENTOS_SERVIDOR = [
  "state:sync",
  "vote:open",
  "vote:close",
  "tally:update",
  "vote:accepted",
  "vote:rejected",
  "results:final",
];

let socket = null;
let rolActual = null;

export function getSocket() {
  return socket;
}

export function getRolSocket() {
  return rolActual;
}

export function connectSocket(rol) {
  if (socket && rolActual === rol) return socket;

  disconnectSocket();

  if (typeof window.io !== "function") {
    console.error("No se cargó el cliente Socket.IO de frontend/vendor");
    return null;
  }

  rolActual = rol;
  socket = window.io({ withCredentials: true });

  socket.on("connect", () => emit("socket:connect", { rol }));
  socket.on("disconnect", () => emit("socket:disconnect", { rol }));
  socket.on("connect_error", (error) =>
    emit("socket:error", { rol, error }),
  );

  for (const evento of EVENTOS_SERVIDOR) {
    socket.on(evento, (datos) => emit(evento, datos));
  }

  return socket;
}

export function disconnectSocket() {
  if (socket) {
    socket.removeAllListeners();
    socket.disconnect();
  }

  socket = null;
  rolActual = null;
}

export function emitSocket(evento, payload) {
  if (!socket?.connected) return false;

  socket.emit(evento, payload);
  return true;
}
