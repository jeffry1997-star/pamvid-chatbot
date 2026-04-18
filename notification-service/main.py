import os
import logging
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from databases import Database
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 1. Definimos el esquema de datos que esperamos recibir
class NotificationRequest(BaseModel):
    user_id: int
    message: str

# Configuración de la Capa de Persistencia
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_ZwStrQ3RbPc1@ep-autumn-art-amm4xi1w-pooler.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")
database = Database(DATABASE_URL)

app = FastAPI(title="Pamvid Notification Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    logger.info("🔔 Notification Service starting up...")
    for i in range(10):
        try:
            await database.connect()
            query = """
                CREATE TABLE IF NOT EXISTS notifications (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER,
                    message TEXT,
                    status VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            await database.execute(query=query)
            logger.info("✅ Notification Service connected to DB")
            break
        except Exception as e:
            logger.warning(f"⏳ Waiting for DB... attempt {i+1}, error: {e}")
            await asyncio.sleep(3)

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()


@app.get("/health")
async def health_check():
    return {"status": "online", "service": "notification-service"}


@app.get("/")
def read_root():
    return {"message": "Servicio de Notificaciones de Pamvid activo"}

# 2. Ruta corregida para recibir JSON
@app.post("/send-notification")
async def send_notification(data: NotificationRequest):
    logger.info(f"Enviando notificación a usuario {data.user_id}")
    query = "INSERT INTO notifications(user_id, message, status) VALUES (:user_id, :message, :status)"
    values = {
        "user_id": data.user_id, 
        "message": data.message, 
        "status": "sent"
    }
    await database.execute(query=query, values=values)
    
    return {
        "status": "Notificación procesada y guardada en DB",
        "user_id": data.user_id,
        "message": data.message
    }

