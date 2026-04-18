import logging
import os
import traceback
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from databases import Database
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import asyncio
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_ZwStrQ3RbPc1@ep-autumn-art-amm4xi1w-pooler.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")
PRODUCT_SERVICE_URL = "http://product-service:80"
PAYMENT_SERVICE_URL = "http://payment-service:80"
ORDER_SERVICE_URL = "http://order-service:80"
NOTIFICATION_SERVICE_URL = "http://notification-service:80"

database = Database(DATABASE_URL)

app = FastAPI(title="Sales Service", description="Servicio de Ventas - Pamvid")

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

# --- MODELOS ---
class SaleItem(BaseModel):
    product_id: int
    quantity: int

class SaleCreate(BaseModel):
    user_id: int
    user_name: str = ""
    items: List[SaleItem]
    payment_method: str
    notes: Optional[str] = None

class SaleItemResponse(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    unit_price: float
    subtotal: float

class SaleResponse(BaseModel):
    id: int
    user_id: int
    user_name: str
    items: List[SaleItemResponse]
    total: float
    payment_method: str
    status: str
    notes: Optional[str]
    created_at: str

# --- STARTUP / SHUTDOWN ---
@app.on_event("startup")
async def startup():
    logger.info("💰 Sales Service starting up...")
    for i in range(10):
        try:
            await database.connect()
            await database.execute(query="""
                CREATE TABLE IF NOT EXISTS sales (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    user_name TEXT,
                    total DECIMAL(10,2) NOT NULL,
                    payment_method TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await database.execute(query="""
                ALTER TABLE sales ADD COLUMN IF NOT EXISTS user_name TEXT
            """)
            await database.execute(query="""
                CREATE TABLE IF NOT EXISTS sale_items (
                    id SERIAL PRIMARY KEY,
                    sale_id INTEGER REFERENCES sales(id),
                    product_id INTEGER NOT NULL,
                    product_name TEXT,
                    quantity INTEGER NOT NULL,
                    unit_price DECIMAL(10,2) NOT NULL,
                    subtotal DECIMAL(10,2) NOT NULL
                )
            """)
            logger.info("✅ Sales Service connected to DB")
            break
        except Exception as e:
            logger.warning(f"⏳ Waiting for db-sales... attempt {i+1}, error: {e}")
            await asyncio.sleep(3)

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# --- FIX CRÍTICO: /health DEBE ir ANTES de /{sale_id} ---
# FastAPI evalúa las rutas en orden de definición.
# Si /{sale_id} se define primero, la petición GET /health
# se interpreta como sale_id="health" → ValueError → 422.
@app.get("/health")
async def health_check():
    return {"status": "online", "service": "sales-service"}

# --- CREAR VENTA ---
@app.post("/", response_model=SaleResponse)
async def create_sale(sale: SaleCreate):
    logger.info(f"Creating sale for user_id: {sale.user_id}, user_name: '{sale.user_name}', items: {len(sale.items)}")

    if not sale.items:
        raise HTTPException(status_code=400, detail="Debe incluir al menos un producto")

    sale_items = []
    total = 0.0

    async with httpx.AsyncClient(timeout=30.0) as client:
        for item in sale.items:
            try:
                response = await client.get(f"{PRODUCT_SERVICE_URL}/{item.product_id}")
                if response.status_code != 200:
                    raise HTTPException(status_code=404, detail=f"Producto {item.product_id} no encontrado")
                product = response.json()
            except httpx.RequestError:
                raise HTTPException(status_code=503, detail="Product Service no disponible")

            if product["stock"] < item.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Stock insuficiente para '{product['name']}'. Disponible: {product['stock']}"
                )

            unit_price = float(product["price"])
            subtotal = unit_price * item.quantity
            total += subtotal
            sale_items.append({
                "product_id": item.product_id,
                "product_name": product["name"],
                "quantity": item.quantity,
                "unit_price": unit_price,
                "subtotal": subtotal
            })

    sale_result = await database.fetch_one(
        query="""
            INSERT INTO sales(user_id, user_name, total, payment_method, status, notes)
            VALUES (:user_id, :user_name, :total, :payment_method, :status, :notes)
            RETURNING id, created_at
        """,
        values={
            "user_id": sale.user_id,
            "user_name": sale.user_name,
            "total": total,
            "payment_method": sale.payment_method,
            "status": "completed",
            "notes": sale.notes
        }
    )
    sale_id = sale_result["id"]

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Procesar pago
        try:
            payment_response = await client.post(
                f"{PAYMENT_SERVICE_URL}/process-payment",
                json={
                    "order_id": sale_id,
                    "amount": total,
                    "method": sale.payment_method
                }
            )
            if payment_response.status_code == 200:
                payment_data = payment_response.json()
                logger.info(f"Pago procesado: {payment_data.get('transaction_id')}")
                
                # Guardar info del pago
                await database.execute(
                    query="INSERT INTO payments(order_id, amount, method, status, transaction_id) VALUES (:order_id, :amount, :method, :status, :transaction_id)",
                    values={
                        "order_id": sale_id,
                        "amount": total,
                        "method": sale.payment_method,
                        "status": payment_data.get("status", "completed"),
                        "transaction_id": payment_data.get("transaction_id", "")
                    }
                )
        except Exception as e:
            logger.warning(f"Error al procesar pago: {e}")

        # 2. Crear orden
        try:
            order_items = ", ".join([f"{item['product_name']} x{item['quantity']}" for item in sale_items])
            order_response = await client.post(
                f"{ORDER_SERVICE_URL}/create-order",
                json={
                    "item": order_items,
                    "quantity": len(sale_items),
                    "user_id": sale.user_id
                }
            )
            if order_response.status_code == 200:
                logger.info("Orden creada correctamente")
        except Exception as e:
            logger.warning(f"Error al crear orden: {e}")

    # 3. Guardar items de venta y actualizar stock
    for item in sale_items:
        await database.execute(
            query="""
                INSERT INTO sale_items(sale_id, product_id, product_name, quantity, unit_price, subtotal)
                VALUES (:sale_id, :product_id, :product_name, :quantity, :unit_price, :subtotal)
            """,
            values={"sale_id": sale_id, **item}
        )
        # Actualizar stock (best-effort)
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                await c.patch(
                    f"{PRODUCT_SERVICE_URL}/{item['product_id']}/stock",
                    json={"quantity": -item["quantity"]}
                )
        except Exception:
            pass

    # 4. Enviar notificación
    try:
        async with httpx.AsyncClient(timeout=10.0) as notif_client:
            await notif_client.post(
                f"{NOTIFICATION_SERVICE_URL}/send-notification",
                json={
                    "user_id": sale.user_id,
                    "message": f"Tu compra #{sale_id} por ${total:.2f} ha sido procesada exitosamente. Gracias por confiar en Pamvid!"
                }
            )
    except Exception as e:
        logger.warning(f"Error al enviar notificación: {e}")

    return SaleResponse(
        id=sale_id,
        user_id=sale.user_id,
        user_name=sale.user_name,
        items=[SaleItemResponse(**item) for item in sale_items],
        total=total,
        payment_method=sale.payment_method,
        status="completed",
        notes=sale.notes,
        created_at=sale_result["created_at"].isoformat()
    )

# --- LISTAR VENTAS ---
@app.get("/", response_model=List[SaleResponse])
async def list_sales(user_id: int = None, limit: int = 50):
    if user_id:
        query = """
            SELECT s.*,
                   json_agg(json_build_object(
                       'product_id', si.product_id,
                       'product_name', si.product_name,
                       'quantity', si.quantity,
                       'unit_price', si.unit_price,
                       'subtotal', si.subtotal
                   )) as items
            FROM sales s
            LEFT JOIN sale_items si ON s.id = si.sale_id
            WHERE s.user_id = :user_id
            GROUP BY s.id
            ORDER BY s.created_at DESC
            LIMIT :limit
        """
        sales_list = await database.fetch_all(query=query, values={"user_id": user_id, "limit": limit})
    else:
        query = """
            SELECT s.*,
                   json_agg(json_build_object(
                       'product_id', si.product_id,
                       'product_name', si.product_name,
                       'quantity', si.quantity,
                       'unit_price', si.unit_price,
                       'subtotal', si.subtotal
                   )) as items
            FROM sales s
            LEFT JOIN sale_items si ON s.id = si.sale_id
            GROUP BY s.id
            ORDER BY s.created_at DESC
            LIMIT :limit
        """
        sales_list = await database.fetch_all(query=query, values={"limit": limit})

    result = []
    for sale in sales_list:
        items = []
        if sale["items"]:
            for item in sale["items"]:
                if item and item.get("product_id"):
                    items.append(SaleItemResponse(**item))
        result.append(SaleResponse(
            id=sale["id"],
            user_id=sale["user_id"],
            user_name=sale.get("user_name", ""),
            items=items,
            total=float(sale["total"]),
            payment_method=sale["payment_method"],
            status=sale["status"],
            notes=sale["notes"],
            created_at=sale["created_at"].isoformat() if sale["created_at"] else ""
        ))
    return result

# --- FIX: /{sale_id} va AL FINAL para no interceptar /health ni / ---
@app.get("/{sale_id}", response_model=SaleResponse)
async def get_sale(sale_id: int):
    query = """
        SELECT s.*,
               json_agg(json_build_object(
                   'product_id', si.product_id,
                   'product_name', si.product_name,
                   'quantity', si.quantity,
                   'unit_price', si.unit_price,
                   'subtotal', si.subtotal
               )) as items
        FROM sales s
        LEFT JOIN sale_items si ON s.id = si.sale_id
        WHERE s.id = :id
        GROUP BY s.id
    """
    sale = await database.fetch_one(query=query, values={"id": sale_id})
    if not sale:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    items = []
    if sale["items"]:
        for item in sale["items"]:
            if item and item.get("product_id"):
                items.append(SaleItemResponse(**item))

    return SaleResponse(
        id=sale["id"],
        user_id=sale["user_id"],
        user_name=sale.get("user_name", ""),
        items=items,
        total=float(sale["total"]),
        payment_method=sale["payment_method"],
        status=sale["status"],
        notes=sale["notes"],
        created_at=sale["created_at"].isoformat() if sale["created_at"] else ""
    )
