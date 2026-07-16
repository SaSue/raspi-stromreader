FROM python:3-slim

WORKDIR /app

RUN pip install --upgrade pip
RUN pip install pyserial crcmod

COPY strom_reader.py /app/strom_reader.py
COPY sqlite_store.py /app/sqlite_store.py

CMD ["python3", "/app/strom_reader.py"]
