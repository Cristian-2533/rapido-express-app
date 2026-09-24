# Guía breve para la exposición

## Tiempo sugerido: máximo 3 minutos

Rápido Express es una aplicación web para gestionar domicilios. El backend se
construyó con **Python y FastAPI**, que permite crear una API REST para el
registro, autenticación, clientes, repartidores, domicilios y asignaciones.

La interfaz se desarrolló con **HTML, CSS y JavaScript**, servida por el mismo
backend. El administrador puede consultar estadísticas, visualizar la flota en
un mapa, registrar clientes y repartidores, crear domicilios y asignar cada
solicitud a un domiciliario disponible.

La aplicación utiliza **SQLite**, una base de datos relacional ligera basada en
un archivo local. Se eligió porque el proyecto es pequeño, no requiere un
servidor de base de datos separado y facilita las pruebas y el despliegue. El
código usa `sqlite3` directamente; no se agregó SQLAlchemy porque no forma
parte de la arquitectura actual.

La base de datos está organizada por perfiles: `usuarios` almacena las cuentas
y roles; `clientes` y `repartidores` almacenan los datos específicos de cada
perfil; `pedidos` almacena las solicitudes; e `historial_pedidos` registra los
cambios de estado.

También se incorporaron validaciones con **Pydantic v2**. Por ejemplo, el
registro de un cliente exige dirección, mientras que el registro de un
repartidor exige tipo de vehículo y placa. Las coordenadas GPS se validan por
rango y se guardan con la hora UTC del servidor.

El flujo de negocio es el siguiente: el cliente crea un domicilio indicando el
local de recogida, las direcciones, la hora opcional y el tiempo de espera. La
solicitud queda en estado `Pendiente`. El administrador la recibe en su panel,
selecciona un domiciliario disponible y el pedido pasa a `Asignado`. El
domiciliario lo ve en su panel y el cliente observa el nombre del domiciliario
y el nuevo estado. La actualización se realiza automáticamente cada 15
segundos y muestra notificaciones visuales.

## Guion oral

> “Desarrollamos Rápido Express con Python y FastAPI para administrar el flujo
> de domicilios. Usamos SQLite como base de datos relacional porque es ligera,
> suficiente para el alcance del proyecto y no necesita un servidor adicional.
> La información se separa entre usuarios, perfiles de clientes,
> repartidores, pedidos e historial.
>
> En la interfaz usamos HTML, CSS y JavaScript. El administrador puede consultar
> estadísticas, ver el mapa GPS, registrar usuarios, revisar solicitudes y
> asignar un domiciliario. El cliente crea una solicitud con local de recogida,
> direcciones, hora opcional y tiempo de espera. La solicitud inicia como
> pendiente; cuando el administrador la asigna, cambia a asignada y el cliente
> y el domiciliario ven la actualización.
>
> Para validar la información usamos Pydantic y para conservar datos existentes
> agregamos migraciones SQLite idempotentes, sin reconstruir ni borrar las
> tablas. Las notificaciones se implementan mediante actualización automática
> del panel, sin introducir WebSockets ni dependencias innecesarias.” 
