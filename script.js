const API_URL = "http://127.0.0.1:8000";

document.addEventListener("DOMContentLoaded", () => {
    cargarPedidos();

    let btnLogout = document.getElementById("btnLogout");
    if (!btnLogout) {
        btnLogout = document.createElement("a");
        btnLogout.id = "btnLogout";
        btnLogout.href = "login.html";
        btnLogout.textContent = "Cerrar sesión";
        btnLogout.style.cssText = [
            "position: fixed",
            "top: 24px",
            "right: 24px",
            "z-index: 1000",
            "display: inline-flex",
            "padding: 12px 18px",
            "border-radius: 8px",
            "background: #1e3a60",
            "color: #ffffff",
            "font: 600 14px Arial, sans-serif",
            "text-decoration: none",
            "box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3)"
        ].join(";");
        document.body.appendChild(btnLogout);
    }

    btnLogout.addEventListener("click", () => {
        window.location.replace("login.html");
    });

    // Evento para guardar un pedido desde el formulario visual
    const formPedido = document.getElementById("formPedido");
    
    if (formPedido) {
       formPedido.addEventListener("submit", async (e) => {
            e.preventDefault(); // Evita que la página se recargue
            
            const nuevoPedido = {
                id_cliente: parseInt(document.getElementById("idCliente").value),
                direccion_recogida: document.getElementById("dirRecogida").value,
                direccion_entrega: document.getElementById("dirEntrega").value,
                valor_servicio: parseFloat(document.getElementById("valorServicio").value),
                metodo_pago: document.getElementById("metodoPago").value,
                observaciones: "Creado desde la interfaz web"
            };

            console.log("Enviando al backend:", nuevoPedido);

            try {
                const res = await fetch(`${API_URL}/pedidos/`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(nuevoPedido)
                });

                const data = await res.json();
                console.log("Respuesta del servidor:", data);

                if (res.ok) {
                    document.getElementById("dirRecogida").value = "";
                    document.getElementById("dirEntrega").value = "";
                    cargarPedidos(); // Recargar la lista en vivo de inmediato
                } else {
                    alert("⚠️ Error: " + JSON.stringify(data));
                }
            } catch (error) {
                console.error("Error de red:", error);
                alert("No se pudo conectar con el servidor FastAPI.");
            }
        });
    }
});

// Función para obtener y mostrar todos los pedidos desde FastAPI
async function cargarPedidos() {
    try {
        const res = await fetch(`${API_URL}/pedidos/`);
        const data = await res.json();
        
        const contenedor = document.getElementById("contenedorPedidos");
        contenedor.innerHTML = "";

        if (!data.pedidos || data.pedidos.length === 0) {
            contenedor.innerHTML = "<p style='color: var(--text-muted);'>No hay pedidos registrados.</p>";
            return;
        }

        data.pedidos.forEach(pedido => {
            let badgeClass = "badge-pendiente";
            if (pedido.estado === "En camino") badgeClass = "badge-en-camino";
            if (pedido.estado === "Entregado") badgeClass = "badge-entregado";

            // Renderizamos la tarjeta incluyendo botones de acción rápidos
            contenedor.innerHTML += `
                <div class="order-card">
                    <div class="order-header">
                        <span class="order-id">Pedido #${pedido.id_pedido}</span>
                        <span class="badge ${badgeClass}">${pedido.estado}</span>
                    </div>
                    <div class="order-info">
                        <p><i class="fa-solid fa-user"></i> <strong>Cliente:</strong> ${pedido.cliente}</p>
                        <p><i class="fa-solid fa-location-dot"></i> <strong>Recogida:</strong> ${pedido.direccion_recogida}</p>
                        <p><i class="fa-solid fa-route"></i> <strong>Entrega:</strong> ${pedido.direccion_entrega}</p>
                        <p><i class="fa-solid fa-dollar-sign"></i> <strong>Valor:</strong> $${pedido.valor_servicio.toLocaleString()}</p>
                    </div>
                    <div class="order-actions">
                        <button class="btn-action btn-camino" onclick="cambiarEstado(${pedido.id_pedido}, 'En camino')">
                            <i class="fa-solid fa-motorcycle"></i> En camino
                        </button>
                        <button class="btn-action btn-entregado" onclick="cambiarEstado(${pedido.id_pedido}, 'Entregado')">
                            <i class="fa-solid fa-check-circle"></i> Entregado
                        </button>
                    </div>
                </div>
            `;
        });
    } catch (error) {
        console.error("Error al cargar pedidos:", error);
    }
}

// Función para cambiar el estado de un pedido al hacer clic en los botones
async function cambiarEstado(idPedido, nuevoEstado) {
    try {
        const res = await fetch(`${API_URL}/pedidos/${idPedido}/estado`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ nuevo_estado: nuevoEstado })
        });

        if (res.ok) {
            cargarPedidos(); // Refresca automáticamente las tarjetas
        } else {
            alert("No se pudo actualizar el estado.");
        }
    } catch (error) {
        console.error("Error de conexión:", error);
    }
}