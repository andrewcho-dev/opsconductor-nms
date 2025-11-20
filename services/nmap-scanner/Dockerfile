FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    nmap \
    nmap-common \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

CMD ["python", "-u", "app/main.py"]
