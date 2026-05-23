# DBaaS — Plataforma Distribuida de Base de Datos como Servicio

Arquitectura de microservicios con gRPC, RabbitMQ y MPI.

---

## Requisitos previos

| Herramienta | Versión mínima | Descarga |
|---|---|---|
| Docker Desktop | 4.x | https://www.docker.com/products/docker-desktop |
| Docker Compose | incluido en Docker Desktop | — |

> **Windows**: asegúrate de tener WSL2 habilitado.  
> **macOS / Linux**: Docker Desktop o Docker Engine + Compose plugin.

---

## 1. Levantar el sistema

```bash
# Desde la carpeta raíz del proyecto
cd dbaas
docker compose up --build
```

La primera vez tarda ~5 minutos (descarga imágenes base, instala dependencias).
Cuando veas esto, todo está listo:

```
dbaas_gateway      | ✅ API Gateway escuchando en puerto 8000
dbaas_auth         | ✅ Auth Service escuchando en puerto 50051
dbaas_admin        | ✅ Admin Service escuchando en puerto 50052
dbaas_storage      | ✅ Storage Service escuchando en puerto 50053
dbaas_query        | ✅ Query Service escuchando en puerto 50054
dbaas_aggregation  | ✅ Aggregation Service escuchando en puerto 50055
dbaas_aggregation  | ✅ RabbitMQ consumer escuchando en 'aggregation_queue'
```

### URLs disponibles

| Servicio | URL |
|---|---|
| **API Gateway** (Swagger UI) | http://localhost:8000/docs |
| **RabbitMQ** (panel de admin) | http://localhost:15672 — user: `dbaas` / pass: `dbaas123` |

---

## 2. Herramienta de prueba recomendada

Puedes usar cualquiera de estas opciones:

- **Swagger UI** → http://localhost:8000/docs (la más fácil, sin instalar nada)
- **curl** (ejemplos abajo)
- **Postman / Insomnia** → importa la colección desde el Swagger

---

## 3. Pruebas paso a paso

### 3.1 Health check

```bash
curl http://localhost:8000/health
# {"status":"ok","service":"api-gateway","version":"1.0.0"}
```

---

### 3.2 Autenticación

#### Login con el admin por defecto

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

Respuesta:
```json
{"success": true, "token": "eyJ...", "role": "admin", "message": "Login exitoso"}
```

**Guarda el token** para usarlo en los siguientes pasos:

```bash
# Linux / macOS
TOKEN="eyJ..."   # pega aquí tu token completo

# Windows PowerShell
$TOKEN="eyJ..."
```

#### Registrar un usuario lector (sin token)

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "ana", "password": "pass1234", "role": "reader"}'
```

#### Registrar un usuario escritor (requiere token de admin)

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"username": "carlos", "password": "pass1234", "role": "writer"}'
```

---

### 3.3 Administración de bases de datos

#### Crear una base de datos

```bash
curl -X POST http://localhost:8000/admin/databases \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"db_name": "tienda"}'
```

#### Listar bases de datos

```bash
curl http://localhost:8000/admin/databases \
  -H "Authorization: Bearer $TOKEN"
```

#### Crear tabla de productos

```bash
curl -X POST http://localhost:8000/admin/databases/tienda/tables \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "table_name": "productos",
    "columns": [
      {"name": "nombre",    "type": "string", "nullable": false, "primary": false},
      {"name": "precio",    "type": "float",  "nullable": true,  "primary": false},
      {"name": "stock",     "type": "int",    "nullable": true,  "primary": false},
      {"name": "categoria", "type": "string", "nullable": true,  "primary": false}
    ]
  }'
```

#### Crear tabla de pedidos (para probar JOIN)

```bash
curl -X POST http://localhost:8000/admin/databases/tienda/tables \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "table_name": "pedidos",
    "columns": [
      {"name": "producto_id", "type": "int",   "nullable": false, "primary": false},
      {"name": "cantidad",    "type": "int",   "nullable": false, "primary": false},
      {"name": "total",       "type": "float", "nullable": false, "primary": false}
    ]
  }'
```

#### Listar tablas

```bash
curl http://localhost:8000/admin/databases/tienda/tables \
  -H "Authorization: Bearer $TOKEN"
```

#### Eliminar tabla

```bash
curl -X DELETE http://localhost:8000/admin/databases/tienda/tables/pedidos \
  -H "Authorization: Bearer $TOKEN"
```

#### Eliminar base de datos

```bash
curl -X DELETE http://localhost:8000/admin/databases/tienda \
  -H "Authorization: Bearer $TOKEN"
```

---

### 3.4 Interfaz SQL-like

#### INSERT

```bash
curl -X POST http://localhost:8000/query/sql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql": "INSERT INTO tienda.productos (nombre, precio, stock, categoria) VALUES (\"Laptop\", 999.99, 10, \"Electronica\")"}'

curl -X POST http://localhost:8000/query/sql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql": "INSERT INTO tienda.productos (nombre, precio, stock, categoria) VALUES (\"Mouse\", 29.99, 50, \"Electronica\")"}'

curl -X POST http://localhost:8000/query/sql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql": "INSERT INTO tienda.productos (nombre, precio, stock, categoria) VALUES (\"Silla\", 250.00, 5, \"Muebles\")"}'

curl -X POST http://localhost:8000/query/sql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql": "INSERT INTO tienda.productos (nombre, precio, stock, categoria) VALUES (\"Lámpara\", 35.00, 20, \"Muebles\")"}'
```

#### SELECT *

```bash
curl -X POST http://localhost:8000/query/sql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM tienda.productos"}'
```

#### SELECT con WHERE

```bash
curl -X POST http://localhost:8000/query/sql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM tienda.productos WHERE precio > 100"}'
```

#### UPDATE

```bash
curl -X POST http://localhost:8000/query/sql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql": "UPDATE tienda.productos SET precio = 899.99 WHERE nombre = \"Laptop\""}'
```

#### DELETE

```bash
curl -X POST http://localhost:8000/query/sql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql": "DELETE FROM tienda.productos WHERE stock < 10"}'
```

---

### 3.5 Agregaciones SQL

#### COUNT

```bash
curl -X POST http://localhost:8000/query/sql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT COUNT(*) FROM tienda.productos"}'
```

#### SUM

```bash
curl -X POST http://localhost:8000/query/sql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT SUM(precio) FROM tienda.productos"}'
```

#### AVG

```bash
curl -X POST http://localhost:8000/query/sql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT AVG(precio) FROM tienda.productos"}'
```

#### DISTINCT

```bash
curl -X POST http://localhost:8000/query/sql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT DISTINCT categoria FROM tienda.productos"}'
```

#### INNER JOIN

Primero inserta algunos pedidos:

```bash
curl -X POST http://localhost:8000/query/sql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql": "INSERT INTO tienda.pedidos (producto_id, cantidad, total) VALUES (1, 2, 1799.98)"}'

curl -X POST http://localhost:8000/query/sql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql": "INSERT INTO tienda.pedidos (producto_id, cantidad, total) VALUES (2, 3, 89.97)"}'
```

Luego el JOIN:

```bash
curl -X POST http://localhost:8000/query/sql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT p.nombre, o.cantidad, o.total FROM tienda.productos p INNER JOIN tienda.pedidos o ON p._id = o.producto_id"}'
```

---

### 3.6 Interfaz NoSQL (JSON)

#### Insert

```bash
curl -X POST http://localhost:8000/query/nosql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "db_name": "tienda",
    "collection": "productos",
    "operation": "insert",
    "payload": {
      "record": {"nombre": "Teclado", "precio": 45.00, "stock": 30, "categoria": "Electronica"}
    }
  }'
```

#### Find (todos)

```bash
curl -X POST http://localhost:8000/query/nosql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "db_name": "tienda",
    "collection": "productos",
    "operation": "find",
    "payload": {"filter": {}}
  }'
```

#### Find con filtro simple

```bash
curl -X POST http://localhost:8000/query/nosql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "db_name": "tienda",
    "collection": "productos",
    "operation": "find",
    "payload": {"filter": {"categoria": "Electronica"}}
  }'
```

#### Find con operadores

```bash
curl -X POST http://localhost:8000/query/nosql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "db_name": "tienda",
    "collection": "productos",
    "operation": "find",
    "payload": {
      "filter": {"precio": {"$gt": 100}, "stock": {"$gte": 5}},
      "limit": 10
    }
  }'
```

#### Update

```bash
curl -X POST http://localhost:8000/query/nosql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "db_name": "tienda",
    "collection": "productos",
    "operation": "update",
    "payload": {
      "filter":  {"nombre": "Mouse"},
      "updates": {"precio": 24.99, "stock": 100}
    }
  }'
```

#### Delete

```bash
curl -X POST http://localhost:8000/query/nosql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "db_name": "tienda",
    "collection": "productos",
    "operation": "delete",
    "payload": {"filter": {"stock": {"$lt": 5}}}
  }'
```

#### Agregación NoSQL

```bash
# COUNT
curl -X POST http://localhost:8000/query/nosql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "db_name": "tienda",
    "collection": "productos",
    "operation": "aggregate",
    "payload": {"op": "COUNT", "field": "", "filter": {}}
  }'

# AVG
curl -X POST http://localhost:8000/query/nosql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "db_name": "tienda",
    "collection": "productos",
    "operation": "aggregate",
    "payload": {"op": "AVG", "field": "precio", "filter": {}}
  }'

# DISTINCT
curl -X POST http://localhost:8000/query/nosql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "db_name": "tienda",
    "collection": "productos",
    "operation": "aggregate",
    "payload": {"op": "DISTINCT", "field": "categoria", "filter": {}}
  }'
```

---

### 3.7 Probar control de roles

```bash
# Hacer login como usuario lector
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "ana", "password": "pass1234"}'

# Guardar token del lector
READER_TOKEN="eyJ..."

# SELECT funciona (lectura)
curl -X POST http://localhost:8000/query/sql \
  -H "Authorization: Bearer $READER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM tienda.productos"}'

# INSERT falla con 403 (solo escritura/admin)
curl -X POST http://localhost:8000/query/sql \
  -H "Authorization: Bearer $READER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql": "INSERT INTO tienda.productos (nombre) VALUES (\"Test\")"}'
# → 403 Forbidden
```

---

## 4. Apagar el sistema

```bash
# Detener todos los contenedores
docker compose down

# Detener Y borrar los volúmenes (borra todos los datos)
docker compose down -v
```

---

## 5. Ver logs de un servicio específico

```bash
docker logs dbaas_gateway      -f
docker logs dbaas_auth         -f
docker logs dbaas_admin        -f
docker logs dbaas_storage      -f
docker logs dbaas_query        -f
docker logs dbaas_aggregation  -f
docker logs dbaas_rabbitmq     -f
```

---

## 6. Solución de problemas comunes

| Problema | Causa probable | Solución |
|---|---|---|
| `connection refused` al hacer curl | Los servicios todavía están arrancando | Espera 30 segundos y reintenta |
| `502 Bad Gateway` en el Gateway | Un servicio gRPC no levantó | Revisa `docker logs dbaas_<servicio>` |
| `Token expirado` | JWT venció (24h por default) | Haz login de nuevo |
| Error en `docker compose up --build` | Falta Docker Desktop | Asegúrate de tener Docker corriendo |
| RabbitMQ panel no abre | RabbitMQ tardó en levantar | Espera 30s y recarga la página |

---

## 7. Estructura del proyecto

```
dbaas/
├── docker-compose.yml
├── proto/                    ← Contratos gRPC (5 archivos .proto)
├── gateway/                  ← API REST (FastAPI) — Puerto 8000
├── auth_service/             ← JWT + bcrypt + roles — Puerto 50051
├── admin_service/            ← DDL SQLite (crear/eliminar DBs/tablas) — Puerto 50052
├── storage_service/          ← DML SQLite (CRUD) — Puerto 50053
├── query_service/            ← Parser SQL + NoSQL + RabbitMQ RPC — Puerto 50054
├── aggregation_service/      ← MPI + RabbitMQ consumer — Puerto 50055
└── scripts/
    └── gen_protos.sh         ← Regenerar stubs gRPC si modificas los .proto
```

---

## 8. Operadores de filtro disponibles (interfaces NoSQL y SQL WHERE)

| Operador | SQL equivalente | Ejemplo |
|---|---|---|
| `{"campo": valor}` | `campo = valor` | `{"nombre": "Ana"}` |
| `{"campo": {"$eq": val}}` | `campo = val` | igual al anterior |
| `{"campo": {"$ne": val}}` | `campo != val` | `{"activo": {"$ne": 0}}` |
| `{"campo": {"$gt": val}}` | `campo > val` | `{"precio": {"$gt": 100}}` |
| `{"campo": {"$gte": val}}` | `campo >= val` | `{"stock": {"$gte": 1}}` |
| `{"campo": {"$lt": val}}` | `campo < val` | `{"precio": {"$lt": 500}}` |
| `{"campo": {"$lte": val}}` | `campo <= val` | `{"edad": {"$lte": 30}}` |
| `{"campo": {"$like": "pat"}}` | `campo LIKE pat` | `{"nombre": {"$like": "A%"}}` |
| `{"campo": {"$in": [...]}}` | `campo IN (...)` | `{"cat": {"$in": ["A","B"]}}` |
