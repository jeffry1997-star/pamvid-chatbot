# 1. Imagen base de Python para la Capa de Aplicación [1]
FROM python:3.11-slim

# 2. Definimos el directorio de trabajo
WORKDIR /app

# 3. Copiamos e instalamos las dependencias (FastAPI, httpx, etc.)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copiamos el código del Enrutador [1]
COPY . .

# 5. Comando para iniciar el Proceso del microservicio [1]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]