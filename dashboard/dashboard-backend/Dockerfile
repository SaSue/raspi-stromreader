FROM python:3-slim

WORKDIR /app

RUN pip install --upgrade pip
RUN pip install flask

COPY dashboard-backend.py /app/dashboard-backend.py
COPY healthcheck.py /app/healthcheck.py

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD ["python3", "/app/healthcheck.py"]
CMD ["python3", "/app/dashboard-backend.py"] 
