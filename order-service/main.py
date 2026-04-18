import os
import asyncio
import logging
import traceback
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from databases import Database
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_ZwStrQ3RbPc1@ep-autumn-art-amm4xi1w-pooler.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")
database = Database(DATABASE_URL)

app = FastAPI(title="Order Service")

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


class OrderIn(BaseModel):
    item: str
    quantity: int
    user_id: int


@app.on_event("startup")
async def startup():
    logger.info("📦 Order Service starting up...")
    for i in range(10):
        try:
            await database.connect()
            query = """
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    item TEXT,
                    quantity INTEGER,
                    user_id INTEGER,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            await database.execute(query=query)
            # Agregar columnas si existen las tablas antiguas
            await database.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS user_id INTEGER")
            await database.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'")
            await database.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            logger.info("✅ Order Service connected to DB")
            break
        except Exception as e:
            logger.warning(f"⏳ Waiting for DB... attempt {i+1}, error: {e}")
            await asyncio.sleep(3)


@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()


@app.get("/health")
async def health_check():
    return {"status": "online", "service": "order-service"}


@app.get("/")
async def list_orders():
    query = "SELECT * FROM orders"
    return await database.fetch_all(query=query)


@app.post("/create-order")
async def create_order(order: OrderIn):
    logger.info(f"Creando orden para usuario {order.user_id}: {order.item}")
    query = "INSERT INTO orders(item, quantity, user_id, status) VALUES (:item, :quantity, :user_id, :status)"
    values = {"item": order.item, "quantity": order.quantity, "user_id": order.user_id, "status": "completed"}
    await database.execute(query=query, values=values)
    return {"status": "Order created in DB", "user_id": order.user_id, "item": order.item}