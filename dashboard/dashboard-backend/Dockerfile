FROM python:3-slim

ENV TZ=UTC

WORKDIR /app

RUN pip install --upgrade pip
RUN pip install flask tzdata

COPY dashboard-backend.py /app/dashboard-backend.py
COPY healthcheck.py /app/healthcheck.py

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD ["python3", "/app/healthcheck.py"]
CMD ["python3", "/app/dashboard-backend.py"] 
