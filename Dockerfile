FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Render předá proměnnou PORT, FastAPI musí poslouchat na 0.0.0.0
CMD ["uvicorn","bot:app","--host","0.0.0.0","--port","${PORT}"]
