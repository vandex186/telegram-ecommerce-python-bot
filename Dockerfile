FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV TZ=UTC

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y apscheduler || true

COPY . .

# config.py or env vars must be provided at runtime
CMD ["python", "bot.py"]
