FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN TMPDIR=/tmp pip install --no-cache-dir --no-clean -r requirements.txt \
    && rm -rf /tmp/pip-*

COPY . .

ENV PYTHONPATH=/app

CMD ["python", "runners/run_container_job.py"]
