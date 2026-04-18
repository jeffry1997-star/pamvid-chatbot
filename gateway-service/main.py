from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
import httpx
import logging
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OrderCreate(BaseModel):
    item: str
    quantity: int
    user_id: int

class PaymentCreate(BaseModel):
    order_id: int
    amount: float
    method: str

SERVICES = {
    "order-service":   "http://order-service:80",
    "payment-service": "http://payment-service:80",
    "user-service":    "http://user-service:80",
    "product-service": "http://product-service:80",
    "sales-service":   "http://sales-service:80",
    "notification-service": "http://notification-service:80",
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(timeout=10.0)
    logger.info("🚀 Gateway starting up - Testing service connectivity...")
    for service_name, service_url in SERVICES.items():
        try:
            response = await app.state.client.get(f"{service_url}/health", timeout=5.0)
            if response.status_code == 200:
                logger.info(f"✅ {service_name} reachable")
            else:
                logger.warning(f"⚠️  {service_name} status {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Cannot connect to {service_name}: {e}")
    yield
    logger.info("🔻 Gateway shutting down...")
    await app.state.client.aclose()

app = FastAPI(
    title="Pamvid API Gateway",
    description="Sistema de Logística y Mensajería - Cali, Colombia",
    version="1.5.0",
    lifespan=lifespan
)

# FIX: CORS definido UNA SOLA VEZ (el original lo tenía duplicado)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================
# ORDERS
# =============================================
@app.post("/order-service/create-order", tags=["Orders"])
async def create_order(order: OrderCreate):
    url = f"{SERVICES['order-service']}/create-order"
    try:
        response = await app.state.client.post(url, json=order.model_dump())
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error de conexión con Orders: {e}")

@app.get("/order-service/all", tags=["Orders"])
async def get_all_orders():
    url = f"{SERVICES['order-service']}/"
    try:
        response = await app.state.client.get(url)
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail="No se pudo contactar al servicio de órdenes.")

# =============================================
# PAYMENTS
# =============================================
@app.post("/payment-service/process", tags=["Payments"])
async def process_payment(payment: PaymentCreate):
    url = f"{SERVICES['payment-service']}/process-payment"
    try:
        response = await app.state.client.post(url, json=payment.model_dump())
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail="Error de comunicación con el servicio de pagos.")

# =============================================
# PRODUCTS
# =============================================
class ProductCreate(BaseModel):
    name: str
    description: str
    price: float
    stock: int
    category: str
    image_url: str = None

class ProductUpdate(BaseModel):
    name: str = None
    description: str = None
    price: float = None
    stock: int = None
    category: str = None
    image_url: str = None

@app.get("/product-service/all", tags=["Products"])
async def get_all_products(category: str = None):
    url = f"{SERVICES['product-service']}/"
    if category:
        url += f"?category={category}"
    try:
        response = await app.state.client.get(url)
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error de conexión con Products: {e}")

@app.get("/product-service/{product_id}", tags=["Products"])
async def get_product(product_id: int):
    url = f"{SERVICES['product-service']}/{product_id}"
    try:
        response = await app.state.client.get(url)
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail="Producto no encontrado.")

@app.post("/product-service/create", tags=["Products"])
async def create_product(product: ProductCreate):
    url = f"{SERVICES['product-service']}/"
    try:
        response = await app.state.client.post(url, json=product.model_dump(exclude_none=True))
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error al crear producto: {e}")

@app.put("/product-service/{product_id}", tags=["Products"])
async def update_product(product_id: int, product: ProductUpdate):
    url = f"{SERVICES['product-service']}/{product_id}"
    try:
        response = await app.state.client.put(url, json=product.model_dump(exclude_none=True))
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error al actualizar producto: {e}")

@app.delete("/product-service/{product_id}", tags=["Products"])
async def delete_product(product_id: int):
    url = f"{SERVICES['product-service']}/{product_id}"
    try:
        response = await app.state.client.delete(url)
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error al eliminar producto: {e}")

# =============================================
# SALES
# =============================================
class SaleItem(BaseModel):
    product_id: int
    quantity: int

class SaleCreate(BaseModel):
    user_id: int
    user_name: str = ""
    items: List[SaleItem]
    payment_method: str
    notes: str = None

@app.post("/sales-service/create-sale", tags=["Sales"])
async def create_sale(sale: SaleCreate):
    url = f"{SERVICES['sales-service']}/"
    try:
        response = await app.state.client.post(url, json=sale.model_dump(exclude_none=True))
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error de conexión con Sales: {e}")

@app.get("/sales-service/all", tags=["Sales"])
async def get_all_sales(user_id: int = None):
    url = f"{SERVICES['sales-service']}/"
    if user_id:
        url += f"?user_id={user_id}"
    try:
        response = await app.state.client.get(url)
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail="No se pudo contactar al servicio de ventas.")

@app.get("/sales-service/{sale_id}", tags=["Sales"])
async def get_sale(sale_id: int):
    url = f"{SERVICES['sales-service']}/{sale_id}"
    try:
        response = await app.state.client.get(url)
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail="Venta no encontrada.")

# =============================================
# USERS
# =============================================
class UserRegister(BaseModel):
    email: str
    password: str
    name: str
    phone: str = None

class UserLogin(BaseModel):
    email: str
    password: str

@app.post("/user-service/register", tags=["Users"])
async def register(user: UserRegister):
    url = f"{SERVICES['user-service']}/register"
    try:
        response = await app.state.client.post(url, json=user.model_dump(exclude_none=True))
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error al registrar usuario: {e}")

@app.post("/user-service/login", tags=["Users"])
async def login(user: UserLogin):
    url = f"{SERVICES['user-service']}/login"
    try:
        response = await app.state.client.post(url, json=user.model_dump())
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error al iniciar sesión: {e}")

# FIX: /me debe ir ANTES de /{user_id} si existiera — aquí ya está correcto
@app.get("/user-service/me", tags=["Users"])
async def get_me(request: Request):
    auth_header = request.headers.get('Authorization')
    url = f"{SERVICES['user-service']}/me"
    try:
        headers = {}
        if auth_header:
            headers['Authorization'] = auth_header
        response = await app.state.client.get(url, headers=headers)
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error al obtener usuario: {e}")

# =============================================
# NOTIFICATIONS
# =============================================
class NotificationRequest(BaseModel):
    user_id: int
    message: str

@app.post("/notification-service/send", tags=["Notifications"])
async def send_notification(notification: NotificationRequest):
    url = f"{SERVICES['notification-service']}/send-notification"
    try:
        response = await app.state.client.post(url, json=notification.model_dump())
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error al enviar notificación: {e}")

# =============================================
# SYSTEM
# =============================================
@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "online", "region": "Cali-AMV"}
