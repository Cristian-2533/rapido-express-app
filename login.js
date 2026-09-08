const API_URL = "http://127.0.0.1:8000";

document.addEventListener("DOMContentLoaded", () => {
    const btnToggle = document.getElementById("btnTogglePassword");
    const inputPassword = document.getElementById("password");
    const formLogin = document.getElementById("formLogin");

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

    // 2. Redirección según el rol seleccionado al presionar "Ingresar"
    if (formLogin) {
        formLogin.addEventListener("submit", (e) => {
            e.preventDefault();
            
            const rolSeleccionado = document.getElementById("rol").value;

            if (rolSeleccionado === "administrador") {
                window.location.href = "dashboard.html?v=2";   // Panel general / Administrador
            } else if (rolSeleccionado === "repartidor") {
                window.location.href = "repartidor.html"; // Vista de Repartidor
            } else if (rolSeleccionado === "cliente") {
                window.location.href = "cliente.html";    // Vista de Cliente
            }
        });
    }
});