import logging
from fastapi import FastAPI, HTTPException
from databases import Database
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import asyncio
import httpx

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = "postgresql://user:pass@db-sales:5432/sales_db"
PRODUCT_SERVICE_URL = "http://product-service:80"

database = Database(DATABASE_URL)

app = FastAPI(title="Sales Service", description="Servicio de Ventas - Pamvid")

# --- 1. MODELOS DE DATOS ---
class SaleItem(BaseModel):
    product_id: int
    quantity: int

class SaleCreate(BaseModel):
    user_id: int
    items: List[SaleItem]
    payment_method: str  # "PSE", "Tarjeta", "Efectivo", "Transferencia"
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
    items: List[SaleItemResponse]
    total: float
    payment_method: str
    status: str
    notes: Optional[str]
    created_at: str

# --- 2. CONEXIÓN A LA BASE DE DATOS ---
@app.on_event("startup")
async def startup():
    logger.info("💰 Sales Service starting up...")
    for i in range(10):
        try:
            await database.connect()
            # Crear tabla de ventas
            query = """
            CREATE TABLE IF NOT EXISTS sales (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                total DECIMAL(10,2) NOT NULL,
                payment_method TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
            await database.execute(query=query)
            
            # Crear tabla de items de venta
            query2 = """
            CREATE TABLE IF NOT EXISTS sale_items (
                id SERIAL PRIMARY KEY,
                sale_id INTEGER REFERENCES sales(id),
                product_id INTEGER NOT NULL,
                product_name TEXT,
                quantity INTEGER NOT NULL,
                unit_price DECIMAL(10,2) NOT NULL,
                subtotal DECIMAL(10,2) NOT NULL
            )
            """
            await database.execute(query=query2)
            
            logger.info("✅ Sales Service connected to DB")
            break
        except Exception as e:
            logger.warning(f"⏳ Waiting for db-sales... attempt {i+1}, error: {e}")
            await asyncio.sleep(3)

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# Helper: Obtener producto del Product Service
async def get_product(product_id: int) -> dict:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{PRODUCT_SERVICE_URL}/{product_id}")
            if response.status_code != 200:
                raise HTTPException(status_code=404, detail="Producto no encontrado")
            return response.json()
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Product Service no disponible")

# --- 3. RUTAS DE VENTAS ---

@app.post("/", response_model=SaleResponse)
async def create_sale(sale: SaleCreate):
    """Crea una nueva venta"""
    logger.info(f"Creating sale for user_id: {sale.user_id}, items: {len(sale.items)}")
    
    if not sale.items:
        raise HTTPException(status_code=400, detail="Debe incluir al menos un producto")
    
    # Validar productos y calcular total
    sale_items = []
    total = 0.0
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for item in sale.items:
            # Consultar producto
            try:
                response = await client.get(f"{PRODUCT_SERVICE_URL}/{item.product_id}")
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=404, 
                        detail=f"Producto {item.product_id} no encontrado"
                    )
                product = response.json()
            except httpx.RequestError:
                raise HTTPException(
                    status_code=503, 
                    detail="Product Service no disponible"
                )
            
            # Validar stock
            if product["stock"] < item.quantity:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Stock insuficiente para {product['name']}. Disponible: {product['stock']}"
                )
            
            # Calcular subtotal
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
    
    # Crear la venta en la base de datos
    query = """
        INSERT INTO sales(user_id, total, payment_method, status, notes)
        VALUES (:user_id, :total, :payment_method, :status, :notes)
        RETURNING id, created_at
    """
    values = {
        "user_id": sale.user_id,
        "total": total,
        "payment_method": sale.payment_method,
        "status": "completed",
        "notes": sale.notes
    }
    sale_result = await database.fetch_one(query=query, values=values)
    sale_id = sale_result["id"]
    
    # Insertar los items de la venta
    for item in sale_items:
        query = """
            INSERT INTO sale_items(sale_id, product_id, product_name, quantity, unit_price, subtotal)
            VALUES (:sale_id, :product_id, :product_name, :quantity, :unit_price, :subtotal)
        """
        await database.fetch_one(query=query, values={
            "sale_id": sale_id,
            "product_id": item["product_id"],
            "product_name": item["product_name"],
            "quantity": item["quantity"],
            "unit_price": item["unit_price"],
            "subtotal": item["subtotal"]
        })
        
        # Actualizar stock del producto (reducir)
        try:
            async with httpx.AsyncClient() as client:
                await client.patch(
                    f"{PRODUCT_SERVICE_URL}/{item['product_id']}/stock",
                    json={"quantity": -item["quantity"]}
                )
        except:
            pass  # Si falla la actualización de stock, continuamos
    
    # Devolver la respuesta
    return {
        "id": sale_id,
        "user_id": sale.user_id,
        "items": [SaleItemResponse(**item) for item in sale_items],
        "total": total,
        "payment_method": sale.payment_method,
        "status": "completed",
        "notes": sale.notes,
        "created_at": sale_result["created_at"].isoformat()
    }

@app.get("/", response_model=List[SaleResponse])
async def list_sales(user_id: int = None, limit: int = 50):
    """Lista todas las ventas"""
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
        sales_list = await database.fetch_all(
            query=query, 
            values={"user_id": user_id, "limit": limit}
        )
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
    
    # Formatear respuesta
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
            items=items,
            total=float(sale["total"]),
            payment_method=sale["payment_method"],
            status=sale["status"],
            notes=sale["notes"],
            created_at=sale["created_at"].isoformat() if sale["created_at"] else ""
        ))
    
    return result

@app.get("/{sale_id}", response_model=SaleResponse)
async def get_sale(sale_id: int):
    """Obtiene los detalles de una venta"""
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
        items=items,
        total=float(sale["total"]),
        payment_method=sale["payment_method"],
        status=sale["status"],
        notes=sale["notes"],
        created_at=sale["created_at"].isoformat() if sale["created_at"] else ""
    )

# --- 4. MONITOREO ---
@app.get("/health")
async def health_check():
    return {"status": "online", "service": "sales-service"}