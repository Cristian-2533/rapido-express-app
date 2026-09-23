from datetime import datetime
from pathlib import Path
import base64
import csv
import hashlib
import hmac
import io
import os
import sqlite3
import time
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATABASE_PATH = Path(os.getenv("RAPIDO_EXPRESS_DB", BASE_DIR / "rapido_express.db"))
SECRET_KEY = os.getenv("RAPIDO_EXPRESS_SECRET", "cambia-esta-clave-en-produccion").encode()
if not os.getenv("RAPIDO_EXPRESS_SECRET"):
    print(
        "ADVERTENCIA: RAPIDO_EXPRESS_SECRET no está definida; usando una clave de solo-desarrollo. "
        "Defínela como variable de entorno antes de exponer este servidor a otras personas."
    )
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
    return JSONResponse(status_code=500, content={"detail": "Error interno del servidor."})


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
                FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
            );
            CREATE TABLE IF NOT EXISTS repartidores (
                id_repartidor INTEGER PRIMARY KEY AUTOINCREMENT,
                id_usuario INTEGER NOT NULL UNIQUE,
                telefono TEXT NOT NULL,
                disponible INTEGER NOT NULL DEFAULT 1,
                zona TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
            );
            CREATE TABLE IF NOT EXISTS pedidos (
                id_pedido INTEGER PRIMARY KEY AUTOINCREMENT,
                id_cliente INTEGER NOT NULL,
                id_repartidor INTEGER,
                direccion_recogida TEXT NOT NULL,
                direccion_entrega TEXT NOT NULL,
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
        if db.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone() is None:
            password = hashlib.sha256("12345678".encode()).hexdigest()
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
                "INSERT INTO repartidores (id_usuario, telefono, disponible, zona) VALUES (?, ?, 1, ?)",
                (driver_user["id_usuario"], "3000000000", "Zona norte"),
            )
            db.execute(
                "INSERT INTO clientes (nombre, telefono, correo) VALUES (?, ?, ?)",
                ("Cliente demo", "3100000000", "cliente@rapidoexpress.com"),
            )
            client_user = db.execute(
                "SELECT id_usuario FROM usuarios WHERE correo = ?",
                ("cliente@rapidoexpress.com",),
            ).fetchone()
            db.execute(
                "UPDATE clientes SET id_usuario = ? WHERE correo = ?",
                (client_user["id_usuario"], "cliente@rapidoexpress.com"),
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


class RegistroRepartidor(BaseModel):
    nombre: str = Field(min_length=2)
    telefono: str = Field(min_length=7)
    correo: str
    password: str = Field(min_length=6)
    zona: str = ""


class Pedido(BaseModel):
    id_cliente: int
    id_repartidor: Optional[int] = None
    direccion_recogida: str = Field(min_length=3)
    direccion_entrega: str = Field(min_length=3)
    valor_servicio: float = Field(ge=0)
    metodo_pago: str = Field(min_length=2)
    tiempo_espera_min: Optional[int] = Field(default=None, ge=0)
    tiempo_recogida_min: Optional[int] = Field(default=None, ge=0)
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
    firma = hmac.new(SECRET_KEY, payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(payload.encode()).decode() + "." + firma


def verificar_token(token: str) -> dict:
    try:
        payload_b64, firma = token.split(".", 1)
        payload = base64.urlsafe_b64decode(payload_b64.encode()).decode()
        firma_esperada = hmac.new(SECRET_KEY, payload.encode(), hashlib.sha256).hexdigest()
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
    latitud: float
    longitud: float


@app.patch("/repartidores/ubicacion")
def actualizar_ubicacion(datos: Ubicacion, actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "repartidor")
    with conectar_db() as db:
        cursor = db.execute(
            "UPDATE repartidores SET latitud = ?, longitud = ?, ultima_actualizacion_gps = ? WHERE id_usuario = ?",
            (datos.latitud, datos.longitud, datetime.now().isoformat(), actual["id_usuario"])
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Repartidor no encontrado.")
    return {"mensaje": "Ubicación actualizada."}


@app.get("/repartidores/ubicaciones")
def obtener_ubicaciones(actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador")
    with conectar_db() as db:
        # Traemos a los repartidores que tengan coordenadas y que su última actualización no sea muy vieja (opcional)
        rows = db.execute(
            """
            SELECT r.id_repartidor, u.nombre, r.latitud, r.longitud, r.ultima_actualizacion_gps, r.disponible
            FROM repartidores r
            JOIN usuarios u ON u.id_usuario = r.id_usuario
            WHERE r.latitud IS NOT NULL AND r.longitud IS NOT NULL
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
    password_hash = hashlib.sha256(datos.password.encode()).hexdigest()
    if not usuario or not hmac.compare_digest(usuario["password_hash"], password_hash):
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
def crear_cliente(datos: RegistroCliente):
    password_hash = hashlib.sha256(datos.password.encode()).hexdigest()
    with conectar_db() as db:
        if db.execute("SELECT 1 FROM usuarios WHERE correo = ?", (datos.correo,)).fetchone():
            raise HTTPException(status_code=400, detail="Ya existe una cuenta con ese correo.")
        id_usuario = db.execute(
            "INSERT INTO usuarios (nombre, correo, password_hash, rol) VALUES (?, ?, ?, 'cliente')",
            (datos.nombre, datos.correo, password_hash),
        ).lastrowid
        cursor = db.execute(
            "INSERT INTO clientes (id_usuario, nombre, telefono, correo) VALUES (?, ?, ?, ?)",
            (id_usuario, datos.nombre, datos.telefono, datos.correo),
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
        password_hash = hashlib.sha256(datos.password.encode()).hexdigest()
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
             valor_servicio, metodo_pago, estado, tiempo_espera_min, tiempo_recogida_min, observaciones)
            VALUES (?, NULL, ?, ?, ?, ?, ?, 'Pendiente', ?, ?, ?)
            """,
            (
                pedido.id_cliente, pedido.direccion_recogida, pedido.direccion_entrega,
                datetime.now().isoformat(timespec="seconds"), pedido.valor_servicio,
                pedido.metodo_pago, pedido.tiempo_espera_min, pedido.tiempo_recogida_min,
                pedido.observaciones,
            ),
        )
        _registrar_historial(db, cursor.lastrowid, "Pendiente", actual["id_usuario"])
    return {"mensaje": "Domicilio registrado con éxito.", "id_pedido": cursor.lastrowid, "estado": "Pendiente"}


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
    password_hash = hashlib.sha256(datos.password.encode()).hexdigest()
    id_usuario = db.execute(
        "INSERT INTO usuarios (nombre, correo, password_hash, rol) VALUES (?, ?, ?, 'repartidor')",
        (datos.nombre, datos.correo, password_hash),
    ).lastrowid
    cursor = db.execute(
        "INSERT INTO repartidores (id_usuario, telefono, disponible, zona) VALUES (?, ?, 1, ?)",
        (id_usuario, datos.telefono, datos.zona),
    )
    return cursor.lastrowid


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
        password_hash = hashlib.sha256(datos.password.encode()).hexdigest()
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
