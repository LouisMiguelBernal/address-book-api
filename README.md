# Address Book API

A minimal FastAPI application for creating, updating and deleting addresses, and for finding addresses within a given distance of a location. Each address stores its coordinates, is validated on input, and is saved to SQLite.

There is no GUI. Use the built-in Swagger UI at `/docs`.

## Requirements

- Python 3.12 or newer
- Git

## Run the app

### Windows (PowerShell)

```powershell
git clone https://github.com/<your-github-username>/address-book-api.git
cd address-book-api
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

If PowerShell blocks `Activate.ps1`, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first.

### macOS / Linux (bash)

```bash
git clone https://github.com/<your-github-username>/address-book-api.git
cd address-book-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open **http://127.0.0.1:8000/docs**.

The database file `address_book.db` is created in the project folder on first start. Data is kept between restarts.

## Run the tests

With the virtual environment active:

```bash
pip install -r requirements-dev.txt
pytest
ruff check .
```

## Endpoints

| Method | Path | Description | Success |
|---|---|---|---|
| POST | `/addresses` | Create an address | 201 |
| GET | `/addresses` | List addresses (`offset`, `limit`) | 200 |
| GET | `/addresses/{id}` | Get one address | 200 |
| PUT | `/addresses/{id}` | Update an address (replaces all fields) | 200 |
| DELETE | `/addresses/{id}` | Delete an address | 204 |
| GET | `/addresses/nearby?lat=&lon=&radius_km=` | Addresses within `radius_km` of a point, nearest first, with `distance_km` | 200 |

Errors: `404` for an unknown ID, `422` for invalid input.

### Example

```bash
curl -X POST http://127.0.0.1:8000/addresses \
  -H "Content-Type: application/json" \
  -d '{"name": "BGC Office", "street": "26th Street corner 5th Avenue", "city": "Taguig",
       "country": "Philippines", "latitude": 14.5507, "longitude": 121.0494}'

curl "http://127.0.0.1:8000/addresses/nearby?lat=14.5547&lon=121.0244&radius_km=5"
```

## Validation

| Field | Rule |
|---|---|
| `name`, `city`, `country` | Required, 1–100 characters after trimming whitespace |
| `street` | Required, 1–200 characters after trimming |
| `state` | Optional, 1–100 characters |
| `postal_code` | Optional, 1–20 characters |
| `latitude` | Required, -90 to 90 |
| `longitude` | Required, -180 to 180 |
| `radius_km` (search) | 0 to 20,015 km (half the Earth's circumference, which covers every point) |

## Project structure

```
app/
  main.py            App factory, lifespan, request logging middleware
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
```

## Libraries

| Library | Why |
|---|---|
| FastAPI | Required by the assignment; request validation and Swagger docs out of the box |
| Pydantic v2 | Declarative input validation; FastAPI's native model layer |
| pydantic-settings | Typed configuration from environment variables |
| SQLAlchemy 2.0 | Typed ORM models and parameterized queries; switching to another database only changes the URL |
| Uvicorn | ASGI server for FastAPI |
| pytest, httpx | Tests through FastAPI's `TestClient` |
| Ruff | Linting and formatting |

The distance calculation uses only the standard library (`math`).

## Design decisions

- **Distance model.** The Earth is treated as a sphere with the IUGG mean radius (6371.0088 km) and distances use the haversine formula. Against the exact WGS84 ellipsoid the error is at most about 0.5%, which is fine for an address book and needs no extra dependency.
- **Nearby search in two steps.** SQL first narrows rows with a latitude/longitude bounding box on an indexed column pair; Python then computes the exact distance for those candidates only. The box handles circles that cross the 180th meridian or contain a pole. A test compares the results against a brute-force scan of all rows.
- **Radius is inclusive.** An address exactly `radius_km` away is returned.
- **Sync endpoints.** SQLAlchemy with SQLite is blocking, so the endpoints are plain `def`. FastAPI runs them in a threadpool, so they do not block the event loop.
- **SQLite in WAL mode.** Readers are not blocked while a write is in progress. SQLite still allows one writer at a time, so the app is meant to run as a single process.
- **Logging.** Every log line includes a request ID (returned in the `X-Request-ID` response header). Each request is logged with method, path, status and duration. Creates, updates and deletes are logged at INFO; validation failures and unknown IDs at WARNING.

## Configuration

Optional environment variables:

| Variable | Default |
|---|---|
| `ADDRESS_BOOK_DATABASE_URL` | `sqlite:///./address_book.db` |
| `ADDRESS_BOOK_LOG_LEVEL` | `INFO` |

## Sample log

```
2026-11-25 15:16:03,207 INFO    [-] app.main: Database ready at sqlite:///./address_book.db
2026-11-25 15:16:05,021 INFO    [ba02bebb46a0] app.crud: Created address id=1
2026-11-25 15:16:05,026 INFO    [ba02bebb46a0] app.main: POST /addresses -> 201 (53.7 ms)
2026-11-25 15:16:05,908 INFO    [bcb044da32c8] app.main: GET /addresses/nearby -> 200 (6.6 ms)
2026-11-25 15:16:06,335 WARNING [ec5e71f6fdb4] app.main: Validation failed on POST /addresses: [{'type': 'less_than_equal', 'loc': ('body', 'latitude'), 'msg': 'Input should be less than or equal to 90', 'input': 95, 'ctx': {'le': 90.0}}]
2026-11-25 15:16:06,340 INFO    [ec5e71f6fdb4] app.main: POST /addresses -> 422 (3.6 ms)
2026-11-25 15:16:07,207 WARNING [48fbe522c542] app.routers.addresses: Address id=1 not found
2026-11-25 15:16:07,207 INFO    [48fbe522c542] app.main: GET /addresses/1 -> 404 (3.9 ms)
```
