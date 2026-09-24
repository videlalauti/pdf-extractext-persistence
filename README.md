# pdf-extractext-persistence

Servicio de persistencia de documentos extraídos de PDFs, expuesto vía FastAPI.

## Instalación

```bash
pip install -r requirements.txt
```

## Cómo correr

```bash
uvicorn main:app --reload --port 8003
```

## Cómo correr los tests

```bash
pytest tests/ -v
```

## Variables de entorno

El servicio necesita las siguientes variables de entorno (ver `.env.example`):

| Variable | Valor por defecto |
| --- | --- |
| `MONGODB_HOST` | `mongo` |
| `MONGODB_PORT` | `27017` |
| `MONGODB_ROOT_USERNAME` | `admin` |
| `MONGODB_ROOT_PASSWORD` | `changeme` |
| `MONGODB_DATABASE_NAME` | `pdf_extractext` |
| `MONGODB_AUTH_SOURCE` | `admin` |