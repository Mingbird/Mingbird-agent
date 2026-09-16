# API Requirements: SensorHub Ingestion API (wf08 fixture)

## Background
SensorHub collects readings from environmental sensors (see messy_sensor_data.csv
for the data shape). A v2 ingestion API is needed so field gateways can push
readings directly.

## Functional requirements
1. `POST /v2/readings` — accept a batch of up to 1000 readings; each reading:
   `{sensor_id, timestamp (ISO 8601), temperature_C, humidity_pct, pressure_hPa}`
2. Validation: reject (400) readings with non-numeric values, impossible
   values (temperature < -60C or > 80C), duplicate (sensor_id, timestamp) pairs
   within a batch; accept the valid subset of a batch and report rejected items
3. `GET /v2/readings?sensor_id=&from=&to=` — query with pagination (limit/offset)
4. `GET /v2/stats?sensor_id=&window=1h` — hourly aggregates (min/max/avg temp)

## Non-functional requirements
- JSON only; RFC 7807 problem+json error bodies
- Idempotent batch submission via client-supplied `X-Batch-Id` header
- Rate limit: 10 batches/min per gateway, header-based feedback (429 + Retry-After)

## Deliverables for this task
- OpenAPI 3.1 spec (openapi.yaml)
- A runnable mock implementation (any framework, in-memory store)
- An examples file with at least one request/response pair per endpoint
