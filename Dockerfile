# python:3.14-slim-bookworm (3.14.7) fijado por digest para builds reproducibles.
# Actualizar con: docker buildx imagetools inspect python:3.14-slim-bookworm
FROM python:3.14-slim-bookworm@sha256:82bc3c539b8813ada9d68c63b40158fa002f7f33de9bf3312a3dfdc0620dff56

RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY routes.py .
COPY persistence/ persistence/

USER appuser

EXPOSE 8000

# /health ya hace ping a Mongo, asi que un 503 aqui es "Mongo no responde".
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health')"]

# Forma shell (no exec) para que el puerto venga del entorno (12-Factor VII).
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
