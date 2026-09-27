FROM python:3.11-slim
WORKDIR /app
# Render deploys backend/ with render.yaml (not this image).
# Compose builds from the repo root so the image can also see ml/ and sim/.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY ml ./ml
COPY config ./config
COPY sim ./sim
ENV PYTHONPATH=/app/backend:/app/ml:/app
WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
