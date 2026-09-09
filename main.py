from datetime import datetime
from pathlib import Path
import hashlib
import hmac
import os
import sqlite3
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.getenv("RAPIDO_EXPRESS_DB", BASE_DIR / "rapido_express.db"))
app = FastAPI(title="Rápido Express API", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


class Repartidor(BaseModel):
    id_usuario: int
    telefono: str = Field(min_length=7)
    disponible: bool = True
    zona: str = ""


class AsignarRepartidor(BaseModel):
    id_repartidor: int


def usuario_actual(
    x_rol: Optional[str] = Header(default=None),
    x_usuario_id: Optional[int] = Header(default=None),
) -> dict:
    if not x_rol:
        raise HTTPException(status_code=401, detail="Debe iniciar sesión.")
    return {"rol": x_rol, "id_usuario": x_usuario_id}


def exigir_rol(usuario: dict, *roles: str) -> None:
    if usuario["rol"] not in roles:
        raise HTTPException(status_code=403, detail="No tiene permisos para esta operación.")


def fila_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    return dict(row) if row else None


@app.get("/")
def inicio():
    return FileResponse(BASE_DIR / "login.html")


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
        "usuario": {
            "id_usuario": usuario["id_usuario"],
            "nombre": usuario["nombre"],
            "correo": usuario["correo"],
            "rol": usuario["rol"],
        }
    }


@app.post("/clientes/")
def crear_cliente(cliente: Cliente, x_rol: Optional[str] = Header(default=None)):
    if x_rol and x_rol != "administrador":
        raise HTTPException(status_code=403, detail="No tiene permisos para registrar clientes.")
    with conectar_db() as db:
        cursor = db.execute(
            "INSERT INTO clientes (nombre, telefono, correo) VALUES (?, ?, ?)",
            (cliente.nombre, cliente.telefono, cliente.correo),
        )
        return {"mensaje": "Cliente registrado con éxito.", "id_cliente": cursor.lastrowid}


@app.get("/clientes/")
def obtener_clientes(actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador")
    with conectar_db() as db:
        clientes = [fila_dict(row) for row in db.execute("SELECT * FROM clientes ORDER BY nombre")]
    return {"total_clientes": len(clientes), "clientes": clientes}


def pedido_query(db: sqlite3.Connection, where: str = "", params: tuple = ()) -> list[dict]:
    rows = db.execute(
        """
        SELECT p.*, c.nombre AS cliente, c.telefono AS telefono_cliente,
               c.correo AS correo_cliente, u.nombre AS repartidor
        FROM pedidos p
        JOIN clientes c ON c.id_cliente = p.id_cliente
        LEFT JOIN repartidores r ON r.id_repartidor = p.id_repartidor
        LEFT JOIN usuarios u ON u.id_usuario = r.id_usuario
        """
        + where
        + " ORDER BY p.id_pedido DESC",
        params,
    ).fetchall()
    return [fila_dict(row) for row in rows]


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
    return {"mensaje": "Domicilio registrado con éxito.", "id_pedido": cursor.lastrowid, "estado": "Pendiente"}


@app.get("/pedidos/")
def obtener_pedidos(actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador")
    with conectar_db() as db:
        pedidos = pedido_query(db)
    return {"total_pedidos": len(pedidos), "pedidos": pedidos}


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


@app.get("/repartidores/me")
def obtener_mi_repartidor(actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "repartidor")
    with conectar_db() as db:
        driver = db.execute(
            """
            SELECT r.id_repartidor, r.id_usuario, r.telefono, r.disponible, r.zona,
                   u.nombre, u.correo
            FROM repartidores r
            JOIN usuarios u ON u.id_usuario = r.id_usuario
            WHERE r.id_usuario = ? AND r.disponible = 1 AND u.activo = 1
            """,
            (actual["id_usuario"],),
        ).fetchone()
    if not driver:
        raise HTTPException(status_code=404, detail="No hay un perfil activo de domiciliario.")
    return {"repartidor": fila_dict(driver)}


@app.post("/repartidores/")
def crear_repartidor(repartidor: Repartidor, actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "administrador")
    with conectar_db() as db:
        if not db.execute("SELECT 1 FROM usuarios WHERE id_usuario = ?", (repartidor.id_usuario,)).fetchone():
            raise HTTPException(status_code=404, detail="El usuario del repartidor no existe.")
        cursor = db.execute(
            "INSERT INTO repartidores (id_usuario, telefono, disponible, zona) VALUES (?, ?, ?, ?)",
            (repartidor.id_usuario, repartidor.telefono, int(repartidor.disponible), repartidor.zona),
        )
    return {"mensaje": "Repartidor registrado con éxito.", "id_repartidor": cursor.lastrowid}


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
    return {"mensaje": "Domicilio cancelado correctamente.", "id_pedido": id_pedido}


@app.get("/repartidores/{id_repartidor}/pedidos")
def pedidos_del_repartidor(id_repartidor: int, actual: dict = Depends(usuario_actual)):
    exigir_rol(actual, "repartidor")
    with conectar_db() as db:
        driver = db.execute(
            "SELECT id_usuario FROM repartidores WHERE id_repartidor = ?", (id_repartidor,)
        ).fetchone()
        if not driver or (actual["id_usuario"] and driver["id_usuario"] != actual["id_usuario"]):
            raise HTTPException(status_code=403, detail="No puede consultar pedidos de otro repartidor.")
        pedidos = pedido_query(db, " WHERE p.id_repartidor = ?", (id_repartidor,))
    return {"total_pedidos": len(pedidos), "pedidos": pedidos}


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
    exigir_rol(actual, "repartidor", "administrador")
    with conectar_db() as db:
        if not db.execute("SELECT 1 FROM pedidos WHERE id_pedido = ?", (id_pedido,)).fetchone():
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
        db.execute("UPDATE pedidos SET estado = ? WHERE id_pedido = ?", (datos.nuevo_estado, id_pedido))
    return {"mensaje": "Estado actualizado correctamente.", "nuevo_estado": datos.nuevo_estado}


app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="frontend")
