"""Levanta el backend de Rapido Express y lo expone a internet con ngrok.

Uso:
    python iniciar_servidor.py

La primera vez debes configurar tu authtoken gratuito de ngrok (ver README
o el mensaje de error que aparece si falta). Después de eso, este script
imprime una URL publica que puedes compartir con tu equipo para que todos
prueben contra el mismo servidor y la misma base de datos.
"""
import threading
import time

import uvicorn
from pyngrok import ngrok

PUERTO = 8000
# Dominio fijo gratuito de tu cuenta ngrok (dashboard.ngrok.com > Dominios).
# Déjalo en None si prefieres una URL aleatoria distinta cada vez.
DOMINIO_NGROK = "shorty-prelaunch-explicit.ngrok-free.dev"


def _iniciar_uvicorn() -> None:
    uvicorn.run("main:app", host="0.0.0.0", port=PUERTO, log_level="info")


def main() -> None:
    threading.Thread(target=_iniciar_uvicorn, daemon=True).start()
    time.sleep(1.5)

    opciones = {"domain": DOMINIO_NGROK} if DOMINIO_NGROK else {}
    tunel = ngrok.connect(PUERTO, "http", **opciones)
    print("\n" + "=" * 60)
    print(f"Servidor local:   http://127.0.0.1:{PUERTO}/")
    print(f"URL publica (compartir con el equipo): {tunel.public_url}")
    print("=" * 60 + "\n")
    print("Deja esta ventana abierta. Presiona Ctrl+C para detener todo.\n")

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nCerrando túnel y servidor...")
        ngrok.disconnect(tunel.public_url)
        ngrok.kill()


if __name__ == "__main__":
    main()
