# Car Wash Manager API

API REST para gestionar un negocio de lavado de autos con MongoDB, incluyendo registro de vehículos, asignaciones de servicios, sistema de puntos de lealtad e historial de clientes.

## 🚀 Características

- **Gestión de Autos**: Registro y consulta de vehículos
- **Sistema de Asignaciones**: Creación y seguimiento de servicios de lavado
- **Puntos de Lealtad**: Acumulación automática de puntos por servicio
- **Historial de Clientes**: Consulta del historial completo de servicios por placa
- **Base de Datos MongoDB**: Persistencia de datos con Motor (driver asíncrono)
- **Documentación Automática**: Swagger UI disponible en `/docs`

## 📋 Requisitos

- Python 3.11+
- MongoDB (local o remoto)
- Docker (opcional)

## 🛠️ Instalación y Configuración

### Opción 1: Ejecución Local

1. **Clonar el repositorio**
```bash
git clone <repository-url>
cd carwash_cloud_api
```

2. **Crear entorno virtual**
```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

3. **Instalar dependencias**
```bash
pip install -r requirements.txt
```

4. **Configurar variables de entorno**
```bash
# Crear archivo .env en el directorio raíz
cp .env.example .env
# Editar .env con tus valores
```

Contenido del archivo `.env`:
```env
MONGO_URL=""
DB_NAME="carwash_db"
```

5. **Ejecutar la aplicación**
```bash
# Desarrollo
python carwash_api.py

# O con uvicorn directamente
uvicorn carwash_api:app --host 0.0.0.0 --port 8000 --reload
```

### Opción 2: Ejecución con Docker

1. **Construir la imagen**
```bash
docker build -t carwash-api .
```

2. **Ejecutar el contenedor**
```bash
# Con variables de entorno
docker run -p 8000:8000 \
  -e MONGO_URL="tu-mongo-url" \
  -e DB_NAME="carwash_db" \
  carwash-api

# O usando archivo .env
docker run -p 8000:8000 --env-file .env carwash-api
```

## 🌐 Endpoints de la API

### General
- `GET /` - Mensaje de bienvenida
- `GET /docs` - Documentación Swagger UI
- `GET /redoc` - Documentación ReDoc

### Gestión de Autos
- `POST /cars/` - Registrar nuevo auto
- `GET /cars/` - Listar todos los autos
- `GET /cars/{plate}` - Obtener auto por placa
- `GET /cars/{plate}/history` - Obtener historial de servicios

### Gestión de Asignaciones
- `POST /assignments/` - Crear nueva asignación de servicio
- `GET /assignments/` - Listar asignaciones pendientes
- `PUT /assignments/{assignment_id}/complete` - Completar servicio y acumular puntos

## 📝 Ejemplos de Uso

### 1. Registrar un Auto
```bash
curl -X POST "http://localhost:8000/cars/" \
  -H "Content-Type: application/json" \
  -d '{
    "plate": "ABC123",
    "car_type": "Sedan",
    "owner_name": "Juan Pérez",
    "owner_phone": "+1234567890"
  }'
```

### 2. Crear Asignación de Servicio
```bash
curl -X POST "http://localhost:8000/assignments/" \
  -H "Content-Type: application/json" \
  -d '{
    "car_plate": "ABC123",
    "employee_name": "María López",
    "service_type": "Lavado Completo"
  }'
```

### 3. Completar Servicio
```bash
curl -X PUT "http://localhost:8000/assignments/{assignment_id}/complete"
```

### 4. Ver Historial del Cliente
```bash
curl "http://localhost:8000/cars/ABC123/history"
```

## 🗄️ Estructura de la Base de Datos

### Colección `cars`
```json
{
  "_id": "ObjectId",
  "plate": "ABC123",
  "car_type": "Sedan",
  "owner_name": "Juan Pérez",
  "owner_phone": "+1234567890",
  "loyalty_points": 5
}
```

### Colección `assignments`
```json
{
  "_id": "ObjectId",
  "car_plate": "ABC123",
  "employee_name": "María López",
  "service_type": "Lavado Completo",
  "status": "Completed",
  "points_earned": 1
}
```

## 🚢 Despliegue en Railway

1. **Conectar repositorio a Railway**
2. **Configurar variables de entorno en Railway:**
   - `MONGO_URL`: URL de tu instancia MongoDB
   - `DB_NAME`: Nombre de la base de datos

3. **Railway detectará automáticamente el Dockerfile y desplegará**

## 🔧 Configuración CORS

La API está configurada para permitir requests desde cualquier origen (`"*"`). Para producción, considera restringir los orígenes:

```python
origins = [
    "https://tu-frontend.com",
    "https://app.tu-dominio.com"
]
```

## 🔍 Monitoreo y Logs

- Los logs de conexión a MongoDB aparecen al iniciar la aplicación
- Usa `docker logs <container-id>` para ver logs del contenedor
- La aplicación incluye logging automático de requests en Uvicorn

## 🛡️ Seguridad

- Variables sensibles (URLs de DB) deben configurarse como variables de entorno
- No incluir el archivo `.env` en el repositorio de producción
- Considerar autenticación/autorización para endpoints sensibles

## 📚 Tecnologías Utilizadas

- **FastAPI** - Framework web moderno para APIs
- **Motor** - Driver asíncrono de MongoDB
- **Pydantic** - Validación de datos y serialización
- **Uvicorn** - Servidor ASGI
- **Python-dotenv** - Gestión de variables de entorno
