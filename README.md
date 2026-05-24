# 🗄️ DBaaS — Database as a Service

> Plataforma distribuida de almacenamiento y consulta de datos basada en microservicios con gRPC, RabbitMQ y MPI.

**Materia:** Programación Distribuida  
**Tecnologías:** Python · FastAPI · gRPC · RabbitMQ · MPI · Docker · SQLite · JWT

---

## 📐 Arquitectura

El sistema se distribuye en **dos máquinas físicas**:

```
Mac (procesamiento)              Ubuntu (datos)
─────────────────────            ──────────────────────
API Gateway     :8000   ←gRPC→  Auth Service    :50051
Query Engine    :50054  ←gRPC→  Admin Service   :50052
Aggregation+MPI :50055  ←gRPC→  Storage Service :50053
RabbitMQ        :5672
```

### Protocolos de comunicación

| Protocolo | Uso |
|-----------|-----|
| HTTP/REST | Cliente → API Gateway |
| gRPC | Comunicación entre microservicios |
| RabbitMQ | Operaciones de agregación (async) |
| MPI | Procesamiento paralelo en 4 workers |

---

## Microservicios

| Servicio | Puerto | Responsabilidad | Máquina |
|----------|--------|-----------------|---------|
| API Gateway | 8000 | Punto de entrada HTTP, JWT, routing | Mac |
| Query Engine | 50054 | Parser SQL/NoSQL, orquestador | Mac |
| Aggregation Service | 50055 | COUNT/SUM/AVG/DISTINCT/JOIN con MPI | Mac |
| RabbitMQ | 5672 | Broker de mensajes async | Mac |
| Auth Service | 50051 | Registro, login, validación JWT | Ubuntu |
| Admin Service | 50052 | Crear/eliminar BDs y tablas (DDL) | Ubuntu |
| Storage Service | 50053 | CRUD sobre SQLite (DML) | Ubuntu |

---

## 📋 Requisitos

- Docker Desktop
- Docker Compose
- Git
- Red local compartida entre las dos máquinas

---

## 🚀 Instalación y Ejecución

### Opción 1 — Una sola máquina

```bash
# 1. Clonar el repositorio
git clone https://github.com/Elyairsm/dbaas-microservicios.git
cd dbaas-microservicios

# 2. Levantar todos los servicios
docker compose up --build

# 3. Verificar que están corriendo
docker ps
```

Acceder en: `http://localhost:8000/docs`

---

### Opción 2 — Distribuido en dos máquinas (Mac + Ubuntu)

#### En Ubuntu (primero)

```bash
# 1. Clonar el repositorio
git clone https://github.com/Elyairsm/dbaas-microservicios.git
cd dbaas-microservicios

# 2. Instalar Docker
sudo apt update && sudo apt install -y docker.io docker-compose-plugin
sudo systemctl start docker
sudo usermod -aG docker $USER
newgrp docker

# 3. Levantar servicios de datos
docker compose -f docker-compose.ubuntu.yml up --build
```

#### En Mac (después)

```bash
# 1. Clonar el repositorio
git clone https://github.com/Elyairsm/dbaas-microservicios.git
cd dbaas-microservicios

# 2. Actualizar IP de Ubuntu en docker-compose.mac.yml
# Cambiar 172.31.14.80 por la IP real de Ubuntu:
# En Ubuntu: hostname -I | awk '{print $1}'

# 3. Levantar servicios de procesamiento
docker compose -f docker-compose.mac.yml up --build
```

---

## Autenticación

| Rol | Permisos |
|-----|----------|
| `admin` | Todo: administración, CRUD, usuarios |
| `writer` | CRUD completo (INSERT, UPDATE, DELETE, SELECT) |
| `reader` | Solo lectura: SELECT y agregaciones |

### Login

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

---

## Endpoints principales

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/auth/register` | Registrar usuario |
| POST | `/auth/login` | Iniciar sesión |
| POST | `/admin/databases` | Crear base de datos |
| GET | `/admin/databases` | Listar bases de datos |
| POST | `/admin/databases/{db}/tables` | Crear tabla |
| POST | `/query/sql` | Ejecutar SQL |
| POST | `/query/nosql` | Ejecutar NoSQL JSON |
| GET | `/health` | Estado del sistema |

Documentación completa: `http://localhost:8000/docs`

---

## 🔍 Ejemplos de uso

### Interfaz SQL

```bash
TOKEN="tu_token_aqui"

# Crear base de datos
curl -X POST http://localhost:8000/admin/databases \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"db_name": "tienda"}'

# Insertar registro
curl -X POST http://localhost:8000/query/sql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql": "INSERT INTO tienda.productos (nombre, precio) VALUES (\"Laptop\", 999.99)"}'

# Agregaciones con MPI
curl -X POST http://localhost:8000/query/sql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT COUNT(*) FROM tienda.productos"}'
```

### Interfaz NoSQL

```bash
curl -X POST http://localhost:8000/query/nosql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "db_name": "tienda",
    "collection": "productos",
    "operation": "find",
    "payload": {
      "filter": {"precio": {"$gt": 100}}
    }
  }'
```

---

## 📊 Análisis de Rendimiento

### Operaciones CRUD (gRPC directo)

| Operación | Tiempo promedio | Protocolo |
|-----------|----------------|-----------|
| INSERT | ~45 ms | HTTP → gRPC → SQLite |
| SELECT * | ~38 ms | HTTP → gRPC → SQLite |
| UPDATE | ~42 ms | HTTP → gRPC → SQLite |
| DELETE | ~40 ms | HTTP → gRPC → SQLite |

### Operaciones de Agregación (RabbitMQ + MPI)

| Operación | Sin MPI (estimado) | Con 4 workers MPI | Mejora |
|-----------|-------------------|-------------------|--------|
| COUNT 1000 registros | ~200 ms | ~80 ms | ~2.5x |
| SUM 1000 registros | ~210 ms | ~85 ms | ~2.5x |
| AVG 1000 registros | ~215 ms | ~88 ms | ~2.4x |
| DISTINCT 1000 registros | ~230 ms | ~95 ms | ~2.4x |

### Prueba de concurrencia

```bash
for i in {1..10}; do
  curl -s -X POST http://localhost:8000/query/sql \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"sql\":\"INSERT INTO tienda.productos (nombre, precio) VALUES (\\\"Producto$i\\\", $i.99)\"}" &
done
wait
echo "✅ 10 inserts concurrentes completados"
```

---

##  Monitoreo RabbitMQ

Panel: `http://localhost:15672` — Usuario: `dbaas` / Contraseña: `dbaas123`

---

## 📁 Estructura del proyecto

```
dbaas/
├── proto/                    # Contratos gRPC (.proto)
│   ├── auth.proto
│   ├── admin.proto
│   ├── storage.proto
│   ├── query.proto
│   └── aggregation.proto
├── auth_service/             # JWT, bcrypt, roles
├── admin_service/            # DDL, catálogo de BDs
├── storage_service/          # CRUD, SQLite
├── query_service/            # Parser SQL/NoSQL
├── aggregation_service/      # MPI, RabbitMQ consumer
├── gateway/                  # FastAPI, HTTP/REST
├── docker-compose.yml        # Una sola máquina
├── docker-compose.mac.yml    # Mac (procesamiento)
└── docker-compose.ubuntu.yml # Ubuntu (datos)
```

---

## 🛑 Comandos útiles

```bash
# Ver logs en tiempo real
docker compose logs -f

# Ver log de un servicio
docker logs dbaas_gateway -f
docker logs dbaas_query -f
docker logs dbaas_aggregation -f

# Apagar sin perder datos
docker compose down

# Apagar y borrar datos
docker compose down -v

# Probar distribución: apagar Auth en Ubuntu
docker stop dbaas_auth   # login falla
docker start dbaas_auth  # login restaurado
```

---

## 🔧 Stack tecnológico

| Tecnología | Uso |
|------------|-----|
| Python 3.11 | Lenguaje principal |
| FastAPI | API Gateway HTTP |
| grpcio ≥1.63 | Comunicación entre servicios |
| pika 1.4.0 | Cliente RabbitMQ |
| mpi4py | Procesamiento paralelo |
| sqlglot ≥25.0 | Parser SQL |
| PyJWT | Tokens JWT |
| bcrypt | Hash de contraseñas |
| SQLite 3 | Almacenamiento interno |
| Docker | Contenedores |
| RabbitMQ 3.12 | Broker de mensajes |

---

## 👤 Autores

**Yair Santiago** — [@Elyairsm](https://github.com/Elyairsm)
**Ricardo Hernandez** - [@Richardx-o](https://github.com/Richardx-o)
Proyecto desarrollado para la materia de **Programación Distribuida **.
