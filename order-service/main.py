import os
from fastapi import FastAPI
from databases import Database
from pydantic import BaseModel # Importante para el Body JSON

# Modelo para recibir los datos
class Order(BaseModel):
    item: str
    quantity: int

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@db-orders:5432/orders_db")
database = Database(DATABASE_URL)

app = FastAPI(title="Pamvid Order Service")

@app.on_event("startup")
async def startup():
    await database.connect()
    query = """
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            item VARCHAR(100),
            quantity INTEGER
        )
    """
    await database.execute(query=query)

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

@app.post("/create-order")
async def create_order(order: Order): # <--- Ahora usamos el modelo
    query = "INSERT INTO orders(item, quantity) VALUES (:item, :quantity)"
    values = {"item": order.item, "quantity": order.quantity}
    await database.execute(query=query, values=values)
    
    return {
        "status": "Pedido guardado en base de datos",
        "order": order
    }