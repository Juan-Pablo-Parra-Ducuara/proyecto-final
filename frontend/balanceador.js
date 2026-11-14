/**
 * Balanceador de cargas — simulación visual.
 *
 * Cada petición es un punto que viaja del cliente al balanceador, de ahí al
 * servidor elegido y de vuelta por el mismo camino. El algoritmo de reparto se
 * puede cambiar en caliente y los servidores se activan o desactivan con clic.
 *
 * No usa dependencias: Canvas 2D + requestAnimationFrame.
 */

(() => {
  "use strict";

  const MAX_SERVIDORES = 6;
  const MIN_SERVIDORES = 2;
  const TAU = Math.PI * 2;
  const FUENTE = '"Segoe UI", system-ui, -apple-system, sans-serif';

  const DURACIONES = {
    ida: 700,
    salida: 540,
    vuelta: 540,
    retorno: 700,
  };

  const NOMBRES_ALGORITMO = {
    "round-robin": "Round robin",
    "least-connections": "Menos conexiones",
    random: "Aleatorio",
  };

  const COLORES_RESPALDO = {
    ink: "#0f1a2c",
    muted: "#5c6b84",
    line: "#e1e8f3",
    surface: "#ffffff",
    surface2: "#f7f9fe",
    primary: "#3559d9",
    danger: "#c03434",
    srv: ["#3559d9", "#0b7a53", "#a15f00", "#c03434", "#6d3fe0", "#0e6f8a"],
  };

  const $ = (id) => document.getElementById(id);

  const estado = {
    algoritmo: "round-robin",
    tasa: 6,
    pausado: false,
    turno: 0,
    siguientePaquete: 1,
    tiempoAcumulado: 0,
    ultimoFrame: 0,
  };

  const metricas = {
    total: 0,
    completadas: 0,
    rechazadas: 0,
  };

  const servidores = [];
  const paquetes = [];
  const efectos = [];
  const nodos = new Map();

  let canvas = null;
  let ctx = null;
  let contenedor = null;
  let ancho = 0;
  let alto = 0;
  let colores = { ...COLORES_RESPALDO };
  let ultimoPintadoUI = 0;
  let ultimoEstado = 0;

  // ------------------------------------------------------------
  // Utilidades
  // ------------------------------------------------------------

  function leerToken(estilos, nombre, respaldo) {
    return estilos.getPropertyValue(nombre).trim() || respaldo;
  }

  function leerColores() {
    const estilos = getComputedStyle(document.documentElement);

    colores = {
      ink: leerToken(estilos, "--ink", COLORES_RESPALDO.ink),
      muted: leerToken(estilos, "--muted", COLORES_RESPALDO.muted),
      line: leerToken(estilos, "--line", COLORES_RESPALDO.line),
      surface: leerToken(estilos, "--surface", COLORES_RESPALDO.surface),
      surface2: leerToken(estilos, "--surface-2", COLORES_RESPALDO.surface2),
      primary: leerToken(estilos, "--primary", COLORES_RESPALDO.primary),
      danger: leerToken(estilos, "--danger", COLORES_RESPALDO.danger),
      srv: [1, 2, 3, 4, 5, 6].map((numero) =>
        leerToken(
          estilos,
          `--srv-${numero}`,
          COLORES_RESPALDO.srv[numero - 1]
        )
      ),
    };
  }

  function colorServidor(servidor) {
    return colores.srv[(servidor.id - 1) % colores.srv.length];
  }

  function rectRedondeado(x, y, anchoRect, altoRect, radio) {
    const r = Math.min(radio, anchoRect / 2, altoRect / 2);

    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + anchoRect, y, x + anchoRect, y + altoRect, r);
    ctx.arcTo(x + anchoRect, y + altoRect, x, y + altoRect, r);
    ctx.arcTo(x, y + altoRect, x, y, r);
    ctx.arcTo(x, y, x + anchoRect, y, r);
    ctx.closePath();
  }

  function texto(contenido, x, y, fuente, color) {
    ctx.font = fuente;
    ctx.fillStyle = color;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(contenido, x, y);
  }

  function anunciar(mensaje, forzar = false) {
    const ahora = performance.now();

    if (!forzar && ahora - ultimoEstado < 500) return;

    ultimoEstado = ahora;
    const salida = $("ultima-decision");

    if (salida) salida.textContent = mensaje;
  }

  // ------------------------------------------------------------
  // Servidores y algoritmos
  // ------------------------------------------------------------

  function nuevoServidor() {
    let id = 1;

    while (servidores.some((servidor) => servidor.id === id)) id += 1;

    return {
      id,
      activo: true,
      activas: 0,
      atendidas: 0,
      velocidad: 520 + id * 70,
    };
  }

  function servidoresActivos() {
    return servidores.filter((servidor) => servidor.activo);
  }

  function elegirServidor() {
    const activos = servidoresActivos();

    if (!activos.length) return null;

    if (estado.algoritmo === "random") {
      return activos[Math.floor(Math.random() * activos.length)];
    }

    if (estado.algoritmo === "least-connections") {
      return activos.reduce((mejor, servidor) => {
        if (!mejor) return servidor;
        if (servidor.activas < mejor.activas) return servidor;
        if (servidor.activas === mejor.activas && servidor.id < mejor.id) {
          return servidor;
        }
        return mejor;
      }, null);
    }

    // Round robin: avanza el turno solo entre los servidores activos.
    const indice = estado.turno % activos.length;
    estado.turno = (estado.turno + 1) % activos.length;

    return activos[indice];
  }

  function agregarServidor() {
    if (servidores.length >= MAX_SERVIDORES) return;

    const servidor = nuevoServidor();
    servidores.push(servidor);

    renderizarServidores();
    calcularNodos();
    anunciar(`Servidor ${servidor.id} añadido.`, true);
  }

  function quitarServidor() {
    if (servidores.length <= MIN_SERVIDORES) return;

    const fuera = servidores[servidores.length - 1];
    servidores.pop();

    const nodoFuera = nodos.get(`srv-${fuera.id}`);

    for (const paquete of paquetes) {
      if (paquete.servidor !== fuera) continue;

      if (paquete.fase === "salida" || paquete.fase === "procesando") {
        fuera.activas = Math.max(0, fuera.activas - 1);

        const destino = elegirServidor();

        if (destino) {
          paquete.servidor = destino;
          destino.activas += 1;
          paquete.fase = "salida";
          paquete.t = 0;
          paquete.duracion = DURACIONES.salida;
        } else {
          paquete.eliminado = true;
          metricas.rechazadas += 1;
          crearEfectoRechazo();
        }
      } else if (paquete.fase === "vuelta" && nodoFuera) {
        // El nodo ya no se dibuja: recordamos de dónde vuelve el paquete.
        paquete.origenVuelta = { x: nodoFuera.x, y: nodoFuera.y };
      }
    }

    renderizarServidores();
    calcularNodos();
    anunciar(`Servidor ${fuera.id} retirado.`, true);
  }

  function alternarServidor(id) {
    const servidor = servidores.find((item) => item.id === id);

    if (!servidor) return;

    servidor.activo = !servidor.activo;
    actualizarTarjetas();

    anunciar(
      servidor.activo
        ? `Servidor ${servidor.id} activado.`
        : `Servidor ${servidor.id} desactivado: no recibirá nuevas peticiones.`,
      true
    );
  }

  // ------------------------------------------------------------
  // Peticiones
  // ------------------------------------------------------------

  function crearPaquete() {
    metricas.total += 1;

    paquetes.push({
      id: estado.siguientePaquete,
      fase: "ida",
      t: 0,
      duracion: DURACIONES.ida,
      servidor: null,
      espera: 0,
      origenVuelta: null,
      eliminado: false,
    });

    estado.siguientePaquete += 1;
  }

  function crearEfectoRechazo() {
    const lb = nodos.get("lb");

    if (!lb) return;

    efectos.push({ x: lb.x, y: lb.y, vida: 650, total: 650 });
  }

  function avanzarPaquete(paquete, delta) {
    if (paquete.fase === "procesando") {
      paquete.espera -= delta;

      if (paquete.espera > 0) return;

      if (paquete.servidor) {
        paquete.servidor.activas = Math.max(0, paquete.servidor.activas - 1);
        paquete.servidor.atendidas += 1;
      }

      paquete.fase = "vuelta";
      paquete.t = 0;
      paquete.duracion = DURACIONES.vuelta;
      return;
    }

    paquete.t += delta / paquete.duracion;

    if (paquete.t < 1) return;

    paquete.t = 0;

    if (paquete.fase === "ida") {
      const servidor = elegirServidor();

      if (!servidor) {
        paquete.eliminado = true;
        metricas.rechazadas += 1;
        crearEfectoRechazo();
        anunciar("Sin servidores activos: la petición se rechaza.");
        return;
      }

      paquete.servidor = servidor;
      servidor.activas += 1;
      paquete.fase = "salida";
      paquete.duracion = DURACIONES.salida;

      anunciar(
        `Petición #${paquete.id} → Servidor ${servidor.id} · ` +
          NOMBRES_ALGORITMO[estado.algoritmo]
      );
    } else if (paquete.fase === "salida") {
      paquete.fase = "procesando";
      paquete.espera = paquete.servidor ? paquete.servidor.velocidad : 700;
    } else if (paquete.fase === "vuelta") {
      paquete.fase = "retorno";
      paquete.duracion = DURACIONES.retorno;
    } else if (paquete.fase === "retorno") {
      paquete.eliminado = true;
      metricas.completadas += 1;
    }
  }

  function posicionPaquete(paquete) {
    const cliente = nodos.get("cliente");
    const lb = nodos.get("lb");

    if (!cliente || !lb) return null;

    if (paquete.fase === "ida") {
      return interpolar(cliente, lb, paquete.t);
    }

    if (paquete.fase === "retorno") {
      return interpolar(lb, cliente, paquete.t);
    }

    const nodo = paquete.servidor
      ? nodos.get(`srv-${paquete.servidor.id}`)
      : null;

    if (paquete.fase === "salida") {
      if (!nodo) return interpolar(lb, cliente, 0);
      return curva(lb, nodo, controlServidor(nodo), paquete.t);
    }

    if (paquete.fase === "procesando") {
      if (!nodo) return { ...lb };

      // Reparte los puntos alrededor del servidor para no amontonarlos.
      const angulo = (paquete.id * 2.39996) % TAU;
      const radio = radioServidor() + 8;

      return {
        x: nodo.x + Math.cos(angulo) * radio,
        y: nodo.y + Math.sin(angulo) * radio,
      };
    }

    if (paquete.fase === "vuelta") {
      const origen = paquete.origenVuelta || nodo;

      if (!origen) return { ...lb };

      return curva(origen, lb, controlServidor(origen), paquete.t);
    }

    return null;
  }

  function interpolar(desde, hasta, t) {
    return {
      x: desde.x + (hasta.x - desde.x) * t,
      y: desde.y + (hasta.y - desde.y) * t,
    };
  }

  function controlServidor(nodo) {
    const lb = nodos.get("lb");
    const dx = nodo.x - lb.x;
    const dy = nodo.y - lb.y;
    const signo = dy === 0 ? 0 : Math.sign(dy);

    return {
      x: lb.x + dx * 0.5,
      y: lb.y + dy * 0.5 + signo * Math.min(18, Math.abs(dy) * 0.18),
    };
  }

  function curva(desde, hasta, control, t) {
    const u = 1 - t;

    return {
      x: u * u * desde.x + 2 * u * t * control.x + t * t * hasta.x,
      y: u * u * desde.y + 2 * u * t * control.y + t * t * hasta.y,
    };
  }

  // ------------------------------------------------------------
  // Lienzo
  // ------------------------------------------------------------

  function ajustarCanvas() {
    if (!canvas || !contenedor) return;

    const rect = contenedor.getBoundingClientRect();

    if (!rect.width || !rect.height) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    ancho = rect.width;
    alto = rect.height;

    canvas.width = Math.round(ancho * dpr);
    canvas.height = Math.round(alto * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    calcularNodos();
    dibujar();
  }

  function calcularNodos() {
    nodos.clear();

    const centroY = alto / 2;

    nodos.set("cliente", {
      x: Math.max(36, ancho * 0.1),
      y: centroY,
    });

    nodos.set("lb", {
      x: Math.max(132, ancho * 0.44),
      y: centroY,
    });

    const total = servidores.length;
    const xServidor = ancho - Math.max(42, ancho * 0.09);
    const margen = Math.min(64, Math.max(42, alto / (total + 1)));

    servidores.forEach((servidor, indice) => {
      const y =
        total === 1
          ? centroY
          : margen + (indice * (alto - 2 * margen)) / (total - 1);

      nodos.set(`srv-${servidor.id}`, { x: xServidor, y });
    });
  }

  function radioServidor() {
    const total = Math.max(1, servidores.length);

    if (total === 1) return 18;

    const margen = Math.min(64, Math.max(42, alto / (total + 1)));
    const separacion = (alto - 2 * margen) / (total - 1);

    return Math.max(12, Math.min(19, separacion * 0.4));
  }

  function dibujar() {
    if (!ctx) return;

    ctx.clearRect(0, 0, ancho, alto);

    dibujarConexiones();
    dibujarNodos();
    dibujarPaquetes();
    dibujarEfectos();
  }

  function dibujarConexiones() {
    const cliente = nodos.get("cliente");
    const lb = nodos.get("lb");

    if (!cliente || !lb) return;

    ctx.save();
    ctx.lineCap = "round";

    ctx.strokeStyle = colores.line;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(cliente.x, cliente.y);
    ctx.lineTo(lb.x, lb.y);
    ctx.stroke();

    servidores.forEach((servidor) => {
      const nodo = nodos.get(`srv-${servidor.id}`);

      if (!nodo) return;

      const control = controlServidor(nodo);

      ctx.globalAlpha = servidor.activo ? 0.4 : 0.55;
      ctx.strokeStyle = servidor.activo
        ? colorServidor(servidor)
        : colores.line;
      ctx.lineWidth = 2;
      ctx.setLineDash(servidor.activo ? [] : [5, 6]);

      ctx.beginPath();
      ctx.moveTo(lb.x, lb.y);
      ctx.quadraticCurveTo(control.x, control.y, nodo.x, nodo.y);
      ctx.stroke();
    });

    ctx.restore();
  }

  function dibujarNodos() {
    dibujarCliente();
    dibujarBalanceador();

    servidores.forEach((servidor) => {
      const nodo = nodos.get(`srv-${servidor.id}`);

      if (!nodo) return;

      const radio = radioServidor();
      const color = colorServidor(servidor);

      ctx.save();
      ctx.beginPath();
      ctx.arc(nodo.x, nodo.y, radio, 0, TAU);
      ctx.fillStyle = colores.surface;
      ctx.fill();

      ctx.strokeStyle = servidor.activo ? color : colores.muted;
      ctx.lineWidth = 2.5;
      ctx.setLineDash(servidor.activo ? [] : [4, 4]);
      ctx.stroke();
      ctx.setLineDash([]);

      texto(
        `S${servidor.id}`,
        nodo.x,
        nodo.y,
        `800 ${Math.round(radio * 0.66)}px ${FUENTE}`,
        colores.ink
      );
      ctx.restore();
    });
  }

  function dibujarCliente() {
    const nodo = nodos.get("cliente");

    if (!nodo) return;

    ctx.save();

    rectRedondeado(nodo.x - 27, nodo.y - 23, 54, 42, 11);
    ctx.fillStyle = colores.surface;
    ctx.fill();
    ctx.strokeStyle = colores.line;
    ctx.lineWidth = 2;
    ctx.stroke();

    // Pantalla.
    rectRedondeado(nodo.x - 19, nodo.y - 15, 38, 25, 4);
    ctx.globalAlpha = 0.16;
    ctx.fillStyle = colores.primary;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.strokeStyle = colores.primary;
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Soporte.
    ctx.strokeStyle = colores.muted;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(nodo.x - 8, nodo.y + 19);
    ctx.lineTo(nodo.x + 8, nodo.y + 19);
    ctx.moveTo(nodo.x, nodo.y + 19);
    ctx.lineTo(nodo.x, nodo.y + 23);
    ctx.stroke();

    texto(
      "Cliente",
      nodo.x,
      nodo.y + 40,
      `700 11px ${FUENTE}`,
      colores.ink
    );

    ctx.restore();
  }

  function dibujarBalanceador() {
    const nodo = nodos.get("lb");

    if (!nodo) return;

    ctx.save();

    rectRedondeado(nodo.x - 39, nodo.y - 26, 78, 52, 14);
    ctx.globalAlpha = 0.14;
    ctx.fillStyle = colores.primary;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.strokeStyle = colores.primary;
    ctx.lineWidth = 2.5;
    ctx.stroke();

    texto("LB", nodo.x, nodo.y - 3, `800 16px ${FUENTE}`, colores.primary);
    texto(
      "Balanceador",
      nodo.x,
      nodo.y + 40,
      `600 10.5px ${FUENTE}`,
      colores.muted
    );

    ctx.restore();
  }

  function dibujarPaquetes() {
    paquetes.forEach((paquete) => {
      const posicion = posicionPaquete(paquete);

      if (!posicion) return;

      const color = paquete.servidor
        ? colorServidor(paquete.servidor)
        : colores.primary;

      ctx.save();
      ctx.beginPath();
      ctx.arc(posicion.x, posicion.y, 5.2, 0, TAU);
      ctx.fillStyle = color;
      ctx.shadowColor = color;
      ctx.shadowBlur = 8;
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.strokeStyle = colores.surface;
      ctx.lineWidth = 1.4;
      ctx.stroke();
      ctx.restore();
    });
  }

  function dibujarEfectos() {
    for (let indice = efectos.length - 1; indice >= 0; indice -= 1) {
      const efecto = efectos[indice];
      const avance = 1 - efecto.vida / efecto.total;
      const radio = 10 + avance * 28;

      ctx.save();
      ctx.globalAlpha = Math.max(0, 1 - avance);
      ctx.strokeStyle = colores.danger;
      ctx.lineWidth = 2.5;

      ctx.beginPath();
      ctx.arc(efecto.x, efecto.y, radio, 0, TAU);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(efecto.x - 6, efecto.y - 6);
      ctx.lineTo(efecto.x + 6, efecto.y + 6);
      ctx.moveTo(efecto.x + 6, efecto.y - 6);
      ctx.lineTo(efecto.x - 6, efecto.y + 6);
      ctx.stroke();

      ctx.restore();
    }
  }

  // ------------------------------------------------------------
  // Interfaz
  // ------------------------------------------------------------

  function renderizarServidores() {
    const contenedorServidores = $("servidores");

    if (!contenedorServidores) return;

    contenedorServidores.innerHTML = servidores
      .map(
        (servidor) => `
        <button
          type="button"
          class="servidor tono-${servidor.id}"
          data-servidor="${servidor.id}"
          aria-pressed="${servidor.activo}"
          title="Activar o desactivar el servidor ${servidor.id}"
        >
          <span class="servidor-cabecera">
            <span class="servidor-punto" aria-hidden="true"></span>
            <span class="servidor-nombre">Servidor ${servidor.id}</span>
            <span class="servidor-estado">${servidor.activo ? "Activo" : "Inactivo"}</span>
          </span>

          <span class="servidor-datos">
            <span class="servidor-dato">
              <strong>0</strong>
              <small>activas</small>
            </span>
            <span class="servidor-dato">
              <strong>0</strong>
              <small>atendidas</small>
            </span>
          </span>

          <span class="servidor-barra" aria-hidden="true">
            <span class="servidor-barra-fill"></span>
          </span>
        </button>
      `
      )
      .join("");

    actualizarTarjetas();
    actualizarBotonesLimite();
  }

  function actualizarTarjetas() {
    const contenedorServidores = $("servidores");

    if (!contenedorServidores) return;

    const mayorCarga = Math.max(
      1,
      ...servidores.map((servidor) => servidor.activas)
    );

    contenedorServidores.querySelectorAll(".servidor").forEach((tarjeta) => {
      const id = Number(tarjeta.dataset.servidor);
      const servidor = servidores.find((item) => item.id === id);

      if (!servidor) return;

      tarjeta.classList.toggle("inactivo", !servidor.activo);
      tarjeta.setAttribute("aria-pressed", String(servidor.activo));

      const estadoTexto = tarjeta.querySelector(".servidor-estado");

      if (estadoTexto) {
        estadoTexto.textContent = servidor.activo ? "Activo" : "Inactivo";
      }

      const datos = tarjeta.querySelectorAll(".servidor-dato strong");

      if (datos[0]) datos[0].textContent = servidor.activas;
      if (datos[1]) datos[1].textContent = servidor.atendidas;

      const barra = tarjeta.querySelector(".servidor-barra-fill");

      if (barra) {
        const carga = Math.min(100, (servidor.activas / mayorCarga) * 100);
        barra.style.width = `${carga}%`;
      }
    });
  }

  function actualizarBotonesLimite() {
    const agregar = $("agregar-servidor");
    const quitar = $("quitar-servidor");

    if (agregar) agregar.disabled = servidores.length >= MAX_SERVIDORES;
    if (quitar) quitar.disabled = servidores.length <= MIN_SERVIDORES;
  }

  function actualizarUI() {
    const total = $("kpi-total");
    const activas = $("kpi-activas");
    const completadas = $("kpi-completadas");
    const rechazadas = $("kpi-rechazadas");

    if (total) total.textContent = metricas.total;
    if (activas) activas.textContent = paquetes.length;
    if (completadas) completadas.textContent = metricas.completadas;
    if (rechazadas) rechazadas.textContent = metricas.rechazadas;

    actualizarTarjetas();
  }

  function pintarTasa() {
    const control = $("tasa");
    const salida = $("tasa-valor");

    if (!control) return;

    const minimo = Number(control.min) || 1;
    const maximo = Number(control.max) || 20;
    const porcentaje =
      ((estado.tasa - minimo) / Math.max(1, maximo - minimo)) * 100;

    control.style.setProperty("--pct", `${Math.round(porcentaje)}%`);

    if (salida) salida.textContent = estado.tasa;
  }

  function alternarPausa() {
    estado.pausado = !estado.pausado;

    const badge = $("sim-status");
    const boton = $("iniciar");

    if (badge) {
      badge.textContent = estado.pausado ? "Pausado" : "En marcha";
      badge.className = `badge ${estado.pausado ? "neutral" : "online"}`;
    }

    if (boton) boton.textContent = estado.pausado ? "Reanudar" : "Pausar";

    anunciar(
      estado.pausado ? "Simulación en pausa." : "Simulación reanudada.",
      true
    );
  }

  function reiniciar() {
    paquetes.length = 0;
    efectos.length = 0;
    metricas.total = 0;
    metricas.completadas = 0;
    metricas.rechazadas = 0;
    estado.turno = 0;
    estado.siguientePaquete = 1;
    estado.tiempoAcumulado = 0;

    servidores.forEach((servidor) => {
      servidor.activas = 0;
      servidor.atendidas = 0;
    });

    actualizarUI();
    anunciar("Simulación reiniciada.", true);
  }

  function conectarControles() {
    const algoritmo = $("algoritmo");
    const tasa = $("tasa");
    const iniciar = $("iniciar");
    const reiniciarBoton = $("reiniciar");
    const agregar = $("agregar-servidor");
    const quitar = $("quitar-servidor");
    const listaServidores = $("servidores");

    if (algoritmo) {
      estado.algoritmo = algoritmo.value;

      algoritmo.addEventListener("change", () => {
        estado.algoritmo = algoritmo.value;
        estado.turno = 0;
        anunciar(`Algoritmo: ${NOMBRES_ALGORITMO[estado.algoritmo]}.`, true);
      });
    }

    if (tasa) {
      estado.tasa = Number(tasa.value) || 1;

      tasa.addEventListener("input", () => {
        estado.tasa = Number(tasa.value) || 1;
        pintarTasa();
      });
    }

    if (iniciar) iniciar.addEventListener("click", alternarPausa);
    if (reiniciarBoton) reiniciarBoton.addEventListener("click", reiniciar);
    if (agregar) agregar.addEventListener("click", agregarServidor);
    if (quitar) quitar.addEventListener("click", quitarServidor);

    if (listaServidores) {
      listaServidores.addEventListener("click", (evento) => {
        const tarjeta = evento.target.closest("[data-servidor]");

        if (!tarjeta) return;

        alternarServidor(Number(tarjeta.dataset.servidor));
      });
    }
  }

  // ------------------------------------------------------------
  // Bucle principal
  // ------------------------------------------------------------

  function bucle(ahora) {
    const delta = estado.ultimoFrame
      ? Math.min(50, ahora - estado.ultimoFrame)
      : 0;

    estado.ultimoFrame = ahora;

    if (!estado.pausado) {
      estado.tiempoAcumulado += delta;

      const intervalo = 1000 / Math.max(1, estado.tasa);

      while (estado.tiempoAcumulado >= intervalo) {
        estado.tiempoAcumulado -= intervalo;
        crearPaquete();
      }

      for (const paquete of paquetes) {
        if (!paquete.eliminado) avanzarPaquete(paquete, delta);
      }

      for (let indice = paquetes.length - 1; indice >= 0; indice -= 1) {
        if (paquetes[indice].eliminado) paquetes.splice(indice, 1);
      }

      for (let indice = efectos.length - 1; indice >= 0; indice -= 1) {
        efectos[indice].vida -= delta;

        if (efectos[indice].vida <= 0) efectos.splice(indice, 1);
      }
    }

    if (ahora - ultimoPintadoUI > 200) {
      ultimoPintadoUI = ahora;
      actualizarUI();
    }

    dibujar();
    requestAnimationFrame(bucle);
  }

  // ------------------------------------------------------------
  // Arranque
  // ------------------------------------------------------------

  function iniciar() {
    canvas = $("balanceador-canvas");
    contenedor = canvas ? canvas.parentElement : null;

    if (!canvas || !contenedor) return;

    ctx = canvas.getContext("2d");

    if (!ctx) return;

    leerColores();

    for (let indice = 0; indice < 3; indice += 1) {
      servidores.push(nuevoServidor());
    }

    renderizarServidores();
    conectarControles();
    pintarTasa();

    ajustarCanvas();

    if (typeof ResizeObserver !== "undefined") {
      new ResizeObserver(() => ajustarCanvas()).observe(contenedor);
    }

    window.addEventListener("resize", ajustarCanvas);

    document.addEventListener("tema:cambiado", () => {
      leerColores();
      dibujar();
    });

    anunciar("Simulación lista: 3 servidores activos.", true);

    requestAnimationFrame(bucle);
  }

  // API mínima para pruebas y para depurar desde la consola.
  window.BalanceadorSim = {
    estado,
    servidores,
    paquetes,
    metricas,
    reiniciar,
    alternarPausa,
    agregarServidor,
    quitarServidor,
    alternarServidor,
    elegirServidor,
    leerColores,
    ajustarCanvas,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }
})();
