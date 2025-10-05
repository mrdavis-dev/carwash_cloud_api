import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from bson import ObjectId
from contextlib import asynccontextmanager

# --- Configuración de la Base de Datos ---
import os
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# --- Configuración de la Base de Datos (desde entorno) ---
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "carwash_db")

# --- Ayudante para ObjectId de Pydantic ---
# MongoDB usa _id como un objeto ObjectId, esto ayuda a Pydantic a manejarlo.
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, handler):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid objectid")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, schema, handler):
        schema.update(type="string")
        return schema

# --- Modelos de Pydantic ---
class Car(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    plate: str
    car_type: str
    owner_name: str
    owner_phone: str
    loyalty_points: int = 0

    class Config:
        json_encoders = {ObjectId: str}
        arbitrary_types_allowed = True

class AssignmentCreate(BaseModel):
    car_plate: str
    employee_name: str

class Assignment(AssignmentCreate):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    status: str = "Pending"

    class Config:
        json_encoders = {ObjectId: str}
        arbitrary_types_allowed = True

# --- Gestión del ciclo de vida de la aplicación (conexión a DB) ---
db_client: Optional[AsyncIOMotorClient] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Al iniciar
    global db_client
    db_client = AsyncIOMotorClient(MONGO_URL)
    print("Conexión a la base de datos establecida.")
    yield
    # Al apagar
    db_client.close()
    print("Conexión a la base de datos cerrada.")

def get_database() -> AsyncIOMotorDatabase:
    return db_client[DB_NAME]

# --- Inicialización de la Aplicación ---
app = FastAPI(
    title="Car Wash Manager API MVP",
    description="API para gestionar autos, asignaciones y puntos de lealtad.",
    version="1.1.0",
    lifespan=lifespan
)

# --- Configuración de CORS ---
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constante de puntos
POINTS_PER_WASH = 1

# --- Endpoints de la API ---

@app.get("/", tags=["General"])
def read_root():
    return {"message": "Bienvenido al Car Wash Manager API MVP. Usa /docs para ver la documentación."}

# -----------------
# Gestión de Autos
# -----------------

@app.post("/cars/", response_model=Car, status_code=201, tags=["Cars"])
async def register_car(car: Car, db: AsyncIOMotorDatabase = Depends(get_database)):
    plate_key = car.plate.upper()
    car.plate = plate_key
    
    existing_car = await db.cars.find_one({"plate": plate_key})
    if existing_car:
        print(f"Advertencia: El auto con placa {plate_key} ya existe. Se omite el registro.")
        return existing_car
    
    car_dict = car.model_dump(by_alias=True, exclude=["id"])
    result = await db.cars.insert_one(car_dict)
    created_car = await db.cars.find_one({"_id": result.inserted_id})
    return created_car

@app.get("/cars/", response_model=List[Car], tags=["Cars"])
async def list_cars(db: AsyncIOMotorDatabase = Depends(get_database)):
    cars = await db.cars.find().to_list(1000)
    return cars

@app.get("/cars/{plate}", response_model=Car, tags=["Cars"])
async def get_car(plate: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    plate_key = plate.upper()
    car = await db.cars.find_one({"plate": plate_key})
    if car is None:
        raise HTTPException(status_code=404, detail=f"Auto con placa {plate_key} no encontrado.")
    return car

# -----------------
# Gestión de Asignaciones y Puntos
# -----------------

@app.post("/assignments/", response_model=Assignment, status_code=201, tags=["Assignments"])
async def create_assignment(assignment_data: AssignmentCreate, db: AsyncIOMotorDatabase = Depends(get_database)):
    plate_key = assignment_data.car_plate.upper()
    
    if not await db.cars.find_one({"plate": plate_key}):
        raise HTTPException(status_code=404, detail=f"Auto con placa {plate_key} no encontrado. ¡Debe registrarse primero!")
    
    new_assignment = Assignment(
        car_plate=plate_key,
        employee_name=assignment_data.employee_name,
        status="Washing"
    )
    
    assignment_dict = new_assignment.model_dump(by_alias=True, exclude=["id"])
    result = await db.assignments.insert_one(assignment_dict)
    created_assignment = await db.assignments.find_one({"_id": result.inserted_id})
    return created_assignment

@app.get("/assignments/", response_model=List[Assignment], tags=["Assignments"])
async def list_assignments(db: AsyncIOMotorDatabase = Depends(get_database)):
    assignments = await db.assignments.find({"status": {"$ne": "Completed"}}).to_list(1000)
    return [Assignment(**assignment) for assignment in assignments]

@app.put("/assignments/{assignment_id}/complete", response_model=Car, tags=["Assignments"])
async def complete_assignment(assignment_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    try:
        obj_id = ObjectId(assignment_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID de asignación inválido.")

    assignment_to_update = await db.assignments.find_one({"_id": obj_id})
    
    if assignment_to_update is None:
        raise HTTPException(status_code=404, detail="Asignación no encontrada.")

    if assignment_to_update["status"] == "Completed":
        raise HTTPException(status_code=400, detail="Esta asignación ya está marcada como completada.")

    # 1. Actualizar el estado de la asignación
    await db.assignments.update_one(
        {"_id": obj_id},
        {"$set": {"status": "Completed"}}
    )

    # 2. Acumular puntos (operación atómica)
    car_plate = assignment_to_update["car_plate"]
    update_result = await db.cars.find_one_and_update(
        {"plate": car_plate},
        {"$inc": {"loyalty_points": POINTS_PER_WASH}},
        return_document=True
    )
    
    if update_result is None:
        raise HTTPException(status_code=404, detail=f"Error: Auto con placa {car_plate} no encontrado para asignar puntos.")
    
    return update_result

# --- Bloque de ejecución principal para Uvicorn ---
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)