import os
from fastapi import FastAPI
from databases import Database
from pydantic import BaseModel

# 1. Definimos el esquema de datos que esperamos recibir
class NotificationRequest(BaseModel):
    user_id: int
    message: str

# Configuración de la Capa de Persistencia
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@db-notifications:5432/notifications_db")
database = Database(DATABASE_URL)

app = FastAPI(title="Pamvid Notification Service")

@app.on_event("startup")
async def startup():
    await database.connect()
    # Crear tabla si no existe
    query = """
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            message TEXT,
            status VARCHAR(50)
        )
    """
    await database.execute(query=query)

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

@app.get("/")
def read_root():
    return {"message": "Servicio de Notificaciones de Pamvid activo"}

# 2. Ruta corregida para recibir JSON
@app.post("/send-notification")
async def send_notification(data: NotificationRequest):
    # Extraemos los datos del objeto 'data'
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

# 3. IMPORTANTE PARA DOCKER: 
# Asegúrate de que el comando de inicio en tu Dockerfile sea:
# CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]