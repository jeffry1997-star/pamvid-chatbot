from fastapi import FastAPI

app = FastAPI(title="Pamvid Payment Service")

@app.get("/")
def read_root():
    return {"message": "Servicio de Pagos de Pamvid activo"}