import logging
import os
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from databases import Database
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
import asyncio
import bcrypt
from jose import JWTError, jwt
from datetime import datetime, timedelta
import traceback

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_ZwStrQ3RbPc1@ep-autumn-art-amm4xi1w-pooler.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")

database = Database(DATABASE_URL)

SECRET_KEY = "pamvid-secret-key-2026"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    phone: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    phone: Optional[str]
    created_at: str


class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


app = FastAPI(title="User Service", description="Servicio de Usuarios - Pamvid")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor"}
    )


def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def get_password_hash(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


@app.on_event("startup")
async def startup():
    logger.info("👤 User Service starting up...")
    for i in range(10):
        try:
            await database.connect()
            query = """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                phone VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
            await database.execute(query=query)
            logger.info("✅ User Service connected to DB")
            break
        except Exception as e:
            logger.warning(f"⏳ Waiting for db-users... attempt {i+1}, error: {e}")
            await asyncio.sleep(3)


@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()


@app.post("/register", response_model=UserResponse)
async def register(user: UserCreate):
    logger.info(f"Register request for: {user.email}")
    query = "SELECT id FROM users WHERE email = :email"
    existing = await database.fetch_one(query=query, values={"email": user.email})
    if existing:
        logger.warning(f"Email already registered: {user.email}")
        raise HTTPException(status_code=400, detail="El email ya está registrado")
    
    password_hash = get_password_hash(user.password)
    query = """
        INSERT INTO users(email, password_hash, name, phone)
        VALUES (:email, :password_hash, :name, :phone)
        RETURNING id, email, name, phone, created_at
    """
    values = {
        "email": user.email,
        "password_hash": password_hash,
        "name": user.name,
        "phone": user.phone
    }
    result = await database.fetch_one(query=query, values=values)
    
    return UserResponse(
        id=result["id"],
        email=result["email"],
        name=result["name"],
        phone=result["phone"],
        created_at=result["created_at"].isoformat()
    )


@app.post("/login", response_model=Token)
async def login(user: UserLogin):
    query = "SELECT * FROM users WHERE email = :email"
    db_user = await database.fetch_one(query=query, values={"email": user.email})
    
    if not db_user or not verify_password(user.password, db_user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    
    access_token = create_access_token(data={"sub": str(db_user["id"]), "email": db_user["email"]})
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=db_user["id"],
            email=db_user["email"],
            name=db_user["name"],
            phone=db_user["phone"],
            created_at=db_user["created_at"].isoformat()
        )
    )


@app.get("/me", response_model=UserResponse)
async def get_me(request: Request):
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="No autorizado")
    
    token = auth_header.split(' ')[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get('sub'))
    except:
        raise HTTPException(status_code=401, detail="Token inválido")
    
    query = "SELECT id, email, name, phone, created_at FROM users WHERE id = :id"
    user = await database.fetch_one(query=query, values={"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    return UserResponse(
        id=user["id"],
        email=user["email"],
        name=user["name"],
        phone=user["phone"],
        created_at=user["created_at"].isoformat()
    )


@app.put("/me", response_model=UserResponse)
async def update_me(user_id: int, name: str = None, phone: str = None):
    updates = []
    values = {"id": user_id}
    
    if name:
        updates.append("name = :name")
        values["name"] = name
    if phone:
        updates.append("phone = :phone")
        values["phone"] = phone
    
    if not updates:
        raise HTTPException(status_code=400, detail="No hay datos para actualizar")
    
    query = f"UPDATE users SET {', '.join(updates)} WHERE id = :id RETURNING id, email, name, phone, created_at"
    result = await database.fetch_one(query=query, values=values)
    
    if not result:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    return UserResponse(
        id=result["id"],
        email=result["email"],
        name=result["name"],
        phone=result["phone"],
        created_at=result["created_at"].isoformat()
    )


@app.get("/health")
async def health_check():
    return {"status": "online", "service": "user-service"}