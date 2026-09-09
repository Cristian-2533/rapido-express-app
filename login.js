const API_URL = window.location.origin;

document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.getElementById("btnTogglePassword");
    const password = document.getElementById("password");
    const form = document.getElementById("formLogin");
    if (toggle && password) {
        toggle.addEventListener("click", () => {
            password.type = password.type === "password" ? "text" : "password";
            toggle.textContent = password.type === "password" ? "Mostrar" : "Ocultar";
        });
    }
    form?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const button = form.querySelector("button[type=submit]");
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
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || "No se pudo iniciar sesión.");
            sessionStorage.setItem("usuario", JSON.stringify(data.usuario));
            const destino = data.usuario.rol === "administrador"
                ? "dashboard.html" : data.usuario.rol === "repartidor" ? "repartidor.html" : "cliente.html";
            window.location.href = destino;
        } catch (error) {
            alert(error.message);
        } finally {
            button.disabled = false;
        }
    });
});
