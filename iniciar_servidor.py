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
from pathlib import Path

import uvicorn
from pyngrok import conf, ngrok

PUERTO = 8000
# Dominio fijo gratuito de tu cuenta ngrok (dashboard.ngrok.com > Dominios).
# Déjalo en None si prefieres una URL aleatoria distinta cada vez.
DOMINIO_NGROK = "shorty-prelaunch-explicit.ngrok-free.dev"

# El Python de la Microsoft Store virtualiza AppData\Local y eso rompe la
# ruta donde pyngrok espera encontrar el binario descargado. Para evitarlo,
# guardamos el binario y la config de ngrok dentro del propio proyecto.
BASE_DIR = Path(__file__).resolve().parent
NGROK_DIR = BASE_DIR / ".ngrok"
NGROK_DIR.mkdir(exist_ok=True)
conf.set_default(conf.PyngrokConfig(
    ngrok_path=str(NGROK_DIR / "ngrok.exe"),
    config_path=str(NGROK_DIR / "ngrok.yml"),
))


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
