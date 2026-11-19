/**
 * Bus de eventos del shell.
 *
 * Permite que los microfrontends se comuniquen sin conocerse entre sí.
 * Cada suscripción devuelve una función para darse de baja al desmontarse.
 */

const destino = new EventTarget();

export function on(tipo, manejador) {
  const escucha = (evento) => manejador(evento.detail);

  destino.addEventListener(tipo, escucha);

  return () => destino.removeEventListener(tipo, escucha);
}

export function emit(tipo, detalle) {
  destino.dispatchEvent(new CustomEvent(tipo, { detail: detalle }));
}
