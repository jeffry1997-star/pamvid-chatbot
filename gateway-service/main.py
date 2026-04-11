from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
import httpx
import logging
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional, List

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 1. MODELOS DE DATOS (Para que Swagger sea interactivo) ---
class OrderCreate(BaseModel):
    item: str       
    quantity: int
    user_id: int

class PaymentCreate(BaseModel):
    order_id: int
    amount: float
    method: str  # ej: "PSE", "Tarjeta", "Efectivo"



# --- 2. DICCIONARIO DE SERVICIOS (Configuración de Red Interna) ---
# IMPORTANTE: Usamos el nombre del servicio definido en docker-compose.yml
# Si tus servicios corren en el puerto 80 dentro del contenedor, cambia 8000 por 80.
SERVICES = {
    "order-service": "http://order-service:80",
    "payment-service": "http://payment-service:80",

    "product-service": "http://product-service:80",
    "sales-service": "http://sales-service:80",
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Cliente asíncrono para manejar múltiples peticiones sin bloquearse
    app.state.client = httpx.AsyncClient(timeout=10.0)
    logger.info("🚀 Gateway starting up - Testing service connectivity...")
    
    # Debug: Test connectivity to all services
    for service_name, service_url in SERVICES.items():
        try:
            response = await app.state.client.get(f"{service_url}/health", timeout=5.0)
            if response.status_code == 200:
                logger.info(f"✅ {service_name} is reachable at {service_url}")
            else:
                logger.warning(f"⚠️ {service_name} responded with status {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Cannot connect to {service_name} at {service_url}: {str(e)}")
    
    yield
    logger.info("🔻 Gateway shutting down...")
    await app.state.client.aclose()

app = FastAPI(
    title="Pamvid API Gateway",
    description="Sistema de Logística y Mensajería - Cali, Colombia",
    version="1.5.0",
    lifespan=lifespan
)

# Add CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 3. RUTAS: ORDER SERVICE ---
@app.post("/order-service/create-order", tags=["Orders"])
async def create_order(order: OrderCreate):
    """Crea una nueva orden de pedido en el sistema."""
    url = f"{SERVICES['order-service']}/create-order"
    try:
        logger.info(f"POST request to {url}")
        response = await app.state.client.post(url, json=order.model_dump())
        logger.info(f"Response status: {response.status_code}, body: {response.text}")
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        logger.error(f"Error creating order: {str(e)}")
        raise HTTPException(status_code=502, detail=f"Error de conexión con Orders: {str(e)}")

@app.get("/order-service/all", tags=["Orders"])
async def get_all_orders():
    """Consulta todas las órdenes registradas."""
    url = f"{SERVICES['order-service']}/"
    try:
        logger.info(f"GET request to {url}")
        response = await app.state.client.get(url)
        logger.info(f"Response status: {response.status_code}")
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        logger.error(f"Error fetching orders: {str(e)}")
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



# --- 6. RUTAS: PRODUCT SERVICE ---
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
    """Consulta todos los productos del catálogo."""
    url = f"{SERVICES['product-service']}/"
    if category:
        url += f"?category={category}"
    try:
        response = await app.state.client.get(url)
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error de conexión con Products: {str(e)}")

@app.get("/product-service/{product_id}", tags=["Products"])
async def get_product(product_id: int):
    """Obtiene los detalles de un producto específico."""
    url = f"{SERVICES['product-service']}/{product_id}"
    try:
        response = await app.state.client.get(url)
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Producto no encontrado.")

@app.post("/product-service/create", tags=["Products"])
async def create_product(product: ProductCreate):
    """Crea un nuevo producto en el catálogo."""
    url = f"{SERVICES['product-service']}/"
    try:
        response = await app.state.client.post(url, json=product.model_dump(exclude_none=True))
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error al crear producto: {str(e)}")

@app.put("/product-service/{product_id}", tags=["Products"])
async def update_product(product_id: int, product: ProductUpdate):
    """Actualiza un producto del catálogo."""
    url = f"{SERVICES['product-service']}/{product_id}"
    try:
        response = await app.state.client.put(url, json=product.model_dump(exclude_none=True))
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error al actualizar producto: {str(e)}")

@app.delete("/product-service/{product_id}", tags=["Products"])
async def delete_product(product_id: int):
    """Elimina un producto del catálogo (soft delete)."""
    url = f"{SERVICES['product-service']}/{product_id}"
    try:
        response = await app.state.client.delete(url)
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error al eliminar producto: {str(e)}")

# --- 7. RUTAS: SALES SERVICE ---
class SaleItem(BaseModel):
    product_id: int
    quantity: int

class SaleCreate(BaseModel):
    user_id: int
    items: List[SaleItem]
    payment_method: str
    notes: str = None

@app.post("/sales-service/create-sale", tags=["Sales"])
async def create_sale(sale: SaleCreate):
    """Crea una nueva venta."""
    url = f"{SERVICES['sales-service']}/"
    try:
        response = await app.state.client.post(url, json=sale.model_dump(exclude_none=True))
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error de conexión con Sales: {str(e)}")

@app.get("/sales-service/all", tags=["Sales"])
async def get_all_sales(user_id: int = None):
    """Consulta todas las ventas realizadas."""
    url = f"{SERVICES['sales-service']}/"
    if user_id:
        url += f"?user_id={user_id}"
    try:
        response = await app.state.client.get(url)
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"No se pudo contactar al servicio de ventas.")

@app.get("/sales-service/{sale_id}", tags=["Sales"])
async def get_sale(sale_id: int):
    """Obtiene los detalles de una venta específica."""
    url = f"{SERVICES['sales-service']}/{sale_id}"
    try:
        response = await app.state.client.get(url)
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Venta no encontrada.")

# --- 8. MONITOREO ---
@app.get("/health", tags=["System"])
async def health_check():
    """Verifica si el Gateway está operativo."""
    return {"status": "online", "region": "Cali-AMV"}