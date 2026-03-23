from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Payment Service")

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
    # Aquí simulas la lógica con una pasarela (PSE, Tarjeta, etc.)
    print(f"Procesando pago de {payment.amount} para la orden {payment.order_id}")
    
    return {
        "status": "Approved",
        "transaction_id": "PAM-TX-9988",
        "order_id": payment.order_id,
        "method": payment.method
    }