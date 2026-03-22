from fastapi import FastAPI, Request, HTTPException, Response
import httpx
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional

# --- 1. MODELOS DE DATOS (Para que Swagger sea interactivo) ---
class OrderCreate(BaseModel):
    item: str       
    quantity: int
    user_id: int

class PaymentCreate(BaseModel):
    order_id: int
    amount: float
    method: str  # ej: "PSE", "Tarjeta", "Efectivo"

class NotificationSend(BaseModel):
    user_id: int
    message: str
    type: str  # ej: "email", "sms"

# --- 2. DICCIONARIO DE SERVICIOS (Configuración de Red Interna) ---
# IMPORTANTE: Usamos el nombre del servicio definido en docker-compose.yml
# Si tus servicios corren en el puerto 80 dentro del contenedor, cambia 8000 por 80.
SERVICES = {
    "order-service": "http://order-service:80",
    "payment-service": "http://payment-service:80",
    "notification-service": "http://notification-service:80",
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Cliente asíncrono para manejar múltiples peticiones sin bloquearse
    app.state.client = httpx.AsyncClient(timeout=10.0)
    yield
    await app.state.client.aclose()

app = FastAPI(
    title="Pamvid API Gateway",
    description="Sistema de Logística y Mensajería - Cali, Colombia",
    version="1.5.0",
    lifespan=lifespan
)

# --- 3. RUTAS: ORDER SERVICE ---
@app.post("/order-service/create-order", tags=["Orders"])
async def create_order(order: OrderCreate):
    """Crea una nueva orden de pedido en el sistema."""
    url = f"{SERVICES['order-service']}/create-order"
    try:
        response = await app.state.client.post(url, json=order.model_dump())
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error de conexión con Orders: {str(e)}")

@app.get("/order-service/all", tags=["Orders"])
async def get_all_orders():
    """Consulta todas las órdenes registradas."""
    url = f"{SERVICES['order-service']}/"
    try:
        response = await app.state.client.get(url)
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"No se pudo contactar al servicio de órdenes.")

# --- 4. RUTAS: PAYMENT SERVICE ---
@app.post("/payment-service/process", tags=["Payments"])
async def process_payment(payment: PaymentCreate):
    """Procesa el pago de una orden."""
    url = f"{SERVICES['payment-service']}/process-payment"
    try:
        response = await app.state.client.post(url, json=payment.model_dump())
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error de comunicación con el servicio de pagos.")

# --- 5. RUTAS: NOTIFICATION SERVICE ---
@app.post("/notification-service/send", tags=["Notifications"])
async def send_notification(notification: NotificationSend):
    """Envía alertas o mensajes a los usuarios."""
    url = f"{SERVICES['notification-service']}/send-notification"
    try:
        response = await app.state.client.post(url, json=notification.model_dump())
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"El servicio de notificaciones no responde.")

# --- 6. MONITOREO ---
@app.get("/health", tags=["System"])
async def health_check():
    """Verifica si el Gateway está operativo."""
    return {"status": "online", "region": "Cali-AMV"}