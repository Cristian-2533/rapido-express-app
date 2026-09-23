const API_URL = window.location.origin;

async function parseJsonSeguro(response) {
    const texto = await response.text();
    if (!texto) {
        throw new Error(`El servidor respondió sin contenido (HTTP ${response.status}).`);
    }
    try {
        return JSON.parse(texto);
    } catch {
        throw new Error(`Respuesta no válida del servidor (HTTP ${response.status}).`);
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
    document.getElementById("linkOlvideContrasena")?.addEventListener("click", (event) => {
        event.preventDefault();
        alert("Por seguridad, las contraseñas no se recuperan por aquí. Contacta a tu administrador para que te restablezca el acceso desde el panel de administración.");
    });
    document.getElementById("linkMostrarLogin")?.addEventListener("click", (event) => {
        event.preventDefault();
        registerView.style.display = "none";
        loginView.style.display = "block";
    });
    const grupoZona = document.getElementById("grupoRegZona");
    document.querySelectorAll('input[name="regRol"]').forEach((radio) => radio.addEventListener("change", () => {
        grupoZona.style.display = radio.value === "repartidor" ? "block" : "none";
    }));
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
            const data = await parseJsonSeguro(response);
            if (!response.ok) throw new Error(data.detail || "No se pudo iniciar sesión.");
            sessionStorage.setItem("usuario", JSON.stringify(data.usuario));
            sessionStorage.setItem("token", data.token);
            // Guardar en localStorage para persistencia como PWA
            localStorage.setItem("usuario", JSON.stringify(data.usuario));
            localStorage.setItem("token", data.token);
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
        const rolElegido = document.querySelector('input[name="regRol"]:checked').value;
        const endpoint = rolElegido === "repartidor" ? "/repartidores/registro" : "/clientes/";
        const payload = {
            nombre: document.getElementById("regNombre").value.trim(),
            telefono: document.getElementById("regTelefono").value.trim(),
            correo: document.getElementById("regCorreo").value.trim(),
            password: document.getElementById("regPassword").value,
        };
        if (rolElegido === "repartidor") payload.zona = document.getElementById("regZona").value.trim();
        try {
            const response = await fetch(`${API_URL}${endpoint}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await parseJsonSeguro(response);
            if (!response.ok) throw new Error(data.detail || data.error || "No se pudo registrar.");
            alert("Cuenta creada con éxito. Ya puedes iniciar sesión.");
            registerForm.reset();
            registerView.style.display = "none";
            loginView.style.display = "block";
        } catch (error) {
            alert(error.message);
        }
    });
});
