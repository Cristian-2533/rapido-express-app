const API_URL = ["5500", "5501"].includes(window.location.port)
    ? "http://127.0.0.1:8000"
    : window.location.origin;
const usuario = JSON.parse(sessionStorage.getItem("usuario") || "null");

function headers() {
    return { "Content-Type": "application/json", "X-Rol": usuario?.rol || "", "X-Usuario-Id": usuario?.id_usuario || "" };
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
    window.location.href = "login.html";
}
function protegerVista(rol) {
    if (!usuario || usuario.rol !== rol) { window.location.replace("login.html"); return false; }
    document.getElementById("nombreUsuario")?.append(` ${usuario.nombre}`);
    document.getElementById("btnLogout")?.addEventListener("click", (event) => { event.preventDefault(); cerrarSesion(); });
    return true;
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

async function cargarAdmin() {
    const [pedidos, drivers] = await Promise.all([api("/pedidos/"), api("/repartidores/activos")]);
    const driverOptions = drivers.repartidores.map((driver) =>
        `<option value="${driver.id_repartidor}">${escapeHtml(driver.nombre)} - ${escapeHtml(driver.zona || "Sin zona")}</option>`).join("");
    document.getElementById("contenedorRepartidores").innerHTML = drivers.repartidores.length
        ? drivers.repartidores.map((driver) => `<div class="order-card"><strong>${escapeHtml(driver.nombre)}</strong><p>${escapeHtml(driver.telefono)} · ${escapeHtml(driver.zona || "Sin zona")}</p><span class="badge badge-entregado">Activo</span></div>`).join("")
        : "<p>No hay domiciliarios activos.</p>";
    document.getElementById("contenedorPedidos").innerHTML = pedidos.pedidos.length
        ? pedidos.pedidos.map((pedido) => `<article class="order-card"><div class="order-header"><strong>Domicilio #${pedido.id_pedido}</strong><span class="badge">${escapeHtml(pedido.estado)}</span></div><div class="order-info">${detallePedido(pedido)}</div>
            <div class="form-group"><label>Asignar domiciliario</label><select class="form-control selector-driver" data-id="${pedido.id_pedido}" ${pedido.estado === "Cancelado" ? "disabled" : ""}><option value="">Seleccione...</option>${driverOptions}</select></div>
            <div class="order-actions"><button class="btn-action btn-camino btn-asignar" data-id="${pedido.id_pedido}">Asignar</button><button class="btn-action btn-cancelar" data-id="${pedido.id_pedido}" ${["Cancelado", "Entregado"].includes(pedido.estado) ? "disabled" : ""}>Cancelar</button></div></article>`).join("")
        : "<p>No hay domicilios registrados.</p>";
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
}

async function iniciarAdmin() {
    if (!protegerVista("administrador")) return;
    try { await cargarClientes(); await cargarAdmin(); } catch (error) { alert(error.message); }
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
}

async function iniciarRepartidor() {
    if (!protegerVista("repartidor")) return;
    try {
        const data = await api("/repartidores/activos");
        const own = data.repartidores.find((driver) => driver.id_usuario === usuario.id_usuario);
        if (!own) throw new Error("No hay un perfil activo de domiciliario para este usuario.");
        const assigned = await api(`/repartidores/${own.id_repartidor}/pedidos`);
        const container = document.getElementById("contenedorPedidosRepartidor");
        container.innerHTML = assigned.pedidos.length ? assigned.pedidos.map((pedido) => `<article class="order-card"><div class="order-header"><strong>Domicilio #${pedido.id_pedido}</strong><span class="badge">${escapeHtml(pedido.estado)}</span></div><div class="order-info">${detallePedido(pedido)}</div><div class="order-actions"><button class="btn-action btn-entregado btn-estado" data-id="${pedido.id_pedido}" data-estado="En camino">En camino</button><button class="btn-action btn-entregado btn-estado" data-id="${pedido.id_pedido}" data-estado="Entregado">Entregado</button></div></article>`).join("") : "<p>No tiene domicilios asignados.</p>";
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
            document.getElementById("resultadoConsulta").innerHTML = `<article class="order-card"><div class="order-header"><strong>Domicilio #${data.pedido.id_pedido}</strong><span class="badge">${escapeHtml(data.pedido.estado)}</span></div><div class="order-info">${detallePedido(data.pedido)}</div></article>`;
        } catch (error) { alert(error.message); }
    });
}

document.addEventListener("DOMContentLoaded", () => {
    if (document.getElementById("formPedido")) iniciarAdmin();
    if (document.getElementById("contenedorPedidosRepartidor")) iniciarRepartidor();
    if (document.getElementById("formConsultaPedido")) iniciarCliente();
});
