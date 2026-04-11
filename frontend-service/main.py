from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Pamvid Frontend",
    description="Interfaz de venta de productos - Pamvid Cali",
    version="1.0.0"
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve the main product catalog page"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "online", "service": "frontend-service"}