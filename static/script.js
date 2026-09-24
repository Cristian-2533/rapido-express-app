const API_URL = window.location.origin;
const usuario = JSON.parse(sessionStorage.getItem("usuario") || "null");
const token = sessionStorage.getItem("token") || "";

function headers() {
    const base = { "Content-Type": "application/json" };
    if (token) base.Authorization = "Bearer " + token;
    return base;
}
function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[char]);
}
function dinero(value) {
    return Number(value || 0).toLocaleString("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });
}
function extraerMensajeError(data) {
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
        return data.detail.map((item) => item.msg || String(item)).join(" ");
    }
    if (typeof data.error === "string") return data.error;
    return "La operación no pudo completarse.";
}
async function api(path, options = {}) {
    const response = await fetch(`${API_URL}${path}`, { ...options, headers: { ...headers(), ...(options.headers || {}) } });
    const texto = await response.text();
    let data = {};
    if (texto) {
        try { data = JSON.parse(texto); }
        catch { throw new Error(`Respuesta no válida del servidor (HTTP ${response.status}).`); }
    }
    if (!response.ok) throw new Error(extraerMensajeError(data));
    return data;
}
function cerrarSesion() {
    sessionStorage.removeItem("usuario");
    sessionStorage.removeItem("token");
    window.location.href = "login.html";
}
function protegerVista(rol) {
    if (!usuario || !token || usuario.rol !== rol) {
        window.location.replace("login.html");
        return false;
    }

    const nombreUsuario = document.getElementById("nombreUsuario");

    if (nombreUsuario && !nombreUsuario.dataset.inicializado) {
        nombreUsuario.textContent = ` ${usuario.nombre}`;
        nombreUsuario.dataset.inicializado = "true";
    }

    const btnLogout = document.getElementById("btnLogout");

    if (btnLogout && !btnLogout.dataset.inicializado) {
        btnLogout.dataset.inicializado = "true";

        btnLogout.addEventListener("click", (event) => {
            event.preventDefault();
            cerrarSesion();
        });
    }

    return true;
}
function badgeClaseEstado(estado) {
    return { "Pendiente": "badge-pendiente", "Asignado": "badge-asignado", "En camino": "badge-en-camino",
        "Entregado": "badge-entregado", "Cancelado": "badge-cancelado" }[estado] || "";
}
function abrirModal(titulo, html) {
    document.getElementById("modalTitulo").textContent = titulo;
    document.getElementById("modalCuerpo").innerHTML = html;
    document.getElementById("modalOverlay").classList.remove("hidden");
}
function cerrarModal() {
    document.getElementById("modalOverlay").classList.add("hidden");
    document.getElementById("modalCuerpo").innerHTML = "";
}
function confirmarAccion(mensaje) {
    return new Promise((resolve) => {
        abrirModal("Confirmar acción", `
            <p style="margin-bottom:1.25rem; color: var(--ink-700);">${escapeHtml(mensaje)}</p>
            <div class="order-actions">
                <button type="button" class="btn-action btn-toggle-off" id="btnConfirmarNo">Cancelar</button>
                <button type="button" class="btn-action btn-cancelar" id="btnConfirmarSi">Sí, continuar</button>
            </div>
        `);
        document.getElementById("btnConfirmarSi").addEventListener("click", () => { cerrarModal(); resolve(true); });
        document.getElementById("btnConfirmarNo").addEventListener("click", () => { cerrarModal(); resolve(false); });
    });
}
function notificar(titulo, mensaje) {
    if ("Notification" in window && Notification.permission === "granted") {
        new Notification(titulo, { body: mensaje, icon: "icons/icon-192.png" });
    } else {
        mostrarToast(`${titulo} — ${mensaje}`);
    }
}
function mostrarToast(mensaje) {
    const toast = document.createElement("div");
    toast.className = "toast-notificacion";
    toast.textContent = mensaje;
    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add("visible"));
    setTimeout(() => {
        toast.classList.remove("visible");
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

function pedirPermisoNotificaciones() {
    if (!("Notification" in window)) return;
    if (Notification.permission === "granted") return;
    if (Notification.permission === "denied") return;
    Notification.requestPermission().catch(() => {});
}

let notificacionesRepartidor = [];

function agregarNotificacionRepartidor(pedido) {
    const existe = notificacionesRepartidor.some(
        (notificacion) => notificacion.id_pedido === pedido.id_pedido
    );

    if (existe) return;

    const notificacion = {
        id_pedido: pedido.id_pedido,
        direccion_recogida: pedido.direccion_recogida,
        direccion_entrega: pedido.direccion_entrega,
        fecha: new Date()
    };

    notificacionesRepartidor.unshift(notificacion);

    actualizarPanelNotificaciones();

    notificar(
        "Nuevo domicilio asignado",
        `Domicilio #${pedido.id_pedido}: ${pedido.direccion_entrega}`
    );
}

function actualizarPanelNotificaciones() {
    const contador = document.getElementById("contadorNotificaciones");
    const lista = document.getElementById("listaNotificaciones");

    if (!contador || !lista) return;

    contador.textContent = notificacionesRepartidor.length;

    contador.style.display =
        notificacionesRepartidor.length > 0 ? "flex" : "none";

    if (notificacionesRepartidor.length === 0) {
        lista.innerHTML = `
            <p class="notification-empty">
                No tienes nuevas notificaciones.
            </p>
        `;
        return;
    }

    lista.innerHTML = notificacionesRepartidor.map((notificacion) => `
        <div class="notification-item">
            <div class="notification-icon">
                <i class="fa-solid fa-box"></i>
            </div>

            <div class="notification-content">
                <strong>Nuevo domicilio asignado</strong>
                <p>Domicilio #${notificacion.id_pedido}</p>
                <small>
                    📍 ${escapeHtml(notificacion.direccion_entrega)}
                </small>
            </div>
        </div>
    `).join("");
}

function renderPaginacion(idContenedor, total, limite, paginaActual, onCambiar) {
    const contenedor = document.getElementById(idContenedor);
    if (!contenedor) return;
    const totalPaginas = Math.max(1, Math.ceil(total / limite));
    if (totalPaginas <= 1) { contenedor.innerHTML = ""; return; }
    contenedor.innerHTML = `
        <button type="button" class="btn-action btn-toggle-off" id="${idContenedor}Prev" ${paginaActual === 0 ? "disabled" : ""}>&laquo; Anterior</button>
        <span class="paginacion-info">Página ${paginaActual + 1} de ${totalPaginas} (${total} en total)</span>
        <button type="button" class="btn-action btn-toggle-off" id="${idContenedor}Next" ${paginaActual >= totalPaginas - 1 ? "disabled" : ""}>Siguiente &raquo;</button>
    `;
    document.getElementById(`${idContenedor}Prev`)?.addEventListener("click", () => onCambiar(paginaActual - 1));
    document.getElementById(`${idContenedor}Next`)?.addEventListener("click", () => onCambiar(paginaActual + 1));
}

async function cargarClientes() {
    const data = await api("/clientes/");
    const selector = document.getElementById("idCliente");
    if (selector) selector.innerHTML = data.clientes.map((client) =>
        `<option value="${client.id_cliente}">${escapeHtml(client.nombre)} - ${escapeHtml(client.telefono)}</option>`).join("");
}
function detallePedido(pedido) {
    return `<p><strong>Cliente:</strong> ${escapeHtml(pedido.cliente || "Solicitud propia")} ${pedido.telefono_cliente ? `(${escapeHtml(pedido.telefono_cliente)}, ${escapeHtml(pedido.correo_cliente)})` : ""}</p>
        <p><strong>Local de recogida:</strong> ${escapeHtml(pedido.nombre_local_recogida || "No indicado")}</p>
        <p><strong>Recogida:</strong> ${escapeHtml(pedido.direccion_recogida)}${pedido.hora_recogida_programada ? ` · ${escapeHtml(pedido.hora_recogida_programada)}` : " · Lo antes posible"}</p>
        <p><strong>Entrega:</strong> ${escapeHtml(pedido.direccion_entrega)}</p>
        <p><strong>Servicio:</strong> ${dinero(pedido.valor_servicio)} · ${escapeHtml(pedido.metodo_pago)}</p>
        <p><strong>Espera:</strong> ${pedido.tiempo_espera_min ?? "No indicada"} min · <strong>Recogida:</strong> ${pedido.tiempo_recogida_min ?? "No indicado"} min</p>
        <p><strong>Observaciones:</strong> ${escapeHtml(pedido.observaciones) || "Sin observaciones"}</p>`;
}

let graficoEstados = null;
let estadisticasConocidas = null;

async function cargarEstadisticas() {
    const data = await api("/estadisticas");
    const items = [
        ["Pendientes", data.pedidos_por_estado["Pendiente"]],
        ["Asignados", data.pedidos_por_estado["Asignado"]],
        ["En camino", data.pedidos_por_estado["En camino"]],
        ["Entregados", data.pedidos_por_estado["Entregado"]],
        ["Cancelados", data.pedidos_por_estado["Cancelado"]],
        ["Domiciliarios activos", `${data.repartidores_activos}/${data.total_repartidores}`],
        ["Clientes", data.total_clientes],
    ];
    document.getElementById("contenedorEstadisticas").innerHTML = items.map(([label, value]) =>
        `<div class="stat-card"><div class="stat-value">${value}</div><div class="stat-label">${escapeHtml(label)}</div></div>`).join("");

    const canvas = document.getElementById("graficoEstados");
    if (canvas && window.Chart) {
        const estados = ["Pendiente", "Asignado", "En camino", "Entregado", "Cancelado"];
        const colores = ["#d97706", "#4f46e5", "#2563eb", "#059669", "#dc2626"];
        const valores = estados.map((estado) => data.pedidos_por_estado[estado]);
        if (graficoEstados) {
            graficoEstados.data.datasets[0].data = valores;
            graficoEstados.update();
        } else {
            graficoEstados = new Chart(canvas, {
                type: "bar",
                data: { labels: estados, datasets: [{ label: "Domicilios", data: valores, backgroundColor: colores, borderRadius: 6 }] },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
                },
            });
        }
    }

    if (estadisticasConocidas) {
        const nuevosClientes = data.total_clientes - estadisticasConocidas.total_clientes;
        if (nuevosClientes > 0) {
            notificar("Nuevo cliente registrado", `${nuevosClientes} cliente(s) nuevo(s) se registraron en el sistema.`);
        }
        const nuevosEntregados = data.pedidos_por_estado["Entregado"] - estadisticasConocidas.pedidos_por_estado["Entregado"];
        if (nuevosEntregados > 0) {
            notificar("Domicilio entregado", `${nuevosEntregados} domicilio(s) fueron marcados como Entregado.`);
        }
    }
    estadisticasConocidas = data;
}

function abrirFormularioPassword(titulo, onGuardar) {
    abrirModal(titulo, `
        <form id="formNuevaPassword">
            <div class="form-group"><label>Nueva contraseña</label><input type="password" id="nuevaPassword" class="form-control" minlength="6" required></div>
            <button class="btn btn-primary" type="submit">Guardar</button>
        </form>
    `);
    document.getElementById("formNuevaPassword").addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
            await onGuardar(document.getElementById("nuevaPassword").value);
            cerrarModal(); alert("Contraseña actualizada.");
        } catch (error) { alert(error.message); }
    });
}

async function cargarRepartidoresAdmin() {
    const data = await api("/repartidores/todos");
    document.getElementById("contenedorRepartidores").innerHTML = data.repartidores.length
        ? data.repartidores.map((driver) => `<div class="order-card"><strong>${escapeHtml(driver.nombre)}</strong><p>${escapeHtml(driver.telefono)} · ${escapeHtml(driver.zona || "Sin zona")}</p>
            <div class="order-actions">
                <button class="btn-action ${driver.disponible ? "btn-toggle-on" : "btn-toggle-off"} btn-toggle-disponible" data-id="${driver.id_repartidor}" data-disponible="${driver.disponible ? 1 : 0}">${driver.disponible ? "Disponible" : "No disponible"}</button>
                <button class="btn-action btn-editar btn-password-repartidor" data-id="${driver.id_repartidor}">Contraseña</button>
                <button class="btn-action btn-cancelar btn-eliminar-repartidor" data-id="${driver.id_repartidor}">Eliminar</button>
            </div></div>`).join("")
        : "<p>No hay domiciliarios registrados.</p>";
    document.querySelectorAll(".btn-toggle-disponible").forEach((button) => button.addEventListener("click", async () => {
        try {
            await api(`/repartidores/${button.dataset.id}/disponibilidad`, { method: "PUT", body: JSON.stringify({ disponible: button.dataset.disponible !== "1" }) });
            await cargarAdmin();
        } catch (error) { alert(error.message); }
    }));
    document.querySelectorAll(".btn-password-repartidor").forEach((button) => button.addEventListener("click", () => {
        abrirFormularioPassword("Restablecer contraseña del domiciliario", (password) =>
            api(`/repartidores/${button.dataset.id}/password`, { method: "PUT", body: JSON.stringify({ password }) }));
    }));
    document.querySelectorAll(".btn-eliminar-repartidor").forEach((button) => button.addEventListener("click", async () => {
        if (!(await confirmarAccion("¿Eliminar este domiciliario? No podrá volver a iniciar sesión."))) return;
        try { await api(`/repartidores/${button.dataset.id}`, { method: "DELETE" }); await cargarAdmin(); }
        catch (error) { alert(error.message); }
    }));
    return data.repartidores.filter((driver) => driver.disponible);
}

function abrirFormularioEditarPedido(pedido) {
    abrirModal(`Editar domicilio #${pedido.id_pedido}`, `
        <form id="formEditarPedido">
            <div class="form-group"><label>Dirección exacta de recogida</label><input id="editDirRecogida" class="form-control" value="${escapeHtml(pedido.direccion_recogida)}" required></div>
            <div class="form-group"><label>Dirección exacta de entrega</label><input id="editDirEntrega" class="form-control" value="${escapeHtml(pedido.direccion_entrega)}" required></div>
            <div class="form-group"><label>Valor total del servicio</label><input type="number" min="0" id="editValorServicio" class="form-control" value="${pedido.valor_servicio}" required></div>
            <div class="form-group"><label>Método de pago</label><select id="editMetodoPago" class="form-control"><option ${pedido.metodo_pago === "Efectivo" ? "selected" : ""}>Efectivo</option><option ${pedido.metodo_pago === "Transferencia" ? "selected" : ""}>Transferencia</option></select></div>
            <div class="form-group"><label>Espera estimada (minutos)</label><input type="number" min="0" id="editTiempoEspera" class="form-control" value="${pedido.tiempo_espera_min ?? ""}"></div>
            <div class="form-group"><label>Tiempo para recoger (minutos)</label><input type="number" min="0" id="editTiempoRecogida" class="form-control" value="${pedido.tiempo_recogida_min ?? ""}"></div>
            <div class="form-group"><label>Observaciones</label><textarea id="editObservaciones" class="form-control">${escapeHtml(pedido.observaciones)}</textarea></div>
            <button class="btn btn-primary" type="submit">Guardar cambios</button>
        </form>
    `);
    document.getElementById("formEditarPedido").addEventListener("submit", async (event) => {
        event.preventDefault();
        const value = (id) => document.getElementById(id).value;
        try {
            await api(`/pedidos/${pedido.id_pedido}`, { method: "PUT", body: JSON.stringify({
                direccion_recogida: value("editDirRecogida").trim(), direccion_entrega: value("editDirEntrega").trim(),
                valor_servicio: Number(value("editValorServicio")), metodo_pago: value("editMetodoPago"),
                tiempo_espera_min: value("editTiempoEspera") ? Number(value("editTiempoEspera")) : null,
                tiempo_recogida_min: value("editTiempoRecogida") ? Number(value("editTiempoRecogida")) : null,
                observaciones: value("editObservaciones").trim(),
            })});
            cerrarModal(); await cargarAdmin(); alert("Domicilio actualizado.");
        } catch (error) { alert(error.message); }
    });
}

async function verHistorialPedido(idPedido) {
    try {
        const data = await api(`/pedidos/${idPedido}/historial`);
        const items = data.historial.map((h) =>
            `<li><span class="badge ${badgeClaseEstado(h.estado)}">${escapeHtml(h.estado)}</span> <span class="historial-fecha">${escapeHtml(h.fecha_hora)}</span>${h.usuario ? ` · ${escapeHtml(h.usuario)}` : ""}</li>`
        ).join("");
        abrirModal(`Historial del domicilio #${idPedido}`, `<ul class="historial-lista">${items || "<li>Sin historial registrado.</li>"}</ul>`);
    } catch (error) { alert(error.message); }
}

let paginaPedidos = 0;
const LIMITE_PEDIDOS = 9;
let pedidosPendientesConocidos = null;

async function cargarPedidosAdmin(driversActivos) {
    const filtro = document.getElementById("filtroEstado")?.value || "";
    const busqueda = document.getElementById("buscarPedidos")?.value.trim() || "";
    const parametros = new URLSearchParams({ limit: LIMITE_PEDIDOS, offset: paginaPedidos * LIMITE_PEDIDOS });
    if (filtro) parametros.set("estado", filtro);
    if (busqueda) parametros.set("q", busqueda);
    const pedidos = await api(`/pedidos/?${parametros.toString()}`);
    const pendientesActuales = new Set(
        pedidos.pedidos.filter((pedido) => pedido.estado === "Pendiente").map((pedido) => pedido.id_pedido)
    );
    if (pedidosPendientesConocidos) {
        const nuevos = pedidos.pedidos.filter(
            (pedido) => pedido.estado === "Pendiente" && !pedidosPendientesConocidos.has(pedido.id_pedido)
        );
        nuevos.forEach((pedido) => notificar("Nueva solicitud", `El cliente solicitó el domicilio #${pedido.id_pedido}.`));
    }
    pedidosPendientesConocidos = pendientesActuales;
    const driverOptions = driversActivos.map((driver) =>
        `<option value="${driver.id_repartidor}">${escapeHtml(driver.nombre)} - ${escapeHtml(driver.zona || "Sin zona")}</option>`).join("");
    document.getElementById("contenedorPedidos").innerHTML = pedidos.pedidos.length
        ? pedidos.pedidos.map((pedido) => { const bloqueado = ["Cancelado", "Entregado"].includes(pedido.estado); return `<article class="order-card"><div class="order-header"><strong>Domicilio #${pedido.id_pedido}</strong><span class="badge ${badgeClaseEstado(pedido.estado)}">${escapeHtml(pedido.estado)}</span></div><div class="order-info">${detallePedido(pedido)}</div>
            <div class="form-group"><label>Asignar domiciliario</label><select class="form-control selector-driver" data-id="${pedido.id_pedido}" ${bloqueado ? "disabled" : ""}><option value="">Seleccione...</option>${driverOptions}</select></div>
            <div class="order-actions">
                <button class="btn-action btn-camino btn-asignar" data-id="${pedido.id_pedido}" ${bloqueado ? "disabled" : ""}>Asignar</button>
                <button class="btn-action btn-editar btn-editar-pedido" data-id="${pedido.id_pedido}" ${bloqueado ? "disabled" : ""}>Editar</button>
                <button class="btn-action btn-toggle-off btn-ver-historial" data-id="${pedido.id_pedido}">Historial</button>
                <button class="btn-action btn-cancelar" data-id="${pedido.id_pedido}" ${bloqueado ? "disabled" : ""}>Cancelar</button>
            </div></article>`; }).join("")
        : "<p>No hay domicilios con ese filtro.</p>";
    renderPaginacion("paginacionPedidos", pedidos.total_pedidos, LIMITE_PEDIDOS, paginaPedidos, (nueva) => { paginaPedidos = nueva; cargarAdmin(); });
    document.querySelectorAll(".btn-asignar").forEach((button) => button.addEventListener("click", async () => {
        const select = document.querySelector(`.selector-driver[data-id="${button.dataset.id}"]`);
        if (!select.value) return alert("Seleccione un domiciliario.");
        try {
            const respuesta = await api(`/pedidos/${button.dataset.id}/asignar-repartidor`, {
                method: "PUT",
                body: JSON.stringify({ id_repartidor: Number(select.value) }),
            });
            await cargarAdmin();
            notificar("Domicilio asignado", `El domicilio #${respuesta.pedido.id_pedido} fue asignado a ${respuesta.pedido.repartidor}.`);
        }
        catch (error) { alert(error.message); }
    }));
    document.querySelectorAll(".btn-cancelar").forEach((button) => button.addEventListener("click", async () => {
        if (!(await confirmarAccion("¿Cancelar este domicilio?"))) return;
        try { await api(`/pedidos/${button.dataset.id}`, { method: "DELETE" }); await cargarAdmin(); }
        catch (error) { alert(error.message); }
    }));
    document.querySelectorAll(".btn-editar-pedido").forEach((button) => button.addEventListener("click", () => {
        const pedido = pedidos.pedidos.find((p) => p.id_pedido === Number(button.dataset.id));
        abrirFormularioEditarPedido(pedido);
    }));
    document.querySelectorAll(".btn-ver-historial").forEach((button) => button.addEventListener("click", () => verHistorialPedido(button.dataset.id)));
}

async function cargarAdmin() {
    const [driversActivos] = await Promise.all([cargarRepartidoresAdmin(), cargarEstadisticas()]);
    await cargarPedidosAdmin(driversActivos);
}

function filaGanancia(nombre, entregas, valorTotal, comisionRepartidor, comisionEmpresa) {
    return `<div class="order-card"><strong>${escapeHtml(nombre)}</strong><p>${entregas} domicilio(s) entregado(s)</p>
        <div class="ganancia-desglose">
            <div class="ganancia-fila"><span class="ganancia-label">Total facturado</span><span class="ganancia-valor">${dinero(valorTotal)}</span></div>
            <div class="ganancia-fila"><span class="ganancia-label">Domiciliario</span><span class="ganancia-valor verde">${dinero(comisionRepartidor)}</span></div>
            <div class="ganancia-fila"><span class="ganancia-label">Empresa</span><span class="ganancia-valor azul">${dinero(comisionEmpresa)}</span></div>
        </div></div>`;
}

async function cargarGanancias() {
    const inputFecha = document.getElementById("fechaGanancias");
    if (inputFecha && !inputFecha.value) inputFecha.value = new Date().toISOString().slice(0, 10);
    const fecha = inputFecha?.value || new Date().toISOString().slice(0, 10);
    const data = await api(`/estadisticas/ganancias?fecha=${encodeURIComponent(fecha)}`);
    document.getElementById("porcentajeGanancias").textContent =
        `Reparto: ${Math.round(data.porcentaje_repartidor * 100)}% domiciliario / ${Math.round((1 - data.porcentaje_repartidor) * 100)}% empresa`;
    document.getElementById("contenedorGanancias").innerHTML = data.repartidores.length
        ? data.repartidores.map((r) => filaGanancia(r.nombre, r.entregas, r.valor_total, r.comision_repartidor, r.comision_empresa)).join("")
        : "<p>No hay domiciliarios registrados.</p>";
    document.getElementById("totalesGanancias").innerHTML = `
        <div class="stat-card"><div class="stat-value">${dinero(data.totales.valor_total)}</div><div class="stat-label">Total del día</div></div>
        <div class="stat-card"><div class="stat-value">${dinero(data.totales.comision_repartidor)}</div><div class="stat-label">Comisión domiciliarios</div></div>
        <div class="stat-card"><div class="stat-value">${dinero(data.totales.comision_empresa)}</div><div class="stat-label">Comisión empresa</div></div>
    `;
}

function abrirFormularioEditarCliente(cliente) {
    abrirModal("Editar cliente", `
        <form id="formEditarCliente">
            <div class="form-group"><label>Nombre</label><input id="editNombreCliente" class="form-control" value="${escapeHtml(cliente.nombre)}" required></div>
            <div class="form-group"><label>Teléfono</label><input id="editTelefonoCliente" class="form-control" value="${escapeHtml(cliente.telefono)}" required></div>
            <div class="form-group"><label>Correo</label><input type="email" id="editCorreoCliente" class="form-control" value="${escapeHtml(cliente.correo)}" required></div>
            <button class="btn btn-primary" type="submit">Guardar cambios</button>
        </form>
    `);
    document.getElementById("formEditarCliente").addEventListener("submit", async (event) => {
        event.preventDefault();
        const value = (id) => document.getElementById(id).value;
        try {
            await api(`/clientes/${cliente.id_cliente}`, { method: "PUT", body: JSON.stringify({
                nombre: value("editNombreCliente").trim(), telefono: value("editTelefonoCliente").trim(), correo: value("editCorreoCliente").trim(),
            })});
            cerrarModal(); await cargarClientesAdmin(); await cargarClientes(); alert("Cliente actualizado.");
        } catch (error) { alert(error.message); }
    });
}

let paginaClientes = 0;
const LIMITE_CLIENTES = 9;

async function cargarClientesAdmin() {
    const busqueda = document.getElementById("buscarClientes")?.value.trim() || "";
    const parametros = new URLSearchParams({ limit: LIMITE_CLIENTES, offset: paginaClientes * LIMITE_CLIENTES });
    if (busqueda) parametros.set("q", busqueda);
    const data = await api(`/clientes/?${parametros.toString()}`);
    document.getElementById("contenedorClientes").innerHTML = data.clientes.length
        ? data.clientes.map((cliente) => `<div class="order-card"><strong>${escapeHtml(cliente.nombre)}</strong><p>${escapeHtml(cliente.telefono)} · ${escapeHtml(cliente.correo)}</p>
            <div class="order-actions">
                <button class="btn-action btn-editar btn-editar-cliente" data-id="${cliente.id_cliente}">Editar</button>
                <button class="btn-action btn-editar btn-password-cliente" data-id="${cliente.id_cliente}">Contraseña</button>
                <button class="btn-action btn-cancelar btn-eliminar-cliente" data-id="${cliente.id_cliente}">Eliminar</button>
            </div></div>`).join("")
        : "<p>No hay clientes registrados.</p>";
    renderPaginacion("paginacionClientes", data.total_clientes, LIMITE_CLIENTES, paginaClientes, (nueva) => { paginaClientes = nueva; cargarClientesAdmin(); });
    document.querySelectorAll(".btn-editar-cliente").forEach((button) => button.addEventListener("click", () => {
        const cliente = data.clientes.find((c) => c.id_cliente === Number(button.dataset.id));
        abrirFormularioEditarCliente(cliente);
    }));
    document.querySelectorAll(".btn-password-cliente").forEach((button) => button.addEventListener("click", () => {
        abrirFormularioPassword("Restablecer contraseña del cliente", (password) =>
            api(`/clientes/${button.dataset.id}/password`, { method: "PUT", body: JSON.stringify({ password }) }));
    }));
    document.querySelectorAll(".btn-eliminar-cliente").forEach((button) => button.addEventListener("click", async () => {
        if (!(await confirmarAccion("¿Eliminar este cliente?"))) return;
        try { await api(`/clientes/${button.dataset.id}`, { method: "DELETE" }); await cargarClientesAdmin(); await cargarClientes(); }
        catch (error) { alert(error.message); }
    }));
}

let debounceBusqueda = null;
function alBuscar(callback) {
    clearTimeout(debounceBusqueda);
    debounceBusqueda = setTimeout(() => callback().catch((error) => alert(error.message)), 350);
}

// --- MAPA LEAFLET ---
let mapaAdmin = null;
let marcadoresFlota = {};
let intervaloMapa = null;

async function actualizarMapaFlota() {
    try {
        const data = await api("/repartidores/ubicaciones");
        data.repartidores.forEach(rep => {
            if (marcadoresFlota[rep.id_repartidor]) {
                marcadoresFlota[rep.id_repartidor].setLatLng([rep.latitud, rep.longitud]);
            } else {
                if(window.L) {
                    const marker = L.marker([rep.latitud, rep.longitud]).addTo(mapaAdmin)
                        .bindPopup(`<b>${escapeHtml(rep.nombre)}</b><br>${rep.disponible ? 'Disponible' : 'Ocupado'}`);
                    marcadoresFlota[rep.id_repartidor] = marker;
                }
            }
        });
    } catch (error) {
        console.error("Error al obtener ubicaciones:", error);
    }
}

function iniciarMapaFlota() {
    if (mapaAdmin || !document.getElementById("mapaFlota") || !window.L) return;
    
    // Coordenadas por defecto (Bogotá)
    mapaAdmin = L.map('mapaFlota').setView([4.6097, -74.0817], 12); 
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap contributors'
    }).addTo(mapaAdmin);
    
    // Al abrir la pestaña de mapa, redibujar para evitar problemas de tiles grises
    document.getElementById("vistaRadioMapa")?.addEventListener("change", () => {
        setTimeout(() => mapaAdmin.invalidateSize(), 100);
    });

    actualizarMapaFlota();
    intervaloMapa = setInterval(actualizarMapaFlota, 10000); // 10 segundos
}

async function iniciarAdmin() {
    if (!protegerVista("administrador")) return;
    pedirPermisoNotificaciones();
    if (!window.intervaloAdmin) {
        window.intervaloAdmin = setInterval(() => cargarAdmin().catch((error) => {
            console.error("Error actualizando el panel administrativo:", error);
        }), 15000);
    }
    iniciarMapaFlota();
    try { await cargarClientes(); await cargarAdmin(); await cargarClientesAdmin(); await cargarGanancias(); } catch (error) { alert(error.message); }
    document.getElementById("fechaGanancias")?.addEventListener("change", () => cargarGanancias().catch((error) => alert(error.message)));
    document.getElementById("filtroEstado")?.addEventListener("change", () => { paginaPedidos = 0; cargarAdmin().catch((error) => alert(error.message)); });
    document.getElementById("buscarPedidos")?.addEventListener("input", () => { paginaPedidos = 0; alBuscar(cargarAdmin); });
    document.getElementById("buscarClientes")?.addEventListener("input", () => { paginaClientes = 0; alBuscar(cargarClientesAdmin); });
    document.getElementById("btnExportarCsv")?.addEventListener("click", async () => {
        try {
            const filtro = document.getElementById("filtroEstado")?.value || "";
            const response = await fetch(`${API_URL}/pedidos/exportar${filtro ? `?estado=${encodeURIComponent(filtro)}` : ""}`, { headers: headers() });
            if (!response.ok) {
                let data = {};
                try { data = JSON.parse(await response.text()); } catch { /* respuesta no era JSON */ }
                throw new Error(`No se pudo exportar el archivo (HTTP ${response.status}): ${extraerMensajeError(data)}`);
            }
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const enlace = document.createElement("a");
            enlace.href = url;
            enlace.download = "domicilios.csv";
            enlace.click();
            URL.revokeObjectURL(url);
        } catch (error) { alert(error.message); }
    });
    document.getElementById("btnCerrarModal")?.addEventListener("click", cerrarModal);
    document.getElementById("modalOverlay")?.addEventListener("click", (event) => { if (event.target.id === "modalOverlay") cerrarModal(); });
    document.getElementById("formPedido")?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const value = (id) => document.getElementById(id).value;
        try {
            await api("/pedidos/", { method: "POST", body: JSON.stringify({
                id_cliente: Number(value("idCliente")), direccion_recogida: value("dirRecogida").trim(),
                direccion_entrega: value("dirEntrega").trim(), valor_servicio: Number(value("valorServicio")),
                metodo_pago: value("metodoPago"), tiempo_espera_min: value("tiempoEspera") ? Number(value("tiempoEspera")) : null,
                tiempo_recogida_min: value("tiempoRecogida") ? Number(value("tiempoRecogida")) : null,
                observaciones: value("observaciones").trim()
            })});
            event.target.reset(); await cargarAdmin(); alert("Domicilio registrado.");
        } catch (error) { alert(error.message); }
    });
    document.getElementById("formNuevoRepartidor")?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const value = (id) => document.getElementById(id).value;
        try {
            await api("/repartidores/", { method: "POST", body: JSON.stringify({
                nombre: value("repNombre").trim(), correo: value("repCorreo").trim(),
                password: value("repPassword"), telefono: value("repTelefono").trim(),
                zona: value("repZona").trim(),
                tipo_vehiculo: value("repTipoVehiculo"),
                placa_vehiculo: value("repPlacaVehiculo").trim().toUpperCase(),
            })});
            event.target.reset(); await cargarAdmin(); alert("Domiciliario creado.");
        } catch (error) { alert(error.message); }
    });
    document.getElementById("formNuevoCliente")?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const value = (id) => document.getElementById(id).value;
        try {
            await api("/clientes/", { method: "POST", body: JSON.stringify({
                nombre: value("cliNombre").trim(), correo: value("cliCorreo").trim(),
                password: value("cliPassword"), telefono: value("cliTelefono").trim(),
                direccion: value("cliDireccion").trim(),
                nombre_local: value("cliLocal").trim() || null,
            })});
            event.target.reset(); await cargarClientesAdmin(); await cargarClientes();
            alert("Cliente registrado. Entrégale su contraseña temporal.");
        } catch (error) { alert(error.message); }
    });
}



let intervaloRepartidor = null;
let pedidosConocidosRepartidor = null;

async function iniciarRepartidor() {
    if (!protegerVista("repartidor")) return;
    const btnNotificaciones = document.getElementById("btnNotificaciones");
    const panelNotificaciones = document.getElementById("panelNotificaciones");

    if (btnNotificaciones && panelNotificaciones && !btnNotificaciones.dataset.inicializado) {

    btnNotificaciones.dataset.inicializado = "true";

    btnNotificaciones.addEventListener("click", () => {
        panelNotificaciones.classList.toggle("visible");
    });
    }
    if (!intervaloRepartidor) {
        pedirPermisoNotificaciones();
        document.getElementById("btnActualizarPedidos")?.addEventListener("click", () => iniciarRepartidor());
        intervaloRepartidor = setInterval(iniciarRepartidor, 15000);
    }
    try {
        const data = await api("/repartidores/me/pedidos");
        const ganancias = await api("/repartidores/me/ganancias");
        const contenedorGanancias = document.getElementById("contenedorGananciasPropias");
        if (contenedorGanancias) contenedorGanancias.innerHTML = `
            <div class="stat-card"><div class="stat-value">${ganancias.entregas}</div><div class="stat-label">Domicilios entregados hoy</div></div>
            <div class="stat-card"><div class="stat-value">${dinero(ganancias.comision_repartidor)}</div><div class="stat-label">Tu ganancia de hoy</div></div>
        `;
        const assigned = data;
        const pedidosNuevos = assigned.pedidos.filter(
            (pedido) => !pedidosConocidosRepartidor || !pedidosConocidosRepartidor.has(pedido.id_pedido)
        );
        pedidosNuevos.forEach(agregarNotificacionRepartidor);
        pedidosConocidosRepartidor = new Set(assigned.pedidos.map((pedido) => pedido.id_pedido));
        const container = document.getElementById("contenedorPedidosRepartidor");
        container.innerHTML = assigned.pedidos.length ? assigned.pedidos.map((pedido) => `<article class="order-card"><div class="order-header"><strong>Domicilio #${pedido.id_pedido}</strong><span class="badge ${badgeClaseEstado(pedido.estado)}">${escapeHtml(pedido.estado)}</span></div><div class="order-info">${detallePedido(pedido)}</div><div class="order-actions"><button class="btn-action btn-entregado btn-estado" data-id="${pedido.id_pedido}" data-estado="En camino">En camino</button><button class="btn-action btn-entregado btn-estado" data-id="${pedido.id_pedido}" data-estado="Entregado">Entregado</button></div></article>`).join("") : "<p>No tiene domicilios asignados.</p>";
        container.querySelectorAll(".btn-estado").forEach((button) => button.addEventListener("click", async () => {
            try { await api(`/pedidos/${button.dataset.id}/estado`, { method: "PUT", body: JSON.stringify({ nuevo_estado: button.dataset.estado }) }); await iniciarRepartidor(); }
            catch (error) { alert(error.message); }
        }));
    } catch (error) { alert(error.message); }
}

async function iniciarCliente() {
    if (!protegerVista("cliente")) return;
    pedirPermisoNotificaciones();
    let pedidosClienteConocidos = null;
    const cargarMisPedidos = async () => {
        const data = await api("/clientes/me/pedidos");
        const cambios = data.pedidos.filter((pedido) => {
            const anterior = pedidosClienteConocidos?.get(pedido.id_pedido);
            return !anterior
                ? pedido.estado === "Asignado"
                : anterior.estado !== pedido.estado || anterior.repartidor !== pedido.repartidor;
        });
        pedidosClienteConocidos = new Map(data.pedidos.map((pedido) => [pedido.id_pedido, pedido]));
        const contenedor = document.getElementById("contenedorPedidosCliente");
        if (contenedor) {
            contenedor.innerHTML = data.pedidos.length
                ? data.pedidos.map((pedido) => `<article class="order-card"><div class="order-header"><strong>Domicilio #${pedido.id_pedido}</strong><span class="badge ${badgeClaseEstado(pedido.estado)}">${escapeHtml(pedido.estado)}</span></div><div class="order-info">${detallePedido(pedido)}<p><strong>Domiciliario:</strong> ${escapeHtml(pedido.repartidor || "Pendiente de asignación")}</p></div></article>`).join("")
                : "<p>No tienes domicilios registrados.</p>";
        }
        cambios.forEach((pedido) => notificar("Actualización de domicilio", `El domicilio #${pedido.id_pedido} ahora está ${pedido.estado}.`));
    };
    cargarMisPedidos().catch((error) => alert(error.message));
    if (!window.intervaloCliente) {
        window.intervaloCliente = setInterval(() => cargarMisPedidos().catch((error) => {
            console.error("Error actualizando los domicilios del cliente:", error);
        }), 15000);
    }
    document.getElementById("formNuevoPedidoCliente")?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const value = (id) => document.getElementById(id).value;
        try {
            await api("/clientes/me/pedidos", { method: "POST", body: JSON.stringify({
                nombre_local_recogida: value("clienteLocalRecogida").trim(),
                direccion_recogida: value("clienteDireccionRecogida").trim(),
                direccion_entrega: value("clienteDireccionEntrega").trim(),
                hora_recogida_programada: value("clienteHoraRecogida") || null,
                tiempo_espera_min: value("clienteTiempoEspera") ? Number(value("clienteTiempoEspera")) : null,
                observaciones: value("clienteObservaciones").trim(),
            })});
            event.target.reset();
            await cargarMisPedidos();
            alert("Solicitud enviada al administrador.");
        } catch (error) { alert(error.message); }
    });
    let ultimoPedidoConsultado = null;
    document.getElementById("formConsultaPedido")?.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
            const data = await api(`/pedidos/${Number(document.getElementById("idPedido").value)}`);
            ultimoPedidoConsultado = data.pedido;
            document.getElementById("resultadoConsulta").innerHTML = `<article class="order-card"><div class="order-header"><strong>Domicilio #${data.pedido.id_pedido}</strong><span class="badge ${badgeClaseEstado(data.pedido.estado)}">${escapeHtml(data.pedido.estado)}</span></div><div class="order-info">${detallePedido(data.pedido)}</div></article>`;
            document.getElementById("wrapperComprobante").style.display = "block";
        } catch (error) {
            alert(error.message);
            ultimoPedidoConsultado = null;
            document.getElementById("resultadoConsulta").innerHTML = `<p class="empty-state">No se encontró el domicilio. Verifique el número e intente de nuevo.</p>`;
            document.getElementById("wrapperComprobante").style.display = "none";
        }
    });
    document.getElementById("btnComprobante")?.addEventListener("click", async (event) => {
        if (!ultimoPedidoConsultado || !window.jspdf) return;
        const btn = event.currentTarget;
        const textoOriginal = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Generando PDF...';
        try {
            const pedido = ultimoPedidoConsultado;
            const doc = new window.jspdf.jsPDF();
            doc.setFontSize(16);
            doc.text("Rápido Express - Comprobante de domicilio", 15, 20);
            doc.setFontSize(11);
            const lineas = [
                `Domicilio #${pedido.id_pedido}`,
                `Estado: ${pedido.estado}`,
                `Cliente: ${pedido.cliente} (${pedido.telefono_cliente})`,
                `Recogida: ${pedido.direccion_recogida}`,
                `Entrega: ${pedido.direccion_entrega}`,
                `Fecha: ${pedido.fecha_hora}`,
                `Valor del servicio: ${dinero(pedido.valor_servicio)}`,
                `Método de pago: ${pedido.metodo_pago}`,
                `Observaciones: ${pedido.observaciones || "Sin observaciones"}`,
            ];
            lineas.forEach((linea, indice) => doc.text(linea, 15, 35 + indice * 8));
            doc.save(`comprobante-domicilio-${pedido.id_pedido}.pdf`);
        } finally {
            btn.disabled = false;
            btn.innerHTML = textoOriginal;
        }
    });
}
document.addEventListener("DOMContentLoaded", () => {
    if (document.getElementById("formPedido")) iniciarAdmin();
    if (document.getElementById("contenedorPedidosRepartidor")) iniciarRepartidor();
    if (document.getElementById("formConsultaPedido")) iniciarCliente();

    const sidebarToggle = document.getElementById("sidebarToggle");
    if (sidebarToggle) {
        document.querySelectorAll(".sidebar-nav .nav-link").forEach((link) => {
            link.addEventListener("click", () => { sidebarToggle.checked = false; });
        });
    }
});

// --- GPS TRACKING PARA REPARTIDORES ---
let rastreadorGPS = null;

function iniciarRastreoGPS() {
    if (usuario && usuario.rol === 'repartidor' && "geolocation" in navigator) {
        // Pedimos la ubicación constantemente
        rastreadorGPS = navigator.geolocation.watchPosition(
            async (pos) => {
                try {
                    await fetch(`${API_URL}/repartidores/ubicacion`, {
                        method: 'PATCH',
                        headers: headers(),
                        body: JSON.stringify({
                            latitud: pos.coords.latitude,
                            longitud: pos.coords.longitude
                        })
                    });
                } catch (error) {
                    console.error("Error enviando ubicación GPS:", error);
                }
            },
            (error) => {
                console.warn("GPS no disponible o denegado:", error);
            },
            {
                enableHighAccuracy: true,
                maximumAge: 10000,
                timeout: 5000
            }
        );
    }
}

// Iniciar el rastreo si somos repartidores
if (usuario && usuario.rol === 'repartidor') {
    iniciarRastreoGPS();
}
