FROM python:3.11-slim

WORKDIR /app

RUN pip install pyserial

COPY strom_raw_dump.py /app/strom_raw_dump.py

CMD ["python3", "/app/strom_raw_dump.py"]
