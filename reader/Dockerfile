FROM python:3-slim

WORKDIR /app

RUN pip install --upgrade pip
RUN pip install pyserial crcmod

COPY strom_reader.py /app/strom_reader.py
COPY sqlite_store.py /app/sqlite_store.py
COPY healthcheck.py /app/healthcheck.py

HEALTHCHECK --interval=60s --timeout=15s --start-period=5m --retries=3 \
    CMD ["python3", "/app/healthcheck.py"]
CMD ["python3", "/app/strom_reader.py"]
