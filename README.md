# Address Book API

A minimal FastAPI application for creating, updating and deleting addresses, and for finding addresses within a given distance of a location. Each address stores its coordinates, is validated on input, and is saved to SQLite.

There is no GUI. Use the built-in Swagger UI at `/docs`.

## Requirements

- Python 3.12, 3.13 or 3.14
- Git

## Run the app

### Windows (PowerShell)

```powershell
git clone https://github.com/LouisMiguelBernal/address-book-api.git
cd address-book-api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

If PowerShell blocks `Activate.ps1`, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first. If `python` is not found, use `py -3` instead.

### macOS / Linux (bash)

```bash
git clone https://github.com/LouisMiguelBernal/address-book-api.git
cd address-book-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open **http://127.0.0.1:8000/docs**.

The database file `address_book.db` is created in the folder you start the server from. Data is kept between restarts.

## Run the tests

With the virtual environment active:

```bash
pip install -r requirements-dev.txt
pytest --cov=app
ruff check .
```

The suite has 106 tests and treats any warning as a failure. GitHub Actions runs lint and tests on Ubuntu and Windows with Python 3.12 and 3.14 on every push.

## Endpoints

| Method | Path | Description | Success |
|---|---|---|---|
| POST | `/addresses` | Create an address | 201 |
| GET | `/addresses?offset=&limit=` | List addresses in ID order | 200 |
| GET | `/addresses/{id}` | Get one address | 200 |
| PUT | `/addresses/{id}` | Update an address (replaces all fields) | 200 |
| DELETE | `/addresses/{id}` | Delete an address | 204 |
| GET | `/addresses/nearby?lat=&lon=&radius_km=&limit=` | Addresses within `radius_km` of a point, nearest first | 200 |

Errors: `404` for an unknown ID, `422` for invalid input (FastAPI's standard error body), `500` with `{"detail": "Internal server error"}` for unexpected failures.

The nearby search returns each match with its distance:

```json
[
  {
    "address": {"id": 2, "name": "BGC Office", "latitude": 14.5507, "longitude": 121.0494, "...": "..."},
    "distance_km": 2.727
  }
]
```

### Examples

bash:

```bash
curl -X POST http://127.0.0.1:8000/addresses \
  -H "Content-Type: application/json" \
  -d '{"name": "BGC Office", "street": "26th Street corner 5th Avenue", "city": "Taguig",
       "country": "Philippines", "latitude": 14.5507, "longitude": 121.0494}'

curl "http://127.0.0.1:8000/addresses/nearby?lat=14.5547&lon=121.0244&radius_km=5"
```

PowerShell:

```powershell
$body = @{ name = "BGC Office"; street = "26th Street corner 5th Avenue"; city = "Taguig"; country = "Philippines"; latitude = 14.5507; longitude = 121.0494 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/addresses -ContentType "application/json" -Body $body

Invoke-RestMethod "http://127.0.0.1:8000/addresses/nearby?lat=14.5547&lon=121.0244&radius_km=5"
```

## Validation

| Input | Rule |
|---|---|
| `name`, `city`, `country` | Required; 1–100 characters after trimming whitespace |
| `street` | Required; 1–200 characters after trimming |
| `state` | Optional; 1–100 characters |
| `postal_code` | Optional; 1–20 characters |
| All text fields | Any Unicode text except control characters (newline, tab, NUL…) |
| `latitude` | Required JSON number, -90 to 90 |
| `longitude` | Required JSON number, -180 to 180 |
| Unknown fields | Rejected (e.g. sending `id` or a misspelled field) |
| `id` (path) | 1 to 2⁶³−1 (SQLite's integer range) |
| `radius_km` | 0 to 20,015 km (half the Earth's circumference, which covers every point) |
| `limit` | 1 to 1000, default 100 |

Coordinates are strict: `true` or `"10.5"` are rejected rather than converted. NaN and infinity are rejected.

## Project structure

```
app/
  main.py            App factory, lifespan, request logging and error middleware
  config.py          Settings from environment variables
  logging_config.py  Log format with a per-request ID
  database.py        Engine, session factory, session dependency
  models.py          SQLAlchemy table definition
  schemas.py         Pydantic request/response models (all validation)
  crud.py            Database operations, including the nearby search
  geo.py             Haversine distance and bounding box
  routers/
    addresses.py     HTTP endpoints
tests/               pytest suite
.github/workflows/   CI
```

## Libraries

| Library | Why |
|---|---|
| FastAPI | Required by the assignment; request validation and Swagger docs out of the box |
| Pydantic v2 | Declarative input validation; FastAPI's native model layer |
| pydantic-settings | Typed configuration from environment variables |
| SQLAlchemy 2.x | Typed ORM models and parameterized queries; switching databases only changes the URL |
| Uvicorn | ASGI server for FastAPI |
| pytest, pytest-cov, httpx | Tests through FastAPI's `TestClient`, with coverage |
| Ruff | Linting and formatting |

The distance calculation uses only the standard library (`math`). `requirements.txt` and `requirements-dev.txt` pin every package, including indirect dependencies, so every install gets the same versions.

## Design decisions

- **Distance model.** The Earth is treated as a sphere with the IUGG mean radius (6371.0088 km) and distances use the haversine formula. Against the exact WGS84 ellipsoid the error is at most about 0.5%, which is fine for an address book and needs no extra dependency.
- **Nearby search in two steps.** SQL first narrows rows with a latitude/longitude bounding box on an indexed column pair; Python then computes the exact distance for those candidates only and keeps the nearest `limit` with a heap. The box handles circles that cross the 180th meridian or contain a pole. A test compares the results, including order, against a brute-force scan of all rows.
- **Radius is inclusive** and **equal distances are ordered by ID**, so results are deterministic.
- **Sync endpoints.** SQLAlchemy with SQLite is blocking, so the endpoints are plain `def`. FastAPI runs them in a threadpool, so they do not block the event loop.
- **SQLite in WAL mode.** Readers are not blocked while a write is in progress. SQLite still allows one writer at a time, so the app is meant to run as a single process; scaling out means moving to PostgreSQL (with PostGIS for the distance query), which only needs a new database URL and a spatial query.
- **Logging.** Every log line includes a request ID, returned in the `X-Request-ID` header. A client-supplied ID is reused only if it is 1–64 letters, digits or hyphens; otherwise a new one is generated, so clients cannot inject fake log lines. Each request is logged with method, path, status and duration. Creates, updates and deletes are logged at INFO; validation failures (field and error type only, never the submitted values, since addresses are personal data) and unknown IDs at WARNING; unexpected errors once at ERROR with a traceback.
- **PUT replaces the whole address.** Partial updates (PATCH) were left out to keep the API minimal.

## Non-goals

Left out on purpose to keep the scope to the assignment:

- Authentication, authorization and rate limiting
- Geocoding (turning street addresses into coordinates); clients send coordinates
- Database migrations (tables are created on startup; Alembic would be the next step)
- Concurrent-edit protection (ETag / `If-Match`); the last PUT wins
- Duplicate detection; two identical addresses can be stored

## Configuration

Optional environment variables:

| Variable | Default |
|---|---|
| `ADDRESS_BOOK_DATABASE_URL` | `sqlite:///./address_book.db` |
| `ADDRESS_BOOK_LOG_LEVEL` | `INFO` |

## Sample log

```
2026-11-25 16:14:35,807 INFO    [-] app.main: Database ready at sqlite:///./address_book.db
2026-11-25 16:14:36,852 INFO    [cd0d9965ecfe] app.crud: Created address id=1
2026-11-25 16:14:36,854 INFO    [cd0d9965ecfe] app.main: POST /addresses -> 201 (41.5 ms)
2026-11-25 16:14:37,196 INFO    [7fc3030c7bd8] app.crud: Updated address id=1
2026-11-25 16:14:37,197 INFO    [7fc3030c7bd8] app.main: PUT /addresses/1 -> 200 (10.2 ms)
2026-11-25 16:14:37,466 INFO    [231c1f4b99cc] app.main: GET /addresses/nearby -> 200 (4.0 ms)
2026-11-25 16:14:38,076 WARNING [acb6d7616597] app.main: Validation failed on POST /addresses: body.latitude: float_type
2026-11-25 16:14:38,076 INFO    [acb6d7616597] app.main: POST /addresses -> 422 (2.6 ms)
2026-11-25 16:14:38,694 INFO    [b47bf533a1ce] app.crud: Deleted address id=1
2026-11-25 16:14:38,694 INFO    [b47bf533a1ce] app.main: DELETE /addresses/1 -> 204 (27.0 ms)
2026-11-25 16:14:39,041 WARNING [306e35b9508f] app.routers.addresses: Address id=1 not found
2026-11-25 16:14:39,041 INFO    [306e35b9508f] app.main: GET /addresses/1 -> 404 (3.3 ms)
```
