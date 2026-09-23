import base64
import csv
import hashlib
import hmac
import io
import logging
import os
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATABASE_PATH = Path(os.getenv("RAPIDO_EXPRESS_DB", BASE_DIR / "rapido_express.db"))

SECRET_KEY = os.getenv("RAPIDO_EXPRESS_SECRET")
if not SECRET_KEY:
    if os.getenv("APP_ENV") == "production":
        raise RuntimeError("RAPIDO_EXPRESS_SECRET debe estar definido en producción.")
    SECRET_KEY = secrets.token_hex(32)
    print(
        "ADVERTENCIA: RAPIDO_EXPRESS_SECRET no está definida; se generó una clave aleatoria de desarrollo. "
        "Defínela como variable de entorno antes de exponer este servidor a otras personas."
    )
SECRET_KEY_BYTES = SECRET_KEY.encode()
PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1)
TOKEN_TTL_SECONDS = 8 * 60 * 60
ESTADOS_PEDIDO = ["Pendiente", "Asignado", "En camino", "Entregado", "Cancelado"]
PORCENTAJE_REPARTIDOR = float(os.getenv("RAPIDO_EXPRESS_COMISION_REPARTIDOR", "0.70"))
app = FastAPI(title="Rápido Express API", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
def manejador_errores_no_controlados(request: Request, exc: Exception) -> JSONResponse:
    logging.exception("Error no controlado en %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Error interno del servidor."})


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verificar_password(password: str, stored_hash: str) -> bool:
    try:
        if stored_hash.startswith("$argon2"):
            return PASSWORD_HASHER.verify(stored_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False
    return hmac.compare_digest(stored_hash, hashlib.sha256(password.encode()).hexdigest())


def conectar_db() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def inicializar_db() -> None:
    with conectar_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                correo TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                rol TEXT NOT NULL CHECK (rol IN ('administrador', 'repartidor', 'cliente')),
                activo INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS clientes (
                id_cliente INTEGER PRIMARY KEY AUTOINCREMENT,
                id_usuario INTEGER UNIQUE,
                nombre TEXT NOT NULL,
                telefono TEXT NOT NULL,
                correo TEXT NOT NULL,
                direccion TEXT,
                nombre_local TEXT,
                FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
            );
            CREATE TABLE IF NOT EXISTS repartidores (
                id_repartidor INTEGER PRIMARY KEY AUTOINCREMENT,
                id_usuario INTEGER NOT NULL UNIQUE,
                telefono TEXT NOT NULL,
                disponible INTEGER NOT NULL DEFAULT 1,
                zona TEXT NOT NULL DEFAULT '',
                tipo_vehiculo TEXT NOT NULL DEFAULT 'moto',
                placa_vehiculo TEXT,
                FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
            );
            CREATE TABLE IF NOT EXISTS pedidos (
                id_pedido INTEGER PRIMARY KEY AUTOINCREMENT,
                id_cliente INTEGER NOT NULL,
                id_repartidor INTEGER,
                direccion_recogida TEXT NOT NULL,
                nombre_local_recogida TEXT,
                direccion_entrega TEXT NOT NULL,
                hora_recogida_programada TEXT,
                fecha_hora TEXT NOT NULL,
                valor_servicio REAL NOT NULL CHECK (valor_servicio >= 0),
                metodo_pago TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'Pendiente',
                tiempo_espera_min INTEGER,
                tiempo_recogida_min INTEGER,
                observaciones TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente),
                FOREIGN KEY (id_repartidor) REFERENCES repartidores(id_repartidor)
            );
            CREATE TABLE IF NOT EXISTS historial_pedidos (
                id_historial INTEGER PRIMARY KEY AUTOINCREMENT,
                id_pedido INTEGER NOT NULL,
                estado TEXT NOT NULL,
                fecha_hora TEXT NOT NULL,
                id_usuario INTEGER,
                FOREIGN KEY (id_pedido) REFERENCES pedidos(id_pedido),
                FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
            );
            """
        )
        _migrar_perfiles_usuario(db)
        if db.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone() is None:
            password = hash_password("12345678")
            db.execute(
                "INSERT INTO usuarios (nombre, correo, password_hash, rol) VALUES (?, ?, ?, ?)",
                ("Administrador", "operaciones@rapidoexpress.com", password, "administrador"),
            )
            db.execute(
                "INSERT INTO usuarios (nombre, correo, password_hash, rol) VALUES (?, ?, ?, ?)",
                ("Juanito Pérez", "juanito@rapidoexpress.com", password, "repartidor"),
            )
            db.execute(
                "INSERT INTO usuarios (nombre, correo, password_hash, rol) VALUES (?, ?, ?, ?)",
                ("Cliente demo", "cliente@rapidoexpress.com", password, "cliente"),
            )
            driver_user = db.execute(
                "SELECT id_usuario FROM usuarios WHERE correo = ?",
                ("juanito@rapidoexpress.com",),
            ).fetchone()
            db.execute(
                """
                INSERT INTO repartidores
                    (id_usuario, telefono, disponible, zona, tipo_vehiculo, placa_vehiculo, latitude, longitude)
                VALUES (?, ?, 1, ?, ?, ?, ?, ?)
                """,
                (driver_user["id_usuario"], "3000000000", "Zona norte", "moto", "DEMO123", 4.6097, -74.0817),
            )
            db.execute(
                """
                INSERT INTO clientes (nombre, telefono, correo, direccion, nombre_local)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("Cliente demo", "3100000000", "cliente@rapidoexpress.com", "Calle 1 # 1-1", None),
            )
            client_user = db.execute(
                "SELECT id_usuario FROM usuarios WHERE correo = ?",
                ("cliente@rapidoexpress.com",),
            ).fetchone()
            db.execute(
                "UPDATE clientes SET id_usuario = ? WHERE correo = ?",
                (client_user["id_usuario"], "cliente@rapidoexpress.com"),
            )


def _migrar_perfiles_usuario(db: sqlite3.Connection) -> None:
    """Añade GPS y campos de perfil sin reconstruir tablas ni perder datos."""
    clientes = {
        fila["name"]
        for fila in db.execute("PRAGMA table_info(clientes)").fetchall()
    }
    if "direccion" not in clientes:
        db.execute("ALTER TABLE clientes ADD COLUMN direccion TEXT")
    if "nombre_local" not in clientes:
        db.execute("ALTER TABLE clientes ADD COLUMN nombre_local TEXT")

    columnas = {
        fila["name"]
        for fila in db.execute("PRAGMA table_info(repartidores)").fetchall()
    }
    if "latitude" not in columnas:
        db.execute("ALTER TABLE repartidores ADD COLUMN latitude REAL")
    if "longitude" not in columnas:
        db.execute("ALTER TABLE repartidores ADD COLUMN longitude REAL")
    if "ultima_actualizacion_gps" not in columnas:
        db.execute("ALTER TABLE repartidores ADD COLUMN ultima_actualizacion_gps TEXT")
    if "tipo_vehiculo" not in columnas:
        db.execute("ALTER TABLE repartidores ADD COLUMN tipo_vehiculo TEXT NOT NULL DEFAULT 'moto'")
    if "placa_vehiculo" not in columnas:
        db.execute("ALTER TABLE repartidores ADD COLUMN placa_vehiculo TEXT")

    pedidos = {
        fila["name"]
        for fila in db.execute("PRAGMA table_info(pedidos)").fetchall()
    }
    if "nombre_local_recogida" not in pedidos:
        db.execute("ALTER TABLE pedidos ADD COLUMN nombre_local_recogida TEXT")
    if "hora_recogida_programada" not in pedidos:
        db.execute("ALTER TABLE pedidos ADD COLUMN hora_recogida_programada TEXT")

    # Compatibilidad con una instalación que hubiera creado los nombres antiguos.
    if "latitud" in columnas:
        db.execute(
            "UPDATE repartidores SET latitude = latitud "
            "WHERE latitude IS NULL AND latitud IS NOT NULL"
        )
    if "longitud" in columnas:
        db.execute(
            "UPDATE repartidores SET longitude = longitud "
            "WHERE longitude IS NULL AND longitud IS NOT NULL"
        )

    db.execute(
        """
        UPDATE repartidores
        SET latitude = 4.6097,
            longitude = -74.0817,
            ultima_actualizacion_gps = ?
        WHERE (latitude IS NULL OR longitude IS NULL)
          AND id_usuario = (
              SELECT id_usuario FROM usuarios WHERE correo = ?
          )
        """,
        (datetime.now(timezone.utc).isoformat(timespec="seconds"), "juanito@rapidoexpress.com"),
    )


@app.on_event("startup")
def startup() -> None:
    inicializar_db()


class LoginRequest(BaseModel):
    correo: str
    password: str
    rol: str


class Cliente(BaseModel):
    nombre: str = Field(min_length=2)
    telefono: str = Field(min_length=7)
    correo: str


class RegistroCliente(BaseModel):
    nombre: str = Field(min_length=2)
    telefono: str = Field(min_length=7)
    correo: str
    password: str = Field(min_length=6)
    direccion: str = Field(min_length=5)
    nombre_local: Optional[str] = None


class RegistroRepartidor(BaseModel):
    nombre: str = Field(min_length=2)
    telefono: str = Field(min_length=7)
    correo: str
    password: str = Field(min_length=6)
    zona: str = ""
    tipo_vehiculo: Literal["moto", "bicicleta", "auto"] = "moto"
    placa_vehiculo: str = Field(min_length=3)


class RegistroUsuario(BaseModel):
    tipo_usuario: Literal["cliente", "repartidor"]
    nombre: str = Field(min_length=2)
    telefono: str = Field(min_length=7)
    correo: str
    password: str = Field(min_length=6)
    direccion: Optional[str] = None
    nombre_local: Optional[str] = None
    zona: str = ""
    tipo_vehiculo: Literal["moto", "bicicleta", "auto"] = "moto"
    placa_vehiculo: Optional[str] = None

    @model_validator(mode="after")
    def validar_datos_por_rol(self) -> "RegistroUsuario":
        if self.tipo_usuario == "cliente" and not self.direccion:
            raise ValueError("La dirección es obligatoria para clientes.")
        if self.tipo_usuario == "repartidor" and not self.placa_vehiculo:
            raise ValueError("La placa del vehículo es obligatoria para repartidores.")
        return self


class Pedido(BaseModel):
    id_cliente: int
    id_repartidor: Optional[int] = None
    direccion_recogida: str = Field(min_length=3)
    nombre_local_recogida: Optional[str] = None
    direccion_entrega: str = Field(min_length=3)
    hora_recogida_programada: Optional[str] = None
    valor_servicio: float = Field(ge=0)
    metodo_pago: str = Field(min_length=2)
    tiempo_espera_min: Optional[int] = Field(default=None, ge=0)
    tiempo_recogida_min: Optional[int] = Field(default=None, ge=0)
    observaciones: str = ""


class PedidoCliente(BaseModel):
    nombre_local_recogida: str = Field(min_length=2)
    direccion_recogida: str = Field(min_length=3)
    direccion_entrega: str = Field(min_length=3)
    hora_recogida_programada: Optional[str] = None
    valor_servicio: float = Field(default=0, ge=0)
    metodo_pago: str = Field(default="Efectivo", min_length=2)
    tiempo_espera_min: Optional[int] = Field(default=None, ge=0)
    observaciones: str = ""


class ActualizarEstado(BaseModel):
    nuevo_estado: str = Field(min_length=2)

    @field_validator("nuevo_estado")
    @classmethod
    def estado_valido(cls, value: str) -> str:
        if value not in ESTADOS_PEDIDO:
            raise ValueError(f"Estado inválido. Use uno de: {', '.join(ESTADOS_PEDIDO)}.")
        estados_permitidos = ESTADOS_PEDIDO + ["En espera", "Cancelado por el cliente", "Recibido con conformidad"]
        if value not in estados_permitidos:
            raise ValueError(f"Estado inválido. Use uno de: {', '.join(estados_permitidos)}.")
        return value


class ActualizarPedido(BaseModel):
    direccion_recogida: str = Field(min_length=3)
    direccion_entrega: str = Field(min_length=3)
    valor_servicio: float = Field(ge=0)
    metodo_pago: str = Field(min_length=2)
    tiempo_espera_min: Optional[int] = Field(default=None, ge=0)
    tiempo_recogida_min: Optional[int] = Field(default=None, ge=0)
    observaciones: str = ""


class ActualizarDisponibilidad(BaseModel):
    disponible: bool


class AsignarRepartidor(BaseModel):
    id_repartidor: int


class NuevaPassword(BaseModel):
    password: str = Field(min_length=6)


def generar_token(id_usuario: int, rol: str) -> str:
    expira = int(time.time()) + TOKEN_TTL_SECONDS
    payload = f"{id_usuario}:{rol}:{expira}"
    firma = hmac.new(SECRET_KEY_BYTES, payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(payload.encode()).decode() + "." + firma


def verificar_token(token: str) -> dict:
    try:
        payload_b64, firma = token.split(".", 1)
        payload = base64.urlsafe_b64decode(payload_b64.encode()).decode()
        firma_esperada = hmac.new(SECRET_KEY_BYTES, payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(firma, firma_esperada):
            raise ValueError("Firma inválida")
        id_usuario_str, rol, expira_str = payload.split(":", 2)
        if int(expira_str) < int(time.time()):
            raise ValueError("Token expirado")
    except (ValueError, IndexError):
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada.")
    return {"id_usuario": int(id_usuario_str), "rol": rol}


def usuario_actual(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Debe iniciar sesión.")
    return verificar_token(authorization.removeprefix("Bearer ").strip())


class Ubicacion(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    latitude: float = Field(
        ge=-90,
        le=90,
        validation_alias=AliasChoices("latitude", "latitud"),
    )
    longitude: float = Field(
        ge=-180,
        le=180,
        validation_alias=AliasChoices("longitude", "longitud"),
    )


def _actualizar_ubicacion(
    db: sqlite3.Connection, id_repartidor: int, datos: Ubicacion
) -> dict:
    ahora_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cursor = db.execute(
        """
        UPDATE repartidores
        SET latitude = ?, longitude = ?, ultima_actualizacion_gps = ?
        WHERE id_repartidor = ?
        """,
        (datos.latitude, datos.longitude, ahora_utc, id_repartidor),
    )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Repartidor no encontrado.")
    return {
        "id_repartidor": id_repartidor,
        "latitude": datos.latitude,
        "longitude": datos.longitude,
        "ultima_actualizacion_gps": ahora_utc,
    }


def _id_repartidor_del_usuario(db: sqlite3.Connection, id_usuario: int) -> int:
    repartidor = db.execute(
        "SELECT id_repartidor FROM repartidores WHERE id_usuario = ? AND EXISTS "
        "(SELECT 1 FROM usuarios WHERE id_usuario = ? AND activo = 1)",
        (id_usuario, id_usuario),
    ).fetchone()
    if not repartidor:
        raise HTTPException(status_code=404, detail="Repartidor no encontrado.")
    return repartidor["id_repartidor"]


@app.put("/repartidores/{id_repartidor}/ubicacion")
def actualizar_ubicacion_por_id(
    id_repartidor: int,
    datos: Ubicacion,
    actual: dict = Depends(usuario_actual),
):
    exigir_rol(actual, "repartidor")
    with conectar_db() as db:
        propietario = db.execute(
            "SELECT id_repartidor FROM repartidores "
            "WHERE id_repartidor = ? AND id_usuario = ?",
            (id_repartidor, actual["id_usuario"]),
        ).fetchone()
        if not propietario:
            raise HTTPException(status_code=403, detail="No puede actualizar esta ubicación.")
        ubicacion = _actualizar_ubicacion(db, id_repartidor, datos)
    return {"mensaje": "Ubicación actualizada.", "repartidor": ubicacion}


@app.patch("/repartidores/ubicacion")
def actualizar_ubicacion(datos: Ubicacion, actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "repartidor")
    with conectar_db() as db:
        id_repartidor = _id_repartidor_del_usuario(db, actual["id_usuario"])
        ubicacion = _actualizar_ubicacion(db, id_repartidor, datos)
    return {"mensaje": "Ubicación actualizada.", "repartidor": ubicacion}


@app.get("/repartidores/ubicaciones")
def obtener_ubicaciones(actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador")
    with conectar_db() as db:
        rows = db.execute(
            """
            SELECT r.id_repartidor, u.nombre,
                   r.latitude, r.longitude,
                   r.latitude AS latitud, r.longitude AS longitud,
                   r.ultima_actualizacion_gps, r.disponible
            FROM repartidores r
            JOIN usuarios u ON u.id_usuario = r.id_usuario
            WHERE r.latitude IS NOT NULL AND r.longitude IS NOT NULL
            """
        ).fetchall()
    return {"repartidores": [fila_dict(row) for row in rows]}


def exigir_rol(usuario: dict, *roles: str) -> None:
    if usuario["rol"] not in roles:
        raise HTTPException(status_code=403, detail="No tiene permisos para esta operación.")


def fila_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    return dict(row) if row else None


def _registrar_historial(db: sqlite3.Connection, id_pedido: int, estado: str, id_usuario: Optional[int]) -> None:
    db.execute(
        "INSERT INTO historial_pedidos (id_pedido, estado, fecha_hora, id_usuario) VALUES (?, ?, ?, ?)",
        (id_pedido, estado, datetime.now().isoformat(timespec="seconds"), id_usuario),
    )


def _desglosar_ganancia(valor_total: float) -> dict:
    return {
        "valor_total": valor_total,
        "comision_repartidor": round(valor_total * PORCENTAJE_REPARTIDOR, 2),
        "comision_empresa": round(valor_total * (1 - PORCENTAJE_REPARTIDOR), 2),
    }


@app.get("/")
def inicio():
    return FileResponse(STATIC_DIR / "login.html")


@app.post("/auth/login")
def login(datos: LoginRequest):
    with conectar_db() as db:
        usuario = db.execute(
            "SELECT id_usuario, nombre, correo, password_hash, rol FROM usuarios "
            "WHERE correo = ? AND rol = ? AND activo = 1",
            (datos.correo, datos.rol),
        ).fetchone()
    if not usuario or not verificar_password(datos.password, usuario["password_hash"]):
        raise HTTPException(status_code=401, detail="Correo, contraseña o rol inválidos.")
    return {
        "token": generar_token(usuario["id_usuario"], usuario["rol"]),
        "usuario": {
            "id_usuario": usuario["id_usuario"],
            "nombre": usuario["nombre"],
            "correo": usuario["correo"],
            "rol": usuario["rol"],
        },
    }


@app.post("/clientes/")
def crear_cliente(datos: RegistroCliente, actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador")
    password_hash = hash_password(datos.password)
    with conectar_db() as db:
        if db.execute("SELECT 1 FROM usuarios WHERE correo = ?", (datos.correo,)).fetchone():
            raise HTTPException(status_code=400, detail="Ya existe una cuenta con ese correo.")
        id_usuario = db.execute(
            "INSERT INTO usuarios (nombre, correo, password_hash, rol) VALUES (?, ?, ?, 'cliente')",
            (datos.nombre, datos.correo, password_hash),
        ).lastrowid
        cursor = db.execute(
            """
            INSERT INTO clientes
                (id_usuario, nombre, telefono, correo, direccion, nombre_local)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                id_usuario, datos.nombre, datos.telefono, datos.correo,
                datos.direccion, datos.nombre_local,
            ),
        )
    return {"mensaje": "Cuenta creada con éxito. Ya puedes iniciar sesión.", "id_cliente": cursor.lastrowid}


@app.get("/clientes/")
def obtener_clientes(
    q: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
    actual: dict = Depends(usuario_actual),
):
    exigir_rol(actual, "administrador")
    condicion = ""
    params: tuple = ()
    if q:
        condicion = " WHERE nombre LIKE ? OR telefono LIKE ? OR correo LIKE ?"
        comodin = f"%{q}%"
        params = (comodin, comodin, comodin)
    with conectar_db() as db:
        total = db.execute(f"SELECT COUNT(*) FROM clientes{condicion}", params).fetchone()[0]
        sql = f"SELECT * FROM clientes{condicion} ORDER BY nombre"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params = params + (max(1, min(limit, 100)), max(0, offset))
        clientes = [fila_dict(row) for row in db.execute(sql, params)]
    return {"total_clientes": total, "clientes": clientes, "limit": limit, "offset": offset}


@app.put("/clientes/{id_cliente}")
def editar_cliente(id_cliente: int, cliente: Cliente, actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador")
    with conectar_db() as db:
        cursor = db.execute(
            "UPDATE clientes SET nombre = ?, telefono = ?, correo = ? WHERE id_cliente = ?",
            (cliente.nombre, cliente.telefono, cliente.correo, id_cliente),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="El cliente no existe.")
    return {"mensaje": "Cliente actualizado correctamente."}


@app.put("/clientes/{id_cliente}/password")
def resetear_password_cliente(id_cliente: int, datos: NuevaPassword, actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador")
    with conectar_db() as db:
        cliente = db.execute("SELECT id_usuario FROM clientes WHERE id_cliente = ?", (id_cliente,)).fetchone()
        if not cliente:
            raise HTTPException(status_code=404, detail="El cliente no existe.")
        if not cliente["id_usuario"]:
            raise HTTPException(status_code=400, detail="Este cliente no tiene una cuenta de acceso asociada.")
        password_hash = hash_password(datos.password)
        db.execute(
            "UPDATE usuarios SET password_hash = ? WHERE id_usuario = ?",
            (password_hash, cliente["id_usuario"]),
        )
    return {"mensaje": "Contraseña actualizada correctamente."}


@app.delete("/clientes/{id_cliente}")
def eliminar_cliente(id_cliente: int, actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador")
    with conectar_db() as db:
        if not db.execute("SELECT 1 FROM clientes WHERE id_cliente = ?", (id_cliente,)).fetchone():
            raise HTTPException(status_code=404, detail="El cliente no existe.")
        if db.execute("SELECT 1 FROM pedidos WHERE id_cliente = ?", (id_cliente,)).fetchone():
            raise HTTPException(
                status_code=400, detail="No se puede eliminar un cliente con domicilios registrados."
            )
        db.execute("DELETE FROM clientes WHERE id_cliente = ?", (id_cliente,))
    return {"mensaje": "Cliente eliminado correctamente."}


def pedido_query(
    db: sqlite3.Connection,
    where: str = "",
    params: tuple = (),
    limit: Optional[int] = None,
    offset: int = 0,
) -> list[dict]:
    sql = (
        """
        SELECT p.*, c.nombre AS cliente, c.telefono AS telefono_cliente,
               c.correo AS correo_cliente, u.nombre AS repartidor
        FROM pedidos p
        JOIN clientes c ON c.id_cliente = p.id_cliente
        LEFT JOIN repartidores r ON r.id_repartidor = p.id_repartidor
        LEFT JOIN usuarios u ON u.id_usuario = r.id_usuario
        """
        + where
        + " ORDER BY p.id_pedido DESC"
    )
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = params + (max(1, min(limit, 100)), max(0, offset))
    rows = db.execute(sql, params).fetchall()
    return [fila_dict(row) for row in rows]


def pedido_count(db: sqlite3.Connection, where: str = "", params: tuple = ()) -> int:
    sql = (
        "SELECT COUNT(*) FROM pedidos p JOIN clientes c ON c.id_cliente = p.id_cliente" + where
    )
    return db.execute(sql, params).fetchone()[0]


def pedido_condiciones(estado: Optional[str], q: Optional[str]) -> tuple[str, tuple]:
    condiciones = []
    params: list = []
    if estado:
        condiciones.append("p.estado = ?")
        params.append(estado)
    if q:
        condiciones.append("(c.nombre LIKE ? OR CAST(p.id_pedido AS TEXT) LIKE ?)")
        comodin = f"%{q}%"
        params.extend([comodin, comodin])
    where = " WHERE " + " AND ".join(condiciones) if condiciones else ""
    return where, tuple(params)


@app.post("/pedidos/")
def crear_pedido(pedido: Pedido, actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador")
    with conectar_db() as db:
        if not db.execute("SELECT 1 FROM clientes WHERE id_cliente = ?", (pedido.id_cliente,)).fetchone():
            raise HTTPException(status_code=404, detail="El cliente no existe.")
        cursor = db.execute(
            """
            INSERT INTO pedidos
            (id_cliente, id_repartidor, direccion_recogida, direccion_entrega, fecha_hora,
             nombre_local_recogida, hora_recogida_programada, valor_servicio, metodo_pago,
             estado, tiempo_espera_min, tiempo_recogida_min, observaciones)
            VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, 'Pendiente', ?, ?, ?)
            """,
            (
                pedido.id_cliente, pedido.direccion_recogida, pedido.direccion_entrega,
                datetime.now().isoformat(timespec="seconds"), pedido.nombre_local_recogida,
                pedido.hora_recogida_programada, pedido.valor_servicio, pedido.metodo_pago,
                pedido.tiempo_espera_min, pedido.tiempo_recogida_min, pedido.observaciones,
            ),
        )
        _registrar_historial(db, cursor.lastrowid, "Pendiente", actual["id_usuario"])
    return {"mensaje": "Domicilio registrado con éxito.", "id_pedido": cursor.lastrowid, "estado": "Pendiente"}


def _cliente_id_del_usuario(db: sqlite3.Connection, id_usuario: int) -> int:
    cliente = db.execute(
        "SELECT id_cliente FROM clientes WHERE id_usuario = ?",
        (id_usuario,),
    ).fetchone()
    if not cliente:
        raise HTTPException(status_code=404, detail="No existe un perfil de cliente.")
    return cliente["id_cliente"]


@app.post("/clientes/me/pedidos")
def crear_pedido_cliente(
    pedido: PedidoCliente, actual: dict = Depends(usuario_actual)
):
    exigir_rol(actual, "cliente")
    with conectar_db() as db:
        id_cliente = _cliente_id_del_usuario(db, actual["id_usuario"])
        cursor = db.execute(
            """
            INSERT INTO pedidos
                (id_cliente, id_repartidor, direccion_recogida,
                 nombre_local_recogida, direccion_entrega, fecha_hora,
                 hora_recogida_programada, valor_servicio, metodo_pago,
                 estado, tiempo_espera_min, observaciones)
            VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, 'Pendiente', ?, ?)
            """,
            (
                id_cliente, pedido.direccion_recogida, pedido.nombre_local_recogida,
                pedido.direccion_entrega, datetime.now().isoformat(timespec="seconds"),
                pedido.hora_recogida_programada, pedido.valor_servicio, pedido.metodo_pago,
                pedido.tiempo_espera_min, pedido.observaciones,
            ),
        )
        _registrar_historial(db, cursor.lastrowid, "Pendiente", actual["id_usuario"])
    return {
        "mensaje": "Solicitud creada. El administrador asignará un domiciliario.",
        "id_pedido": cursor.lastrowid,
        "estado": "Pendiente",
    }


@app.get("/clientes/me/pedidos")
def obtener_pedidos_cliente(actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "cliente")
    with conectar_db() as db:
        id_cliente = _cliente_id_del_usuario(db, actual["id_usuario"])
        pedidos = pedido_query(db, " WHERE p.id_cliente = ?", (id_cliente,))
    return {"total_pedidos": len(pedidos), "pedidos": pedidos}


@app.get("/pedidos/")
def obtener_pedidos(
    estado: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    actual: dict = Depends(usuario_actual),
):
    exigir_rol(actual, "administrador")
    if estado and estado not in ESTADOS_PEDIDO:
        raise HTTPException(status_code=400, detail=f"Estado inválido. Use uno de: {', '.join(ESTADOS_PEDIDO)}.")
    where, params = pedido_condiciones(estado, q)
    with conectar_db() as db:
        total = pedido_count(db, where, params)
        pedidos = pedido_query(db, where, params, limit=limit, offset=offset)
    return {"total_pedidos": total, "pedidos": pedidos, "limit": limit, "offset": offset}


@app.get("/pedidos/exportar")
def exportar_pedidos_csv(estado: Optional[str] = None, q: Optional[str] = None, actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador")
    where, params = pedido_condiciones(estado, q)
    with conectar_db() as db:
        pedidos = pedido_query(db, where, params)
    buffer = io.StringIO()
    buffer.write("﻿")
    writer = csv.writer(buffer)
    writer.writerow([
        "ID", "Cliente", "Teléfono", "Recogida", "Entrega", "Fecha", "Valor",
        "Método de pago", "Estado", "Repartidor", "Observaciones",
    ])
    for pedido in pedidos:
        writer.writerow([
            pedido["id_pedido"], pedido["cliente"], pedido["telefono_cliente"],
            pedido["direccion_recogida"], pedido["direccion_entrega"], pedido["fecha_hora"],
            pedido["valor_servicio"], pedido["metodo_pago"], pedido["estado"],
            pedido["repartidor"] or "", pedido["observaciones"],
        ])
    buffer.seek(0)
    return StreamingResponse(
        buffer, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=domicilios.csv"},
    )


@app.get("/pedidos/{id_pedido}/historial")
def historial_pedido(id_pedido: int, actual: dict = Depends(usuario_actual)):
    obtener_pedido_por_id(id_pedido, actual)
    with conectar_db() as db:
        rows = db.execute(
            """
            SELECT h.estado, h.fecha_hora, u.nombre AS usuario
            FROM historial_pedidos h LEFT JOIN usuarios u ON u.id_usuario = h.id_usuario
            WHERE h.id_pedido = ? ORDER BY h.id_historial
            """,
            (id_pedido,),
        ).fetchall()
    return {"historial": [fila_dict(row) for row in rows]}


@app.put("/pedidos/{id_pedido}")
def editar_pedido(id_pedido: int, datos: ActualizarPedido, actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador")
    with conectar_db() as db:
        pedido = db.execute("SELECT estado FROM pedidos WHERE id_pedido = ?", (id_pedido,)).fetchone()
        if not pedido:
            raise HTTPException(status_code=404, detail="El domicilio no existe.")
        if pedido["estado"] in ("Entregado", "Cancelado"):
            raise HTTPException(
                status_code=400, detail="No se puede editar un domicilio entregado o cancelado."
            )
        db.execute(
            """
            UPDATE pedidos SET direccion_recogida = ?, direccion_entrega = ?, valor_servicio = ?,
                   metodo_pago = ?, tiempo_espera_min = ?, tiempo_recogida_min = ?, observaciones = ?
            WHERE id_pedido = ?
            """,
            (
                datos.direccion_recogida, datos.direccion_entrega, datos.valor_servicio,
                datos.metodo_pago, datos.tiempo_espera_min, datos.tiempo_recogida_min,
                datos.observaciones, id_pedido,
            ),
        )
    return {"mensaje": "Domicilio actualizado correctamente."}


@app.get("/repartidores/activos")
def obtener_repartidores_activos(actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador")
    with conectar_db() as db:
        rows = db.execute(
            """
            SELECT r.id_repartidor, r.id_usuario, r.telefono, r.disponible, r.zona,
                   u.nombre, u.correo
            FROM repartidores r JOIN usuarios u ON u.id_usuario = r.id_usuario
            WHERE r.disponible = 1 AND u.activo = 1 ORDER BY u.nombre
            """
        ).fetchall()
    return {"total_repartidores": len(rows), "repartidores": [fila_dict(row) for row in rows]}


@app.get("/repartidores/")
def obtener_repartidores(actual: dict = Depends(usuario_actual)):
    return obtener_repartidores_activos(actual)


@app.get("/repartidores/todos")
def obtener_todos_repartidores(actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador")
    with conectar_db() as db:
        rows = db.execute(
            """
            SELECT r.id_repartidor, r.id_usuario, r.telefono, r.disponible, r.zona,
                   u.nombre, u.correo
            FROM repartidores r JOIN usuarios u ON u.id_usuario = r.id_usuario
            WHERE u.activo = 1
            ORDER BY u.nombre
            """
        ).fetchall()
    return {"total_repartidores": len(rows), "repartidores": [fila_dict(row) for row in rows]}


@app.put("/repartidores/{id_repartidor}/disponibilidad")
def actualizar_disponibilidad(
    id_repartidor: int, datos: ActualizarDisponibilidad, actual: dict = Depends(usuario_actual)
):
    exigir_rol(actual, "administrador")
    with conectar_db() as db:
        cursor = db.execute(
            "UPDATE repartidores SET disponible = ? WHERE id_repartidor = ?",
            (int(datos.disponible), id_repartidor),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="El repartidor no existe.")
    return {"mensaje": "Disponibilidad actualizada correctamente.", "disponible": datos.disponible}


def _crear_cuenta_repartidor(db: sqlite3.Connection, datos: RegistroRepartidor) -> int:
    if db.execute("SELECT 1 FROM usuarios WHERE correo = ?", (datos.correo,)).fetchone():
        raise HTTPException(status_code=400, detail="Ya existe una cuenta con ese correo.")
    password_hash = hash_password(datos.password)
    id_usuario = db.execute(
        "INSERT INTO usuarios (nombre, correo, password_hash, rol) VALUES (?, ?, ?, 'repartidor')",
        (datos.nombre, datos.correo, password_hash),
    ).lastrowid
    cursor = db.execute(
        """
        INSERT INTO repartidores
            (id_usuario, telefono, disponible, zona, tipo_vehiculo, placa_vehiculo)
        VALUES (?, ?, 1, ?, ?, ?)
        """,
        (
            id_usuario, datos.telefono, datos.zona,
            datos.tipo_vehiculo, datos.placa_vehiculo,
        ),
    )
    return cursor.lastrowid


def _crear_cuenta_cliente(db: sqlite3.Connection, datos: RegistroCliente) -> int:
    if db.execute("SELECT 1 FROM usuarios WHERE correo = ?", (datos.correo,)).fetchone():
        raise HTTPException(status_code=400, detail="Ya existe una cuenta con ese correo.")
    password_hash = hash_password(datos.password)
    id_usuario = db.execute(
        "INSERT INTO usuarios (nombre, correo, password_hash, rol) VALUES (?, ?, ?, 'cliente')",
        (datos.nombre, datos.correo, password_hash),
    ).lastrowid
    cursor = db.execute(
        """
        INSERT INTO clientes
            (id_usuario, nombre, telefono, correo, direccion, nombre_local)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            id_usuario, datos.nombre, datos.telefono, datos.correo,
            datos.direccion, datos.nombre_local,
        ),
    )
    return cursor.lastrowid


@app.post("/registro")
def registrar_usuario(datos: RegistroUsuario):
    if datos.tipo_usuario == "cliente":
        cliente = RegistroCliente(
            nombre=datos.nombre,
            telefono=datos.telefono,
            correo=datos.correo,
            password=datos.password,
            direccion=datos.direccion or "",
            nombre_local=datos.nombre_local,
        )
        with conectar_db() as db:
            id_cliente = _crear_cuenta_cliente(db, cliente)
        return {"mensaje": "Cuenta de cliente creada con éxito.", "id_cliente": id_cliente}

    repartidor = RegistroRepartidor(
        nombre=datos.nombre,
        telefono=datos.telefono,
        correo=datos.correo,
        password=datos.password,
        zona=datos.zona,
        tipo_vehiculo=datos.tipo_vehiculo,
        placa_vehiculo=datos.placa_vehiculo or "",
    )
    with conectar_db() as db:
        id_repartidor = _crear_cuenta_repartidor(db, repartidor)
    return {
        "mensaje": "Cuenta de repartidor creada con éxito.",
        "id_repartidor": id_repartidor,
    }


@app.post("/repartidores/registro")
def registrar_repartidor(datos: RegistroRepartidor):
    with conectar_db() as db:
        id_repartidor = _crear_cuenta_repartidor(db, datos)
    return {"mensaje": "Cuenta creada con éxito. Ya puedes iniciar sesión.", "id_repartidor": id_repartidor}


@app.post("/repartidores/")
def crear_repartidor(datos: RegistroRepartidor, actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador")
    with conectar_db() as db:
        id_repartidor = _crear_cuenta_repartidor(db, datos)
    return {"mensaje": "Repartidor registrado con éxito.", "id_repartidor": id_repartidor}


@app.put("/repartidores/{id_repartidor}/password")
def resetear_password_repartidor(id_repartidor: int, datos: NuevaPassword, actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador")
    with conectar_db() as db:
        repartidor = db.execute(
            "SELECT id_usuario FROM repartidores WHERE id_repartidor = ?", (id_repartidor,)
        ).fetchone()
        if not repartidor:
            raise HTTPException(status_code=404, detail="El repartidor no existe.")
        password_hash = hash_password(datos.password)
        db.execute(
            "UPDATE usuarios SET password_hash = ? WHERE id_usuario = ?",
            (password_hash, repartidor["id_usuario"]),
        )
    return {"mensaje": "Contraseña actualizada correctamente."}


@app.delete("/repartidores/{id_repartidor}")
def eliminar_repartidor(id_repartidor: int, actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador")
    with conectar_db() as db:
        repartidor = db.execute(
            "SELECT id_usuario FROM repartidores WHERE id_repartidor = ?", (id_repartidor,)
        ).fetchone()
        if not repartidor:
            raise HTTPException(status_code=404, detail="El repartidor no existe.")
        pendiente = db.execute(
            "SELECT 1 FROM pedidos WHERE id_repartidor = ? AND estado NOT IN ('Entregado', 'Cancelado')",
            (id_repartidor,),
        ).fetchone()
        if pendiente:
            raise HTTPException(
                status_code=400,
                detail="No se puede eliminar un domiciliario con domicilios activos asignados.",
            )
        db.execute("UPDATE usuarios SET activo = 0 WHERE id_usuario = ?", (repartidor["id_usuario"],))
    return {"mensaje": "Domiciliario eliminado correctamente."}


@app.put("/pedidos/{id_pedido}/asignar-repartidor")
def asignar_repartidor_pedido(
    id_pedido: int, datos: AsignarRepartidor, actual: dict = Depends(usuario_actual)
):
    exigir_rol(actual, "administrador")
    with conectar_db() as db:
        pedido = db.execute("SELECT estado FROM pedidos WHERE id_pedido = ?", (id_pedido,)).fetchone()
        repartidor = db.execute(
            "SELECT id_repartidor FROM repartidores WHERE id_repartidor = ? AND disponible = 1",
            (datos.id_repartidor,),
        ).fetchone()
        if not pedido:
            raise HTTPException(status_code=404, detail="El domicilio no existe.")
        if not repartidor:
            raise HTTPException(status_code=400, detail="El repartidor no existe o no está activo.")
        if pedido["estado"] == "Cancelado":
            raise HTTPException(status_code=400, detail="No se puede asignar un domicilio cancelado.")
        db.execute(
            "UPDATE pedidos SET id_repartidor = ?, estado = 'Asignado' WHERE id_pedido = ?",
            (datos.id_repartidor, id_pedido),
        )
        _registrar_historial(db, id_pedido, "Asignado", actual["id_usuario"])
    return {"mensaje": "Domicilio asignado correctamente.", "nuevo_estado": "Asignado"}


@app.delete("/pedidos/{id_pedido}")
def cancelar_pedido(id_pedido: int, actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador")
    with conectar_db() as db:
        cursor = db.execute(
            "UPDATE pedidos SET estado = 'Cancelado' WHERE id_pedido = ? AND estado != 'Entregado'",
            (id_pedido,),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="El domicilio no existe o ya fue entregado.")
        _registrar_historial(db, id_pedido, "Cancelado", actual["id_usuario"])
    return {"mensaje": "Domicilio cancelado correctamente.", "id_pedido": id_pedido}


@app.get("/repartidores/{id_repartidor}/pedidos")
def pedidos_del_repartidor(id_repartidor: int, actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "repartidor")
    with conectar_db() as db:
        driver = db.execute(
            "SELECT id_usuario FROM repartidores WHERE id_repartidor = ?", (id_repartidor,)
        ).fetchone()
        if not driver or driver["id_usuario"] != actual["id_usuario"]:
            raise HTTPException(status_code=403, detail="No puede consultar pedidos de otro repartidor.")
        pedidos = pedido_query(db, " WHERE p.id_repartidor = ?", (id_repartidor,))
    return {"total_pedidos": len(pedidos), "pedidos": pedidos}


@app.get("/repartidores/{id_repartidor}/ganancias")
def ganancias_repartidor(id_repartidor: int, fecha: Optional[str] = None, actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador", "repartidor")
    fecha = fecha or datetime.now().date().isoformat()
    with conectar_db() as db:
        driver = db.execute(
            "SELECT id_usuario FROM repartidores WHERE id_repartidor = ?", (id_repartidor,)
        ).fetchone()
        if not driver:
            raise HTTPException(status_code=404, detail="El repartidor no existe.")
        if actual["rol"] == "repartidor" and driver["id_usuario"] != actual["id_usuario"]:
            raise HTTPException(status_code=403, detail="No puede consultar las ganancias de otro repartidor.")
        fila = db.execute(
            """
            SELECT COUNT(*) AS entregas, COALESCE(SUM(p.valor_servicio), 0) AS valor_total
            FROM historial_pedidos h JOIN pedidos p ON p.id_pedido = h.id_pedido
            WHERE h.estado = 'Entregado' AND date(h.fecha_hora) = ? AND p.id_repartidor = ?
            """,
            (fecha, id_repartidor),
        ).fetchone()
    return {"fecha": fecha, "entregas": fila["entregas"], "porcentaje_repartidor": PORCENTAJE_REPARTIDOR,
             **_desglosar_ganancia(fila["valor_total"])}


@app.get("/pedidos/{id_pedido}")
def obtener_pedido_por_id(id_pedido: int, actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador", "repartidor", "cliente")
    with conectar_db() as db:
        pedido = pedido_query(db, " WHERE p.id_pedido = ?", (id_pedido,))
    if not pedido:
        raise HTTPException(status_code=404, detail="El domicilio no fue encontrado.")
    if actual["rol"] == "repartidor":
        with conectar_db() as db:
            assigned = db.execute(
                """
                SELECT 1 FROM pedidos p
                JOIN repartidores r ON r.id_repartidor = p.id_repartidor
                WHERE p.id_pedido = ? AND r.id_usuario = ?
                """,
                (id_pedido, actual["id_usuario"]),
            ).fetchone()
        if not assigned:
            raise HTTPException(status_code=403, detail="No puede consultar este domicilio.")
    if actual["rol"] == "cliente":
        with conectar_db() as db:
            owner = db.execute(
                "SELECT 1 FROM clientes WHERE id_cliente = ? AND id_usuario = ?",
                (pedido[0]["id_cliente"], actual["id_usuario"]),
            ).fetchone()
        if not owner:
            raise HTTPException(status_code=403, detail="No puede consultar este domicilio.")
    return {"pedido": pedido[0]}


@app.put("/pedidos/{id_pedido}/estado")
def actualizar_estado_pedido(
    id_pedido: int, datos: ActualizarEstado, actual: dict = Depends(usuario_actual)
):
    exigir_rol(actual, "repartidor", "administrador", "cliente")
    
    with conectar_db() as db:
        pedido = db.execute("SELECT id_cliente FROM pedidos WHERE id_pedido = ?", (id_pedido,)).fetchone()
        if not pedido:
            raise HTTPException(status_code=404, detail="El domicilio no existe.")
            
        if actual["rol"] == "repartidor":
            assigned = db.execute(
                """
                SELECT 1 FROM pedidos p
                JOIN repartidores r ON r.id_repartidor = p.id_repartidor
                WHERE p.id_pedido = ? AND r.id_usuario = ?
                """,
                (id_pedido, actual["id_usuario"]),
            ).fetchone()
            if not assigned:
                raise HTTPException(status_code=403, detail="Solo puede actualizar domicilios asignados.")
                
        if actual["rol"] == "cliente":
            # Verificar que el pedido pertenezca a este cliente
            es_dueno = db.execute(
                "SELECT 1 FROM clientes WHERE id_cliente = ? AND id_usuario = ?",
                (pedido["id_cliente"], actual["id_usuario"])
            ).fetchone()
            if not es_dueno:
                raise HTTPException(status_code=403, detail="No puedes actualizar pedidos de otros clientes.")
            
            # Un cliente solo puede cancelar un pedido si está pendiente
            # o confirmar que lo recibió con conformidad
            estado_actual = db.execute("SELECT estado FROM pedidos WHERE id_pedido = ?", (id_pedido,)).fetchone()["estado"]
            
            if datos.nuevo_estado == "Cancelado por el cliente":
                if estado_actual not in ["Pendiente"]:
                    raise HTTPException(status_code=400, detail="Solo puedes cancelar un pedido que está Pendiente.")
                datos.nuevo_estado = "Cancelado"
                
            elif datos.nuevo_estado == "Recibido con conformidad":
                if estado_actual not in ["En camino", "Entregado"]:
                    raise HTTPException(status_code=400, detail="Solo puedes confirmar un pedido que ya está en camino o entregado.")
                datos.nuevo_estado = "Entregado"
                
            elif datos.nuevo_estado == "En espera":
                if estado_actual != "Pendiente":
                    raise HTTPException(status_code=400, detail="El pedido no puede volver a espera.")
                datos.nuevo_estado = "Pendiente"
            else:
                raise HTTPException(status_code=403, detail="Estado no permitido para clientes.")

        db.execute("UPDATE pedidos SET estado = ? WHERE id_pedido = ?", (datos.nuevo_estado, id_pedido))
        _registrar_historial(db, id_pedido, datos.nuevo_estado, actual["id_usuario"])
        
    return {"mensaje": "Estado actualizado correctamente.", "nuevo_estado": datos.nuevo_estado}


@app.get("/estadisticas/ganancias")
def ganancias_generales(fecha: Optional[str] = None, actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador")
    fecha = fecha or datetime.now().date().isoformat()
    with conectar_db() as db:
        filas = db.execute(
            """
            SELECT r.id_repartidor, u.nombre,
                   COUNT(h.id_historial) AS entregas,
                   COALESCE(SUM(p.valor_servicio), 0) AS valor_total
            FROM repartidores r
            JOIN usuarios u ON u.id_usuario = r.id_usuario
            LEFT JOIN pedidos p ON p.id_repartidor = r.id_repartidor
            LEFT JOIN historial_pedidos h
                ON h.id_pedido = p.id_pedido AND h.estado = 'Entregado' AND date(h.fecha_hora) = ?
            WHERE u.activo = 1
            GROUP BY r.id_repartidor
            ORDER BY valor_total DESC
            """,
            (fecha,),
        ).fetchall()
    repartidores = [
        {"id_repartidor": fila["id_repartidor"], "nombre": fila["nombre"], "entregas": fila["entregas"],
         **_desglosar_ganancia(fila["valor_total"])}
        for fila in filas
    ]
    total_general = sum(fila["valor_total"] for fila in repartidores)
    return {
        "fecha": fecha,
        "porcentaje_repartidor": PORCENTAJE_REPARTIDOR,
        "repartidores": repartidores,
        "totales": _desglosar_ganancia(total_general),
    }


@app.get("/estadisticas")
def obtener_estadisticas(actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador")
    with conectar_db() as db:
        pedidos_por_estado = {estado: 0 for estado in ESTADOS_PEDIDO}
        pedidos_por_estado.update(
            dict(db.execute("SELECT estado, COUNT(*) FROM pedidos GROUP BY estado").fetchall())
        )
        total_repartidores = db.execute(
            """
            SELECT COUNT(*) FROM repartidores r JOIN usuarios u ON u.id_usuario = r.id_usuario
            WHERE u.activo = 1
            """
        ).fetchone()[0]
        repartidores_activos = db.execute(
            """
            SELECT COUNT(*) FROM repartidores r JOIN usuarios u ON u.id_usuario = r.id_usuario
            WHERE r.disponible = 1 AND u.activo = 1
            """
        ).fetchone()[0]
        total_clientes = db.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
    return {
        "pedidos_por_estado": pedidos_por_estado,
        "total_repartidores": total_repartidores,
        "repartidores_activos": repartidores_activos,
        "total_clientes": total_clientes,
    }


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
