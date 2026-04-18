import os
import logging
import random
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from databases import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_ZwStrQ3RbPc1@ep-autumn-art-amm4xi1w-pooler.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")
database = Database(DATABASE_URL)

app = FastAPI(title="Payment Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    for i in range(10):
        try:
            await database.connect()
            query = """
                CREATE TABLE IF NOT EXISTS payments (
                    id SERIAL PRIMARY KEY,
                    order_id INTEGER,
                    amount DECIMAL(10,2),
                    method TEXT,
                    status TEXT DEFAULT 'pending',
                    transaction_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            await database.execute(query=query)
            logger.info("✅ Payment Service connected to DB")
            break
        except Exception as e:
            logger.warning(f"⏳ Waiting for DB... attempt {i+1}, error: {e}")
            await asyncio.sleep(3)


@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()


@app.get("/health")
async def health_check():
    return {"status": "online", "service": "payment-service"}

# 1. Modelo para recibir el JSON del Gateway
class PaymentIn(BaseModel):
    order_id: int
    amount: float
    method: str

@app.get("/")
def read_root():
    return {"message": "Servicio de Pagos de Pamvid activo"}

# 2. Ruta para procesar el pago
@app.post("/process-payment")
async def process_payment(payment: PaymentIn):
    logger.info(f"Procesando pago de {payment.amount} para la orden {payment.order_id}")
    
    transaction_id = f"PAM-TX-{random.randint(1000, 9999)}"
    status = "Approved"
    
    # Guardar el pago en la base de datos
    try:
        await database.execute(
            query="""
                INSERT INTO payments(order_id, amount, method, status, transaction_id)
                VALUES (:order_id, :amount, :method, :status, :transaction_id)
            """,
            values={
                "order_id": payment.order_id,
                "amount": payment.amount,
                "method": payment.method,
                "status": status,
                "transaction_id": transaction_id
            }
        )
        logger.info(f"Pago guardado: transaction_id={transaction_id}")
    except Exception as e:
        logger.error(f"Error al guardar pago: {e}")
    
    return {
        "status": status,
        "transaction_id": transaction_id,
        "order_id": payment.order_id,
        "method": payment.method
    }