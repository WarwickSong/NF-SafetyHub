FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

COPY . .

RUN useradd --create-home --shell /usr/sbin/nologin safetyhub \
    && mkdir -p /app/data \
    && chown -R safetyhub:safetyhub /app

USER safetyhub

EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host ${UVICORN_HOST:-0.0.0.0} --port ${UVICORN_PORT:-8000} --workers ${UVICORN_WORKERS:-4} --proxy-headers --forwarded-allow-ips=${UVICORN_FORWARDED_ALLOW_IPS:-*}"]
