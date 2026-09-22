# Rápido Express

Sistema de gestión de pedidos y entregas. Backend en FastAPI + SQLite, frontend en HTML/CSS/JS servido por el mismo backend.

## 1. Primer arranque (cada persona del equipo, una sola vez)

1. Cloná el repositorio y entrá a la carpeta del proyecto.
2. Instalá las dependencias:
   ```
   pip install -r requirements.txt
   ```
3. Levantá el servidor:
   ```
   uvicorn main:app --reload
   ```
4. Abrí el navegador en **http://127.0.0.1:8000/** (no `0.0.0.0:8000`, esa dirección no se puede visitar directamente).

Al arrancar por primera vez, `main.py` crea automáticamente el archivo `rapido_express.db` (SQLite) con 3 cuentas de prueba:

| Correo | Rol | Contraseña |
|---|---|---|
| `operaciones@rapidoexpress.com` | administrador | `12345678` |
| `juanito@rapidoexpress.com` | repartidor | `12345678` |
| `cliente@rapidoexpress.com` | cliente | `12345678` |

**Importante:** `rapido_express.db` está en `.gitignore` — cada persona tiene su propia base de datos local, independiente de la de los demás. Si cada quien corre su propio servidor, no van a ver los mismos pedidos/clientes que el resto del equipo.

## 2. Trabajar todos sobre los mismos datos (recomendado para pruebas en equipo)

Si el equipo está en redes distintas (cada quien en su casa), usamos **ngrok** para exponer el servidor de una sola persona a internet, y todos se conectan a esa URL en vez de correr su propia copia.

Configuración (una sola vez, en la máquina que va a compartir el servidor):

1. Crear cuenta gratis en https://dashboard.ngrok.com/signup
2. Copiar el authtoken desde https://dashboard.ngrok.com/get-started/your-authtoken
3. Configurarlo localmente:
   ```
   python -c "from pyngrok import ngrok; ngrok.set_auth_token('TU_TOKEN_AQUI')"
   ```
4. En `iniciar_servidor.py`, poné tu dominio fijo gratuito (lo ves en el dashboard, sección "Dominios") en la constante `DOMINIO_NGROK`.

Uso diario (solo la persona que comparte el servidor):
```
python iniciar_servidor.py
```
Esto levanta el backend y el túnel de ngrok juntos, e imprime la URL pública para pasarle al resto del equipo. Esa URL es fija (no cambia entre reinicios) mientras uses el dominio de tu cuenta ngrok.

El resto del equipo simplemente abre esa URL en el navegador e inicia sesión con cualquiera de las 3 cuentas de la tabla de arriba — no necesitan clonar nada ni instalar dependencias para *probar* la app, solo para *desarrollarla*.

## 3. Despliegue permanente (sin depender de tu laptop ni de ngrok)

Para tener una URL fija que funcione siempre, sin que dependa de que tu equipo esté prendido, se puede desplegar gratis en **Render** (https://render.com):

1. Sube este repositorio a GitHub (si no lo has hecho ya).
2. Crea una cuenta gratis en https://render.com e inicia sesión con GitHub.
3. En el dashboard, click en **New +** → **Blueprint**, y selecciona este repositorio. Render detecta automáticamente el archivo `render.yaml` incluido y configura todo solo (build command, start command, y una `RAPIDO_EXPRESS_SECRET` aleatoria y segura).
4. Click en **Apply** / **Deploy**. En unos minutos te da una URL pública tipo `https://rapido-express-api.onrender.com`.
5. Esa URL sirve el login, los paneles y la API — igual que con ngrok, pero permanente. El `manifest.json` sigue funcionando igual para instalar la app en el celular desde esa URL.

**Ten en cuenta (plan gratuito de Render):**
- El servicio "duerme" tras ~15 minutos sin tráfico y tarda unos 30-60 segundos en despertar con la primera visita — normal en el plan gratis, no es un error.
- El disco donde vive `rapido_express.db` se reinicia cada vez que subes código nuevo (cada redeploy vuelve a sembrar las 3 cuentas de prueba y borra los datos reales que se hayan cargado). Para un proyecto de universidad en fase de demo esto normalmente no es un problema; si más adelante necesitas que los datos sobrevivan entre despliegues, hay que agregar un disco persistente de pago o migrar a una base de datos gestionada aparte.

## Notas

- `SECRET_KEY` (usada para firmar los tokens de sesión) tiene un valor por defecto en `main.py` pensado solo para desarrollo. Para un uso más serio, definila como variable de entorno `RAPIDO_EXPRESS_SECRET`.
- Si Windows te pide permiso de firewall al arrancar `uvicorn`, aceptalo para que el resto del equipo pueda conectarse.
