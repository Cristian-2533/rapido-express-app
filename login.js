const API_URL = ["5500", "5501"].includes(window.location.port)
    ? "http://127.0.0.1:8000"
    : window.location.origin;

async function readResponse(response) {
    const text = await response.text();
    if (!text) {
        throw new Error(`La API no devolvió respuesta (HTTP ${response.status}). Verifica que FastAPI esté ejecutándose en ${API_URL}.`);
    }
    try {
        return JSON.parse(text);
    } catch {
        throw new Error(`La API devolvió una respuesta inválida (HTTP ${response.status}).`);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.getElementById("btnTogglePassword");
    const password = document.getElementById("password");
    const loginForm = document.getElementById("formLogin");
    const registerForm = document.getElementById("formRegistro");
    const loginView = document.getElementById("vistaLogin");
    const registerView = document.getElementById("vistaRegistro");

    toggle?.addEventListener("click", () => {
        password.type = password.type === "password" ? "text" : "password";
        toggle.textContent = password.type === "password" ? "Mostrar" : "Ocultar";
    });
    document.getElementById("linkMostrarRegistro")?.addEventListener("click", (event) => {
        event.preventDefault();
        loginView.style.display = "none";
        registerView.style.display = "block";
    });
    document.getElementById("linkMostrarLogin")?.addEventListener("click", (event) => {
        event.preventDefault();
        registerView.style.display = "none";
        loginView.style.display = "block";
    });
    loginForm?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const button = loginForm.querySelector("button[type=submit]");
        button.disabled = true;
        try {
            const response = await fetch(`${API_URL}/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    correo: document.getElementById("correo").value.trim(),
                    password: password.value,
                    rol: document.getElementById("rol").value
                })
            });
            const data = await readResponse(response);
            if (!response.ok) throw new Error(data.detail || "No se pudo iniciar sesión.");
            sessionStorage.setItem("usuario", JSON.stringify(data.usuario));
            window.location.href = data.usuario.rol === "administrador"
                ? "dashboard.html" : data.usuario.rol === "repartidor" ? "repartidor.html" : "cliente.html";
        } catch (error) {
            alert(error.message);
        } finally {
            button.disabled = false;
        }
    });
    registerForm?.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
            const response = await fetch(`${API_URL}/clientes/`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    nombre: document.getElementById("regNombre").value.trim(),
                    telefono: document.getElementById("regTelefono").value.trim(),
                    correo: document.getElementById("regCorreo").value.trim()
                })
            });
            const data = await readResponse(response);
            if (!response.ok) throw new Error(data.detail || data.error || "No se pudo registrar.");
            alert("Registro exitoso. El administrador debe activar sus credenciales.");
            registerForm.reset();
            registerView.style.display = "none";
            loginView.style.display = "block";
        } catch (error) {
            alert(error.message);
        }
    });
});
