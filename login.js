const API_URL = "http://127.0.0.1:8000";

document.addEventListener("DOMContentLoaded", () => {
    const btnToggle = document.getElementById("btnTogglePassword");
    const inputPassword = document.getElementById("password");
    const formLogin = document.getElementById("formLogin");
    const formRegistro = document.getElementById("formRegistro");

    const vistaLogin = document.getElementById("vistaLogin");
    const vistaRegistro = document.getElementById("vistaRegistro");
    const linkMostrarRegistro = document.getElementById("linkMostrarRegistro");
    const linkMostrarLogin = document.getElementById("linkMostrarLogin");

    // 1. Mostrar u ocultar la contraseña
    if (btnToggle && inputPassword) {
        btnToggle.addEventListener("click", () => {
            if (inputPassword.type === "password") {
                inputPassword.type = "text";
                btnToggle.textContent = "Ocultar";
            } else {
                inputPassword.type = "password";
                btnToggle.textContent = "Mostrar";
            }
        });
    }

    // 2. Alternar entre Vista Login y Vista Registro
    if (linkMostrarRegistro && linkMostrarLogin) {
        linkMostrarRegistro.addEventListener("click", (e) => {
            e.preventDefault();
            vistaLogin.style.display = "none";
            vistaRegistro.style.display = "block";
        });

        linkMostrarLogin.addEventListener("click", (e) => {
            e.preventDefault();
            vistaRegistro.style.display = "none";
            vistaLogin.style.display = "block";
        });
    }

    // 3. Redirección según el rol en Login
    if (formLogin) {
        formLogin.addEventListener("submit", (e) => {
            e.preventDefault();
            
            const rolSeleccionado = document.getElementById("rol").value;

            if (rolSeleccionado === "administrador") {
                window.location.href = "dashboard.html?v=2";   // Panel general / Administrador
            } else if (rolSeleccionado === "repartidor") {
                window.location.href = "repartidor.html";
            } else if (rolSeleccionado === "cliente") {
                window.location.href = "cliente.html";
            }
        });
    }

    // 4. Registrar un nuevo cliente en el backend FastAPI
    if (formRegistro) {
        formRegistro.addEventListener("submit", async (e) => {
            e.preventDefault();

            const nuevoCliente = {
                nombre: document.getElementById("regNombre").value,
                telefono: document.getElementById("regTelefono").value,
                correo: document.getElementById("regCorreo").value
            };

            try {
                const res = await fetch(`${API_URL}/clientes/`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(nuevoCliente)
                });

                const data = await res.json();

                if (res.ok) {
                    alert("¡Registro exitoso! Ahora puedes ingresar.");
                    formRegistro.reset();
                    vistaRegistro.style.display = "none";
                    vistaLogin.style.display = "block";
                } else {
                    alert("⚠️ Error al registrar: " + JSON.stringify(data));
                }
            } catch (error) {
                console.error("Error de conexión:", error);
                alert("No se pudo conectar con el servidor para registrar el usuario.");
            }
        });
    }
});