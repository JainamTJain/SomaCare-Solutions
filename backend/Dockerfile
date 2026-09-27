FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY ml ./ml
COPY config ./config
COPY sim ./sim
ENV PYTHONPATH=/app/backend:/app/ml:/app
EXPOSE 8000
CMD ["uvicorn", "turnwise.main:app", "--host", "0.0.0.0", "--port", "8000"]
