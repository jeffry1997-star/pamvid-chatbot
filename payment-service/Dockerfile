# Imagen base para la Capa de Aplicación
FROM python:3.11-slim

# Directorio de trabajo del microservicio
WORKDIR /app

# Copiamos e instalamos dependencias para que el servicio se comunique por red
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el código de la Lógica de Negocio
COPY . .

# Comando para iniciar el Proceso independiente
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]