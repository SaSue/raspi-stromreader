FROM python:3.13-slim

WORKDIR /app

RUN pip install pyserial crcmod

COPY strom_reader.py /app/strom_reader.py

CMD ["python3", "/app/strom_reader.py"]
