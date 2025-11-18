FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY populate_mibs.py ./populate_mibs.py
COPY migrate_mib_ids.py ./migrate_mib_ids.py
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
