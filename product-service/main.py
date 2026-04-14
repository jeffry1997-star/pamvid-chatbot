import logging
import os
from fastapi import FastAPI, HTTPException
from databases import Database
from pydantic import BaseModel
from typing import Optional, List
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@db-products:5432/products_db")
database = Database(DATABASE_URL)

app = FastAPI(title="Product Service", description="Gestión de Productos - Pamvid Ventas")

# --- 1. MODELOS DE DATOS ---
class ProductCreate(BaseModel):
    name: str
    description: str
    price: float
    stock: int
    category: str
    image_url: Optional[str] = None

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = None
    category: Optional[str] = None
    image_url: Optional[str] = None

class ProductResponse(BaseModel):
    id: int
    name: str
    description: str
    price: float
    stock: int
    category: str
    image_url: Optional[str]
    is_active: bool

# --- 2. CONEXIÓN A LA BASE DE DATOS ---
@app.on_event("startup")
async def startup():
    logger.info("🔔 Product Service starting up...")
    for i in range(10):
        try:
            await database.connect()
            # Crear tabla de productos
            query = """
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                price DECIMAL(10,2) NOT NULL,
                stock INTEGER DEFAULT 0,
                category TEXT,
                image_url TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
            await database.execute(query=query)
            logger.info("✅ Product Service connected to DB")
            break
        except Exception as e:
            logger.warning(f"⏳ Waiting for db-products... attempt {i+1}, error: {e}")
            await asyncio.sleep(3)

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# --- 3. RUTAS CRUD ---

@app.get("/", response_model=List[ProductResponse])
async def list_products(category: str = None, active_only: bool = True):
    """Lista todos los productos, opcionalmente filtrados por categoría"""
    logger.info(f"Fetching products - category: {category}, active_only: {active_only}")
    if category:
        query = "SELECT * FROM products WHERE category = :category"
        if active_only:
            query += " AND is_active = TRUE"
        return await database.fetch_all(query=query, values={"category": category})
    else:
        if active_only:
            query = "SELECT * FROM products WHERE is_active = TRUE"
        else:
            query = "SELECT * FROM products"
        return await database.fetch_all(query=query)

@app.get("/search")
async def search_products(q: str):
    """Busca productos por nombre o descripción"""
    query = """
        SELECT * FROM products 
        WHERE is_active = TRUE 
        AND (name ILIKE :q OR description ILIKE :q)
    """
    return await database.fetch_all(query=query, values={"q": f"%{q}%"})

@app.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: int):
    """取得单个产品详情"""
    query = "SELECT * FROM products WHERE id = :id"
    product = await database.fetch_one(query=query, values={"id": product_id})
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return product

@app.post("/")
async def create_product(product: ProductCreate):
    """Crea un nuevo producto"""
    logger.info(f"Creating product: {product.name}")
    query = """
        INSERT INTO products(name, description, price, stock, category, image_url)
        VALUES (:name, :description, :price, :stock, :category, :image_url)
        RETURNING id
    """
    values = {
        "name": product.name,
        "description": product.description,
        "price": product.price,
        "stock": product.stock,
        "category": product.category,
        "image_url": product.image_url
    }
    result = await database.fetch_one(query=query, values=values)
    return {"id": result["id"], "status": "Producto creado"}

@app.put("/{product_id}")
async def update_product(product_id: int, product: ProductUpdate):
    """Actualiza un producto"""
    # Primero verificamos que existe
    query = "SELECT * FROM products WHERE id = :id"
    existing = await database.fetch_one(query=query, values={"id": product_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    
    # Construimos la consulta dinámicamente
    updates = []
    values = {"id": product_id}
    
    if product.name is not None:
        updates.append("name = :name")
        values["name"] = product.name
    if product.description is not None:
        updates.append("description = :description")
        values["description"] = product.description
    if product.price is not None:
        updates.append("price = :price")
        values["price"] = product.price
    if product.stock is not None:
        updates.append("stock = :stock")
        values["stock"] = product.stock
    if product.category is not None:
        updates.append("category = :category")
        values["category"] = product.category
    if product.image_url is not None:
        updates.append("image_url = :image_url")
        values["image_url"] = product.image_url
    
    if updates:
        query = f"UPDATE products SET {', '.join(updates)} WHERE id = :id"
        await database.execute(query=query, values=values)
    
    return {"status": "Producto actualizado"}

@app.delete("/{product_id}")
async def delete_product(product_id: int, hard_delete: bool = False):
    """Elimina un producto (soft delete por defecto)"""
    if hard_delete:
        query = "DELETE FROM products WHERE id = :id"
        await database.execute(query=query, values={"id": product_id})
        return {"status": "Producto eliminado permanentemente"}
    else:
        query = "UPDATE products SET is_active = FALSE WHERE id = :id"
        await database.execute(query=query, values={"id": product_id})
        return {"status": "Producto desactivado (soft delete)"}

@app.patch("/{product_id}/stock")
async def update_stock(product_id: int, quantity: int):
    """Actualiza el stock de un producto (positivo para agregar, negativo para reducir)"""
    # Verificamos que existe y obtenemos el stock actual
    query = "SELECT * FROM products WHERE id = :id"
    product = await database.fetch_one(query=query, values={"id": product_id})
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    
    new_stock = product["stock"] + quantity
    if new_stock < 0:
        raise HTTPException(status_code=400, detail="Stock insuficiente")
    
    query = "UPDATE products SET stock = :new_stock WHERE id = :id"
    await database.execute(query=query, values={"id": product_id, "new_stock": new_stock})
    return {"id": product_id, "new_stock": new_stock}

# --- 4. MONITOREO ---
@app.get("/health")
async def health_check():
    return {"status": "online", "service": "product-service"}