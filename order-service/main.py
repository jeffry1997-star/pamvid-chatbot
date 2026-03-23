from fastapi import FastAPI
from databases import Database
from pydantic import BaseModel
import asyncio

DATABASE_URL = "postgresql://user:pass@db-orders:5432/orders_db"
database = Database(DATABASE_URL)

app = FastAPI(title="Order Service")

# Modelo para recibir el JSON del Gateway
class OrderIn(BaseModel):
    item: str
    quantity: int
    user_id: int

@app.on_event("startup")
async def startup():
    for i in range(5):
        try:
            await database.connect()
            # Creamos la tabla si no existe
            query = "CREATE TABLE IF NOT EXISTS orders (id SERIAL PRIMARY KEY, item TEXT, quantity INTEGER)"
            await database.execute(query=query)
            print("¡Conectado a la DB y tabla lista!")
            break
        except Exception as e:
            print(f"Esperando a la DB... intento {i+1}")
            await asyncio.sleep(3)

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

@app.get("/")
async def list_orders():
    query = "SELECT * FROM orders"
    return await database.fetch_all(query=query)

@app.post("/create-order")
async def create_order(order: OrderIn):
    query = "INSERT INTO orders(item, quantity) VALUES (:item, :quantity)"
    values = {"item": order.item, "quantity": order.quantity}
    await database.execute(query=query, values=values)
    return {"status": "Order created in DB"}