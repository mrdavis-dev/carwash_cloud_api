import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from typing import List, Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from bson import ObjectId
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext

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
    business_id: str
    plate: str
    car_type: str
    owner_name: str
    owner_phone: str
    loyalty_points: int = 0

    class Config:
        json_encoders = {ObjectId: str}
        arbitrary_types_allowed = True


class CarCreate(BaseModel):
    plate: str
    car_type: str
    owner_name: str
    owner_phone: str

class AssignmentCreate(BaseModel):
    car_plate: str
    employee_name: str
    service_type: str = "Lavado Completo"  # Tipo de servicio aplicado


class Assignment(AssignmentCreate):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    business_id: str
    status: str = "Pending"
    points_earned: int = 0  # Puntos ganados en este servicio

    class Config:
        json_encoders = {ObjectId: str}
        arbitrary_types_allowed = True

# --- AUTH / JWT setup ---
SECRET_KEY = os.getenv("SECRET_KEY", "replace-this-with-a-secure-random-string")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_user(db: AsyncIOMotorDatabase, username: str):
    return await db.users.find_one({"username": username})


async def authenticate_user(db: AsyncIOMotorDatabase, username: str, password: str):
    user = await get_user(db, username)
    if not user:
        return False
    if not verify_password(password, user.get("hashed_password")):
        return False
    return user


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


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncIOMotorDatabase = Depends(get_database)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        business_id: str = payload.get("business_id")
        if username is None or business_id is None:
            raise credentials_exception
        token_data = {"username": username, "business_id": business_id}
    except JWTError:
        raise credentials_exception
    user = await get_user(db, username=token_data["username"])
    if user is None:
        raise credentials_exception
    return user

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

# --- Auth endpoints ---
class SignupData(BaseModel):
    business_name: str
    username: str
    password: str


@app.post("/auth/signup", tags=["auth"])
async def signup(data: SignupData, db: AsyncIOMotorDatabase = Depends(get_database)):
    # Crear negocio
    business = {"name": data.business_name}
    res = await db.businesses.insert_one(business)
    business_id = str(res.inserted_id)

    # Crear usuario admin para ese negocio
    hashed = get_password_hash(data.password)
    user = {"username": data.username, "hashed_password": hashed, "business_id": business_id}
    await db.users.insert_one(user)
    return {"msg": "Business and user created", "business_id": business_id}


@app.post("/auth/login", tags=["auth"] )
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncIOMotorDatabase = Depends(get_database)):
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"], "business_id": user["business_id"]},
        expires_delta=access_token_expires,
    )
    return {"access_token": access_token, "token_type": "bearer"}

# -----------------
# Gestión de Autos
# -----------------

@app.post("/cars/", response_model=Car, status_code=201, tags=["Cars"])
async def register_car(car: CarCreate, db: AsyncIOMotorDatabase = Depends(get_database), current_user: dict = Depends(get_current_user)):
    plate_key = car.plate.upper()

    business_id = current_user["business_id"]

    existing_car = await db.cars.find_one({"plate": plate_key, "business_id": business_id})
    if existing_car:
        print(f"Advertencia: El auto con placa {plate_key} ya existe. Se omite el registro.")
        return existing_car

    car_dict = car.model_dump()
    car_dict.update({"plate": plate_key, "business_id": business_id, "loyalty_points": 0})
    result = await db.cars.insert_one(car_dict)
    created_car = await db.cars.find_one({"_id": result.inserted_id})
    return created_car

@app.get("/cars/", response_model=List[Car], tags=["Cars"])
async def list_cars(db: AsyncIOMotorDatabase = Depends(get_database), current_user: dict = Depends(get_current_user)):
    business_id = current_user["business_id"]
    cars = await db.cars.find({"business_id": business_id}).to_list(1000)
    return cars

@app.get("/cars/{plate}", response_model=Car, tags=["Cars"])
async def get_car(plate: str, db: AsyncIOMotorDatabase = Depends(get_database), current_user: dict = Depends(get_current_user)):
    plate_key = plate.upper()
    business_id = current_user["business_id"]
    car = await db.cars.find_one({"plate": plate_key, "business_id": business_id})
    if car is None:
        raise HTTPException(status_code=404, detail=f"Auto con placa {plate_key} no encontrado.")
    return car

@app.get("/cars/{plate}/history", response_model=List[Assignment], tags=["Cars"])
async def get_car_history(plate: str, db: AsyncIOMotorDatabase = Depends(get_database), current_user: dict = Depends(get_current_user)):
    plate_key = plate.upper()
    business_id = current_user["business_id"]

    # Verificar que el auto existe para este negocio
    car = await db.cars.find_one({"plate": plate_key, "business_id": business_id})
    if car is None:
        raise HTTPException(status_code=404, detail=f"Auto con placa {plate_key} no encontrado.")

    # Obtener todas las asignaciones completadas para esta placa y negocio
    history = await db.assignments.find({
        "car_plate": plate_key,
        "status": "Completed",
        "business_id": business_id
    }).sort("_id", -1).to_list(1000)  # Ordenar por más reciente primero

    return [Assignment(**assignment) for assignment in history]

# -----------------
# Gestión de Asignaciones y Puntos
# -----------------

@app.post("/assignments/", response_model=Assignment, status_code=201, tags=["Assignments"])
async def create_assignment(assignment_data: AssignmentCreate, db: AsyncIOMotorDatabase = Depends(get_database), current_user: dict = Depends(get_current_user)):
    plate_key = assignment_data.car_plate.upper()
    business_id = current_user["business_id"]

    if not await db.cars.find_one({"plate": plate_key, "business_id": business_id}):
        raise HTTPException(status_code=404, detail=f"Auto con placa {plate_key} no encontrado. ¡Debe registrarse primero!")

    new_assignment = Assignment(
        car_plate=plate_key,
        employee_name=assignment_data.employee_name,
        service_type=assignment_data.service_type,
        business_id=business_id,
        status="Washing",
        points_earned=0
    )

    assignment_dict = new_assignment.model_dump(by_alias=True, exclude=["id"])
    result = await db.assignments.insert_one(assignment_dict)
    created_assignment = await db.assignments.find_one({"_id": result.inserted_id})
    return created_assignment

@app.get("/assignments/", response_model=List[Assignment], tags=["Assignments"])
async def list_assignments(db: AsyncIOMotorDatabase = Depends(get_database), current_user: dict = Depends(get_current_user)):
    business_id = current_user["business_id"]
    assignments = await db.assignments.find({"status": {"$ne": "Completed"}, "business_id": business_id}).to_list(1000)
    return [Assignment(**assignment) for assignment in assignments]

@app.put("/assignments/{assignment_id}/complete", response_model=Car, tags=["Assignments"])
async def complete_assignment(assignment_id: str, db: AsyncIOMotorDatabase = Depends(get_database), current_user: dict = Depends(get_current_user)):
    try:
        obj_id = ObjectId(assignment_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID de asignación inválido.")
    assignment_to_update = await db.assignments.find_one({"_id": obj_id})
    
    if assignment_to_update is None:
        raise HTTPException(status_code=404, detail="Asignación no encontrada.")

    # Verificar pertenencia al negocio del usuario
    business_id = current_user["business_id"]
    if str(assignment_to_update.get("business_id")) != str(business_id):
        raise HTTPException(status_code=403, detail="No autorizado para modificar esta asignación.")

    if assignment_to_update["status"] == "Completed":
        raise HTTPException(status_code=400, detail="Esta asignación ya está marcada como completada.")

    # 1. Actualizar el estado de la asignación y registrar puntos ganados
    update_res = await db.assignments.update_one(
        {"_id": obj_id, "business_id": business_id},
        {"$set": {
            "status": "Completed",
            "points_earned": POINTS_PER_WASH
        }}
    )

    if update_res.modified_count == 0:
        # could indicate assignment doesn't belong to business or was already updated
        raise HTTPException(status_code=404, detail="Asignación no encontrada o ya actualizada.")

    # 2. Acumular puntos (operación atómica)
    car_plate = assignment_to_update["car_plate"]
    update_result = await db.cars.find_one_and_update(
        {"plate": car_plate, "business_id": business_id},
        {"$inc": {"loyalty_points": POINTS_PER_WASH}},
        return_document=True
    )
    
    if update_result is None:
        raise HTTPException(status_code=404, detail=f"Error: Auto con placa {car_plate} no encontrado para asignar puntos.")
    
    return update_result

# --- Bloque de ejecución principal para Uvicorn ---
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)