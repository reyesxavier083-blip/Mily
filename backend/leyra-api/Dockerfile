FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LEYRA_WEB_DIR=/app/web \
    LEYRA_DATA_DIR=/data

WORKDIR /app
COPY backend/leyra-api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY leyra_core ./leyra_core
COPY mily_core ./mily_core
COPY backend/leyra-api ./backend/leyra-api
COPY web ./web

RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"

CMD ["python", "backend/leyra-api/run.py", "--host", "0.0.0.0", "--port", "8080"]
