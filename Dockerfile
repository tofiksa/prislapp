FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
CMD ["sh", "-c", "python -m scripts.run_migrations && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
