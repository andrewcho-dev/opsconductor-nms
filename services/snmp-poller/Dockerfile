FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y snmp expect openssh-client && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir psycopg2-binary pexpect

COPY poller.py /app/

CMD ["python", "-u", "poller.py"]
