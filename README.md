# pdf-extractext-persistence

Servicio de persistencia de documentos extraídos de PDFs, expuesto vía FastAPI.
Es el dueño de la colección `documents` en MongoDB y el responsable del dedup
por `checksum` (SHA-256 de los bytes del PDF, que es la identidad de duplicado).

## Endpoints

| Método | Ruta | Respuesta |
| --- | --- | --- |
| `POST` | `/documents` | `201` creado · `409` checksum duplicado |
| `GET` | `/documents` | `200` lista |
| `GET` | `/documents/by-checksum/{checksum}` | `200` · `404` |
| `GET` | `/documents/{id}` | `200` · `404` |
| `PUT` | `/documents/{id}` | `200` · `400` sin campos · `404` · `409` checksum duplicado |
| `DELETE` | `/documents/{id}` | `204` · `404` |
| `GET` | `/health` | `200` healthy · `503` si Mongo no responde |

El `409` es un **resultado de negocio** ("ese PDF ya existe"), no un error de
infraestructura: el cliente lo resuelve con `GET /documents/by-checksum/{checksum}`.

## Instalación

```bash
pip install -r requirements.txt
```

## Cómo correr

```bash
uvicorn main:app --reload --port 8003
```

En un contenedor arranca `entrypoint.py`, que lee `PORT` (default `8000`); el
`HEALTHCHECK` del `Dockerfile` consulta ese mismo puerto.

## Cómo correr los tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Lint

```bash
ruff check .
```

## Variables de entorno

El servicio necesita las siguientes variables de entorno (ver `.env.example`):

| Variable | Valor por defecto | Para qué |
| --- | --- | --- |
| `MONGODB_HOST` | `mongo` | Host de MongoDB |
| `MONGODB_PORT` | `27017` | Puerto de MongoDB |
| `MONGODB_ROOT_USERNAME` | `admin` | Usuario (se URL-encodéa al armar la URL) |
| `MONGODB_ROOT_PASSWORD` | `changeme` | Password (se URL-encodéa al armar la URL) |
| `MONGODB_DATABASE_NAME` | `pdf_extractext` | Base de datos |
| `MONGODB_AUTH_SOURCE` | `admin` | Base contra la que se autentica |
| `PORT` | `8000` | Puerto de escucha (12-Factor VII) |
| `CORS_ORIGINS` | `http://localhost` | Orígenes permitidos, separados por coma |

## Notas de diseño

- **Deduplicación sin carrera:** en el arranque se crea el índice único de
  `checksum` (`DocumentRepository.ensure_indexes`). El `find_one` previo en
  `create` es solo el camino rápido; la garantía real es el índice, y un
  `DuplicateKeyError` se traduce a `DuplicateDocumentError` → `409`. En
  `update` se usa un único `find_one_and_update` atómico por el mismo motivo.
- **Inyección de dependencias:** el router no instancia el repositorio;
  lo recibe por `Depends(get_repository)` y los tests lo sustituyen con
  `app.dependency_overrides`.
- **Observabilidad:** los logs van a stdout con `request_id`, tomado del header
  `X-Request-Id` (o generado) vía `pdf-extractext-shared`.
- **Deuda técnica — `motor` deprecado:** Motor queda deprecado el 14/05/2026
  (un año después del release de producción del driver async de PyMongo) y
  recibe bug fixes críticos hasta el 14/05/2027. La migración recomendada es al
  driver async de PyMongo. Se mantiene `motor==3.7.1`; migrar queda fuera de
  alcance.


## Arquitectura N capas y demostracion en MongoDB Compass

- **Presentacion (HTTP):** `routes.py` expone el CRUD, modelos Pydantic y
  traduce excepciones de dominio a status 201/404/409/400/500.
- **Aplicacion:** `persistence/service.py` encapsula casos de uso CRUD sobre
  el puerto `DocumentStore`, sin importar FastAPI ni Mongo.
- **Acceso a datos:** `persistence/repository.py` implementa el repositorio
  MongoDB (Motor), maneja el índice único de checksum y el `_id`.
- **Infraestructura:** `persistence/mongodb_connection.py` configura y
  conecta MongoDB mediante variables de entorno; `main.py` administra
  startup, health y cierre de conexion.

**Qué persiste:** el texto extraido como `content`, el identificador
`_id` (String/UUID) y `checksum` (String/SHA-256). **No guarda el
binario original del PDF.** Mongo usa un modelo de documentos flexible;
`Schema` en Compass es una inspeccion de los campos observados, NO un
validador JSON Schema requerido.

Para demostrar persistencia desde el equipo del expositor:

1. En el repo Infra, `python scripts/dev.py start` y
   `python scripts/dev.py compass-on`.
2. En Infra, `python scripts/dev.py upload --unique`.
3. Compass: URI `mongodb://127.0.0.1:27017/`, usuario/password de
   `infra/.env` (authSource `admin`).
4. Abrir `pdf_extractext > documents > Documents`; filtrar por el
   `_id` que imprime el script; mostrar `content` y `checksum`.
5. Abrir `Schema` para analizar campos e `Indexes` para mostrar
   unicidad de `checksum`.
6. En Infra, `python scripts/dev.py compass-off` para cerrar el puerto.
