from datetime import datetime
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector
from pydantic import BaseModel
from typing import Optional

app = FastAPI()
BASE_DIR = Path(__file__).resolve().parent

# Configurar CORS para permitir peticiones sin bloqueos del navegador
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Conexión a tu base de datos MySQL
def conectar_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="1035414045",  # Tu contraseña real de MySQL
        database="rapido_express"
    )

class Cliente(BaseModel):
    nombre: str
    telefono: str
    correo: str

class Pedido(BaseModel):
    id_cliente: int
    id_repartidor: Optional[int] = None
    direccion_recogida: str
    direccion_entrega: str
    valor_servicio: float
    metodo_pago: str
    observaciones: str = ""

class ActualizarEstado(BaseModel):
    nuevo_estado: str

@app.get("/")
def inicio():
    return FileResponse(BASE_DIR / "login.html")

@app.get("/probar-conexion")
def probar_conexion():
    try:
        conexion = conectar_db()
        cursor = conexion.cursor()
        cursor.execute("SHOW TABLES;")
        tablas = [tabla[0] for tabla in cursor.fetchall()]
        cursor.close()
        conexion.close()
        return {"estado": "¡Conexión exitosa con MySQL!", "tablas": tablas}
    except Exception as e:
        return {"estado": "Error", "detalle": str(e)}

@app.post("/clientes/")
def crear_cliente(cliente: Cliente):
    try:
        conexion = conectar_db()
        cursor = conexion.cursor()
        sql = "INSERT INTO CLIENTE (nombre, telefono, correo) VALUES (%s, %s, %s)"
        valores = (cliente.nombre, cliente.telefono, cliente.correo)
        
        cursor.execute(sql, valores)
        conexion.commit()
        
        cliente_id = cursor.lastrowid
        cursor.close()
        conexion.close()
        
        return {
            "mensaje": "¡Cliente registrado con éxito en Rápido Express!",
            "id_cliente": cliente_id,
            "datos": cliente
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/clientes/")
def obtener_clientes():
    try:
        conexion = conectar_db()
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT * FROM CLIENTE;")
        clientes = cursor.fetchall()
        
        cursor.close()
        conexion.close()
        
        return {
            "total_clientes": len(clientes),
            "clientes": clientes
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/pedidos/")
def crear_pedido(pedido: Pedido):
    try:
        conexion = conectar_db()
        cursor = conexion.cursor()
        
        estado_inicial = "Pendiente"
        fecha_actual = datetime.now()
        
        sql = """
            INSERT INTO PEDIDO 
            (id_cliente, id_repartidor, direccion_recogida, direccion_entrega, fecha_hora, valor_servicio, metodo_pago, estado, observaciones) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        valores = (
            pedido.id_cliente, 
            pedido.id_repartidor if pedido.id_repartidor else None, 
            pedido.direccion_recogida, 
            pedido.direccion_entrega, 
            fecha_actual, 
            pedido.valor_servicio, 
            pedido.metodo_pago, 
            estado_inicial, 
            pedido.observaciones
        )
        
        cursor.execute(sql, valores)
        conexion.commit()
        
        pedido_id = cursor.lastrowid
        cursor.close()
        conexion.close()
        
        return {
            "mensaje": "¡Pedido registrado con éxito en estado Pendiente!",
            "id_pedido": pedido_id,
            "estado": estado_inicial,
            "datos_pedido": pedido
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/pedidos/")
def obtener_pedidos():
    try:
        conexion = conectar_db()
        cursor = conexion.cursor(dictionary=True)
        
        sql = """
            SELECT p.id_pedido, c.nombre AS cliente, p.direccion_recogida, 
                   p.direccion_entrega, p.fecha_hora, p.valor_servicio, 
                   p.metodo_pago, p.estado, p.observaciones
            FROM PEDIDO p
            JOIN CLIENTE c ON p.id_cliente = c.id_cliente;
        """
        cursor.execute(sql)
        pedidos = cursor.fetchall()
        
        cursor.close()
        conexion.close()
        
        return {
            "total_pedidos": len(pedidos),
            "pedidos": pedidos
        }
    except Exception as e:
        return {"error": str(e)}

# RUTA NUEVA: Actualizar el estado de un pedido
@app.put("/pedidos/{id_pedido}/estado")
def actualizar_estado_pedido(id_pedido: int, datos: ActualizarEstado):
    try:
        conexion = conectar_db()
        cursor = conexion.cursor()
        
        cursor.execute("SELECT id_pedido FROM PEDIDO WHERE id_pedido = %s;", (id_pedido,))
        pedido_existente = cursor.fetchone()
        
        if not pedido_existente:
            cursor.close()
            conexion.close()
            return {"error": f"El pedido con ID {id_pedido} no existe en la base de datos."}
        
        sql = "UPDATE PEDIDO SET estado = %s WHERE id_pedido = %s;"
        cursor.execute(sql, (datos.nuevo_estado, id_pedido))
        conexion.commit()
        
        cursor.close()
        conexion.close()
        
        return {
            "mensaje": f"¡El estado del pedido #{id_pedido} fue actualizado con éxito!",
            "nuevo_estado": datos.nuevo_estado
        }
    except Exception as e:
        return {"error": str(e)}
    # Estructura para recibir los datos de un repartidor
class Repartidor(BaseModel):
    id_usuario: int
    telefono: str
    disponible: int = 1
    id_zona: int

# NUEVA RUTA: Registrar un nuevo repartidor
@app.post("/repartidores/")
def crear_repartidor(repartidor: Repartidor):
    try:
        conexion = conectar_db()
        cursor = conexion.cursor()
        
        sql = """
            INSERT INTO repartidor (id_usuario, telefono, disponible, id_zona) 
            VALUES (%s, %s, %s, %s)
        """
        valores = (repartidor.id_usuario, repartidor.telefono, repartidor.disponible, repartidor.id_zona)
        
        cursor.execute(sql, valores)
        conexion.commit()
        
        repartidor_id = cursor.lastrowid
        cursor.close()
        conexion.close()
        
        return {
            "mensaje": "¡Repartidor registrado con éxito en Rápido Express!",
            "id_repartidor": repartidor_id,
            "datos": repartidor
        }
    except Exception as e:
        return {"error": str(e)}
    # NUEVA RUTA: Consultar todos los repartidores registrados
@app.get("/repartidores/")
def obtener_repartidores():
    try:
        conexion = conectar_db()
        cursor = conexion.cursor(dictionary=True)
        
        cursor.execute("SELECT * FROM repartidor;")
        repartidores = cursor.fetchall()
        
        cursor.close()
        conexion.close()
        
        return {
            "total_repartidores": len(repartidores),
            "repartidores": repartidores
        }
    except Exception as e:
        return {"error": str(e)}
    # Estructura para recibir el ID del repartidor a asignar
class AsignarRepartidor(BaseModel):
    id_repartidor: int

# NUEVA RUTA: Asignar un repartidor a un pedido y cambiar su estado a "En camino"
@app.put("/pedidos/{id_pedido}/asignar-repartidor")
def asignar_repartidor_pedido(id_pedido: int, datos: AsignarRepartidor):
    try:
        conexion = conectar_db()
        cursor = conexion.cursor()
        
        # 1. Verificar si el pedido existe
        cursor.execute("SELECT id_pedido FROM PEDIDO WHERE id_pedido = %s;", (id_pedido,))
        if not cursor.fetchone():
            cursor.close()
            conexion.close()
            return {"error": f"El pedido con ID {id_pedido} no existe."}
            
        # 2. Verificar si el repartidor existe
        cursor.execute("SELECT id_repartidor FROM repartidor WHERE id_repartidor = %s;", (datos.id_repartidor,))
        if not cursor.fetchone():
            cursor.close()
            conexion.close()
            return {"error": f"El repartidor con ID {datos.id_repartidor} no existe."}
        
        # 3. Asignar el repartidor y cambiar el estado automáticamente a "En camino"
        sql = "UPDATE PEDIDO SET id_repartidor = %s, estado = 'En camino' WHERE id_pedido = %s;"
        cursor.execute(sql, (datos.id_repartidor, id_pedido))
        conexion.commit()
        
        cursor.close()
        conexion.close()
        
        return {
            "mensaje": f"¡Repartidor #{datos.id_repartidor} asignado al pedido #{id_pedido} con éxito!",
            "nuevo_estado": "En camino"
        }
    except Exception as e:
        return {"error": str(e)}
    # NUEVA RUTA: Consultar un pedido específico por su ID con datos del cliente
@app.get("/pedidos/{id_pedido}")
def obtener_pedido_por_id(id_pedido: int):
    try:
        conexion = conectar_db()
        cursor = conexion.cursor(dictionary=True)
        
        sql = """
            SELECT p.id_pedido, c.nombre AS cliente, c.telefono AS telefono_cliente, 
                   p.id_repartidor, p.direccion_recogida, p.direccion_entrega, 
                   p.fecha_hora, p.valor_servicio, p.metodo_pago, p.estado, p.observaciones
            FROM PEDIDO p
            JOIN CLIENTE c ON p.id_cliente = c.id_cliente
            WHERE p.id_pedido = %s;
        """
        cursor.execute(sql, (id_pedido,))
        pedido = cursor.fetchone()
        
        cursor.close()
        conexion.close()
        
        if not pedido:
            return {"error": f"El pedido con ID {id_pedido} no fue encontrado."}
            
        return {"pedido": pedido}
    except Exception as e:
        return {"error": str(e)}


# Servir la interfaz web junto con la API cuando se inicia FastAPI.
app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="frontend")