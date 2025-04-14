FROM python:3-slim

WORKDIR /app

RUN pip install flask

COPY dashboard-backend.py /app/dashboard-backend.py

CMD ["python3", "/app/dashboard-backend.py"] 