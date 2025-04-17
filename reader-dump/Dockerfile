FROM python:3-slim

WORKDIR /app

RUN pip install --upgrade pip
RUN pip install pyserial

COPY reader-raw-dump.py /app/reader-raw-dump.py

CMD ["python3", "/app/reader-raw-dump.py"]
