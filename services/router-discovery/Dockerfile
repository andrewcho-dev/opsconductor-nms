FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl snmp libsnmp-dev && \
    mkdir -p /root/.pysnmp/mibs && \
    rm -rf /var/lib/apt/lists/*

# With build context set to project root, copy requirements and app from services/router-discovery
COPY services/router-discovery/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir pysmi

COPY services/router-discovery/app/ ./app/
COPY services/state-server/snmp_routing.py ./snmp_routing.py

ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV DATABASE_URL=postgresql://opsconductor:opsconductor@postgres:5432/opsconductor
ENV PORT=8000

RUN python -c "from pysmi.compiler import MibCompiler; from pysmi.reader import FileReader; from pysmi.writer import PySnmpWriter; import os, sys; \
compiler = MibCompiler(FileReader('/usr/share/snmp/mibs'), PySnmpWriter(os.path.expanduser('~/.pysnmp/mibs'))); \
mibs = ['IP-MIB', 'IP-FORWARD-MIB', 'IF-MIB', 'TCP-MIB', 'UDP-MIB', 'SNMPv2-MIB']; \
[compiler.compileMibs(m, enforceConstraints=False) for m in mibs]" 2>&1 || echo "Warning: MIB compilation failed, will use online source"

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
