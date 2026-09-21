const API_URL = window.location.origin;
const usuario = JSON.parse(sessionStorage.getItem("usuario") || "null");
const token = sessionStorage.getItem("token") || "";

function headers() {
    const base = { "Content-Type": "application/json" };
    if (token) base.Authorization = `Bearer ${token}`;
    return base;
}
function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[char]);
}
function dinero(value) {
    return Number(value || 0).toLocaleString("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });
}
async function api(path, options = {}) {
    const response = await fetch(`${API_URL}${path}`, { ...options, headers: { ...headers(), ...(options.headers || {}) } });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || data.error || "La operación no pudo completarse.");
    return data;
}
function cerrarSesion() {
    sessionStorage.removeItem("usuario");
    sessionStorage.removeItem("token");
    window.location.href = "login.html";
}
function protegerVista(rol) {
    if (!usuario || !token || usuario.rol !== rol) { window.location.replace("login.html"); return false; }
    document.getElementById("nombreUsuario")?.append(` ${usuario.nombre}`);
    document.getElementById("btnLogout")?.addEventListener("click", (event) => { event.preventDefault(); cerrarSesion(); });
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

async function cargarClientes() {
    const data = await api("/clientes/");
    const selector = document.getElementById("idCliente");
    if (selector) selector.innerHTML = data.clientes.map((client) =>
        `<option value="${client.id_cliente}">${escapeHtml(client.nombre)} - ${escapeHtml(client.telefono)}</option>`).join("");
}
function detallePedido(pedido) {
    return `<p><strong>Cliente:</strong> ${escapeHtml(pedido.cliente)} (${escapeHtml(pedido.telefono_cliente)}, ${escapeHtml(pedido.correo_cliente)})</p>
        <p><strong>Recogida:</strong> ${escapeHtml(pedido.direccion_recogida)}</p>
        <p><strong>Entrega:</strong> ${escapeHtml(pedido.direccion_entrega)}</p>
        <p><strong>Servicio:</strong> ${dinero(pedido.valor_servicio)} · ${escapeHtml(pedido.metodo_pago)}</p>
        <p><strong>Espera:</strong> ${pedido.tiempo_espera_min ?? "No indicada"} min · <strong>Recogida:</strong> ${pedido.tiempo_recogida_min ?? "No indicado"} min</p>
        <p><strong>Observaciones:</strong> ${escapeHtml(pedido.observaciones) || "Sin observaciones"}</p>`;
}

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
}

async function cargarRepartidoresAdmin() {
    const data = await api("/repartidores/todos");
    document.getElementById("contenedorRepartidores").innerHTML = data.repartidores.length
        ? data.repartidores.map((driver) => `<div class="order-card"><strong>${escapeHtml(driver.nombre)}</strong><p>${escapeHtml(driver.telefono)} · ${escapeHtml(driver.zona || "Sin zona")}</p>
            <div class="order-actions">
                <button class="btn-action ${driver.disponible ? "btn-toggle-on" : "btn-toggle-off"} btn-toggle-disponible" data-id="${driver.id_repartidor}" data-disponible="${driver.disponible ? 1 : 0}">${driver.disponible ? "Disponible" : "No disponible"}</button>
                <button class="btn-action btn-cancelar btn-eliminar-repartidor" data-id="${driver.id_repartidor}">Eliminar</button>
            </div></div>`).join("")
        : "<p>No hay domiciliarios registrados.</p>";
    document.querySelectorAll(".btn-toggle-disponible").forEach((button) => button.addEventListener("click", async () => {
        try {
            await api(`/repartidores/${button.dataset.id}/disponibilidad`, { method: "PUT", body: JSON.stringify({ disponible: button.dataset.disponible !== "1" }) });
            await cargarAdmin();
        } catch (error) { alert(error.message); }
    }));
    document.querySelectorAll(".btn-eliminar-repartidor").forEach((button) => button.addEventListener("click", async () => {
        if (!confirm("¿Eliminar este domiciliario? No podrá volver a iniciar sesión.")) return;
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

async function cargarPedidosAdmin(driversActivos) {
    const filtro = document.getElementById("filtroEstado")?.value || "";
    const pedidos = await api(`/pedidos/${filtro ? `?estado=${encodeURIComponent(filtro)}` : ""}`);
    const driverOptions = driversActivos.map((driver) =>
        `<option value="${driver.id_repartidor}">${escapeHtml(driver.nombre)} - ${escapeHtml(driver.zona || "Sin zona")}</option>`).join("");
    document.getElementById("contenedorPedidos").innerHTML = pedidos.pedidos.length
        ? pedidos.pedidos.map((pedido) => { const bloqueado = ["Cancelado", "Entregado"].includes(pedido.estado); return `<article class="order-card"><div class="order-header"><strong>Domicilio #${pedido.id_pedido}</strong><span class="badge ${badgeClaseEstado(pedido.estado)}">${escapeHtml(pedido.estado)}</span></div><div class="order-info">${detallePedido(pedido)}</div>
            <div class="form-group"><label>Asignar domiciliario</label><select class="form-control selector-driver" data-id="${pedido.id_pedido}" ${bloqueado ? "disabled" : ""}><option value="">Seleccione...</option>${driverOptions}</select></div>
            <div class="order-actions">
                <button class="btn-action btn-camino btn-asignar" data-id="${pedido.id_pedido}" ${bloqueado ? "disabled" : ""}>Asignar</button>
                <button class="btn-action btn-editar btn-editar-pedido" data-id="${pedido.id_pedido}" ${bloqueado ? "disabled" : ""}>Editar</button>
                <button class="btn-action btn-cancelar" data-id="${pedido.id_pedido}" ${bloqueado ? "disabled" : ""}>Cancelar</button>
            </div></article>`; }).join("")
        : "<p>No hay domicilios con ese filtro.</p>";
    document.querySelectorAll(".btn-asignar").forEach((button) => button.addEventListener("click", async () => {
        const select = document.querySelector(`.selector-driver[data-id="${button.dataset.id}"]`);
        if (!select.value) return alert("Seleccione un domiciliario.");
        try { await api(`/pedidos/${button.dataset.id}/asignar-repartidor`, { method: "PUT", body: JSON.stringify({ id_repartidor: Number(select.value) }) }); await cargarAdmin(); }
        catch (error) { alert(error.message); }
    }));
    document.querySelectorAll(".btn-cancelar").forEach((button) => button.addEventListener("click", async () => {
        if (!confirm("¿Cancelar este domicilio?")) return;
        try { await api(`/pedidos/${button.dataset.id}`, { method: "DELETE" }); await cargarAdmin(); }
        catch (error) { alert(error.message); }
    }));
    document.querySelectorAll(".btn-editar-pedido").forEach((button) => button.addEventListener("click", () => {
        const pedido = pedidos.pedidos.find((p) => p.id_pedido === Number(button.dataset.id));
        abrirFormularioEditarPedido(pedido);
    }));
}

async function cargarAdmin() {
    const [driversActivos] = await Promise.all([cargarRepartidoresAdmin(), cargarEstadisticas()]);
    await cargarPedidosAdmin(driversActivos);
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

async function cargarClientesAdmin() {
    const data = await api("/clientes/");
    document.getElementById("contenedorClientes").innerHTML = data.clientes.length
        ? data.clientes.map((cliente) => `<div class="order-card"><strong>${escapeHtml(cliente.nombre)}</strong><p>${escapeHtml(cliente.telefono)} · ${escapeHtml(cliente.correo)}</p>
            <div class="order-actions"><button class="btn-action btn-editar btn-editar-cliente" data-id="${cliente.id_cliente}">Editar</button><button class="btn-action btn-cancelar btn-eliminar-cliente" data-id="${cliente.id_cliente}">Eliminar</button></div></div>`).join("")
        : "<p>No hay clientes registrados.</p>";
    document.querySelectorAll(".btn-editar-cliente").forEach((button) => button.addEventListener("click", () => {
        const cliente = data.clientes.find((c) => c.id_cliente === Number(button.dataset.id));
        abrirFormularioEditarCliente(cliente);
    }));
    document.querySelectorAll(".btn-eliminar-cliente").forEach((button) => button.addEventListener("click", async () => {
        if (!confirm("¿Eliminar este cliente?")) return;
        try { await api(`/clientes/${button.dataset.id}`, { method: "DELETE" }); await cargarClientesAdmin(); await cargarClientes(); }
        catch (error) { alert(error.message); }
    }));
}

async function iniciarAdmin() {
    if (!protegerVista("administrador")) return;
    try { await cargarClientes(); await cargarAdmin(); await cargarClientesAdmin(); } catch (error) { alert(error.message); }
    document.getElementById("filtroEstado")?.addEventListener("change", () => cargarAdmin().catch((error) => alert(error.message)));
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
            })});
            event.target.reset(); await cargarAdmin(); alert("Domiciliario creado.");
        } catch (error) { alert(error.message); }
    });
}

function pedirPermisoNotificaciones() {
    if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
}

function notificarNuevoDomicilio(pedido) {
    const mensaje = `Domicilio #${pedido.id_pedido}: ${pedido.direccion_recogida} → ${pedido.direccion_entrega}`;
    if ("Notification" in window && Notification.permission === "granted") {
        new Notification("Nuevo domicilio asignado", { body: mensaje, icon: "icons/icon-192.png" });
    } else {
        mostrarToast(`Nuevo domicilio asignado — ${mensaje}`);
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

let intervaloRepartidor = null;
let pedidosConocidosRepartidor = null;

async function iniciarRepartidor() {
    if (!protegerVista("repartidor")) return;
    if (!intervaloRepartidor) {
        pedirPermisoNotificaciones();
        document.getElementById("btnActualizarPedidos")?.addEventListener("click", () => iniciarRepartidor());
        intervaloRepartidor = setInterval(iniciarRepartidor, 15000);
    }
    try {
        const data = await api("/repartidores/activos");
        const own = data.repartidores.find((driver) => driver.id_usuario === usuario.id_usuario);
        if (!own) throw new Error("No hay un perfil activo de domiciliario para este usuario.");
        const assigned = await api(`/repartidores/${own.id_repartidor}/pedidos`);
        if (pedidosConocidosRepartidor) {
            assigned.pedidos
                .filter((pedido) => !pedidosConocidosRepartidor.has(pedido.id_pedido))
                .forEach(notificarNuevoDomicilio);
        }
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
    document.getElementById("formConsultaPedido")?.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
            const data = await api(`/pedidos/${Number(document.getElementById("idPedido").value)}`);
            document.getElementById("resultadoConsulta").innerHTML = `<article class="order-card"><div class="order-header"><strong>Domicilio #${data.pedido.id_pedido}</strong><span class="badge ${badgeClaseEstado(data.pedido.estado)}">${escapeHtml(data.pedido.estado)}</span></div><div class="order-info">${detallePedido(data.pedido)}</div></article>`;
        } catch (error) { alert(error.message); }
    });
}

document.addEventListener("DOMContentLoaded", () => {
    if (document.getElementById("formPedido")) iniciarAdmin();
    if (document.getElementById("contenedorPedidosRepartidor")) iniciarRepartidor();
    if (document.getElementById("formConsultaPedido")) iniciarCliente();
});
