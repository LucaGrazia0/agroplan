"""AgroPlan Sentinel-2 API. OAuth secrets remain on the server."""
from __future__ import annotations
from soil_api import router as soil_router

import asyncio
from io import BytesIO
import os
import time
from datetime import date as DateType, timedelta
from typing import Literal

import httpx
from PIL import Image, ImageChops, ImageDraw
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator, model_validator

load_dotenv()
TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
SH_BASE = "https://sh.dataspace.copernicus.eu/api/v1"

app = FastAPI(title="AgroPlan Sentinel-2 Backend", version="1.0.0")
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8080,http://localhost:8090,http://127.0.0.1:8090,http://localhost:8091,http://127.0.0.1:8091,http://localhost:5173").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["*"])

_token: str | None = None
_token_expiry = 0.0
_token_lock = asyncio.Lock()


class GeometryRequest(BaseModel):
    # GeoJSON geometry, coordinates [longitude, latitude] in EPSG:4326
    geometry: dict
    date: DateType | None = None
    max_cloud_coverage: float = Field(default=30, ge=0, le=100)

    @field_validator("geometry")
    @classmethod
    def check_geometry(cls, value: dict) -> dict:
        if value.get("type") not in ("Polygon", "MultiPolygon"):
            raise ValueError("geometry must be GeoJSON Polygon or MultiPolygon")
        coords = value.get("coordinates")
        if not isinstance(coords, list) or not coords:
            raise ValueError("geometry.coordinates is missing")
        # Guard against pathological geometries and unexpected coordinate formats.
        def walk(node, depth=0):
            if depth > 6:
                raise ValueError("Invalid geometry nesting")
            if isinstance(node, list) and len(node) == 2 and all(isinstance(v, (float, int)) and not isinstance(v, bool) for v in node):
                lon, lat = node
                if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                    raise ValueError("Coordinates must be WGS84 longitude, latitude")
                return 1
            if not isinstance(node, list):
                raise ValueError("Invalid GeoJSON coordinates")
            return sum(walk(x, depth + 1) for x in node)
        count = walk(coords)
        if count < 4 or count > 3000:
            raise ValueError("Polygon must have 4 to 3000 coordinate pairs")
        return value


class OverlayRequest(GeometryRequest):
    index: Literal["ndvi", "dvi"] = "ndvi"
    width: int = Field(default=512, ge=64, le=1500)
    height: int = Field(default=512, ge=64, le=1500)


class ScenesRequest(GeometryRequest):
    start_date: DateType = Field(default_factory=lambda: DateType.today() - timedelta(days=45))
    end_date: DateType = Field(default_factory=DateType.today)
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def dates_in_order(self):
        if self.start_date > self.end_date:
            raise ValueError("start_date must be before end_date")
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("Limit search window to 366 days")
        return self


def bbox_from_geometry(geometry: dict) -> list[float]:
    points = []
    def collect(v):
        if isinstance(v, list) and len(v) == 2 and all(isinstance(z, (int, float)) for z in v):
            points.append(v)
        elif isinstance(v, list):
            for item in v:
                collect(item)
    collect(geometry["coordinates"])
    if not points:
        raise HTTPException(422, "No valid coordinates")
    return [min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)]


async def get_token() -> str:
    global _token, _token_expiry
    if _token and time.monotonic() < _token_expiry:
        return _token
    async with _token_lock:
        if _token and time.monotonic() < _token_expiry:
            return _token
        client_id = os.getenv("COPERNICUS_CLIENT_ID")
        client_secret = os.getenv("COPERNICUS_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise HTTPException(503, "Copernicus credentials missing: configure backend/.env")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(TOKEN_URL, data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret})
                r.raise_for_status()
                payload = r.json()
                _token = payload["access_token"]
                _token_expiry = time.monotonic() + max(10, int(payload.get("expires_in", 300)) - 60)
                return _token
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise HTTPException(502, f"OAuth authentication failed: {type(e).__name__}") from e


async def sentinel_post(path: str, payload: dict, accept: str = "application/json") -> httpx.Response:
    token = await get_token()
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(f"{SH_BASE}{path}", json=payload, headers={"Authorization": f"Bearer {token}", "Accept": accept})
        if r.status_code >= 400:
            if path == "/statistics":
                print(
                    f"[SENTINEL STATISTICS HTTP {r.status_code}] "
                    f"{r.text[:3000]}",
                    flush=True
                )
            # Do not return secrets or upstream response body (could contain sensitive details).
            raise HTTPException(
                status_code=502,
                detail=f"Sentinel Hub returned HTTP {r.status_code}; check backend logs for details"
            )
        return r
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Sentinel Hub request failed: {type(e).__name__}") from e


def evalscript(index: str, stats: bool = False) -> str:
    formula = "(sample.B08 - sample.B04) / (sample.B08 + sample.B04)" if index == "ndvi" else "sample.B08 - sample.B04"
    # Cloud/shadow/snow mask: SCL 3,8,9,10,11; invalid or no-data 0,1; water 6 retained.
    prelude = f'''//VERSION=3
function setup() {{ return {{ input: [{{ bands: ["B04", "B08", "SCL", "dataMask"], units: ["REFLECTANCE", "REFLECTANCE", "DN", "DN"] }}], output: {{ bands: {2 if stats else 4}, sampleType: "FLOAT32" }} }}; }}
function evaluatePixel(sample) {{
  let valid = sample.dataMask === 1 && ![0,1,3,8,9,10,11].includes(sample.SCL) && (sample.B08 + sample.B04) > 0;
  let value = valid ? {formula} : 0;
'''
    if stats:
        return prelude + '  return [value, valid ? 1 : 0];\n}'
    # Image values need UINT8; use separate setup, transparent outside valid pixels.
    prelude = prelude.replace('bands: 4, sampleType: "FLOAT32"', 'bands: 4, sampleType: "AUTO"')
    if index == "ndvi":
        ramp = '''  let t = Math.max(0, Math.min(1, (value + 0.2) / 1.1));
  let rgb = t < 0.45 ? [0.65 + t*0.6, 0.32 + t*0.9, 0.10] : [0.95 - (t-0.45)*1.5, 0.72 - (t-0.45)*0.1, 0.12 + (t-0.45)*0.2];'''
    else:
        ramp = '''  let t = Math.max(0, Math.min(1, (value + 0.1) / 0.7));
  let rgb = t < 0.45 ? [0.65 + t*0.6, 0.32 + t*0.9, 0.10] : [0.95 - (t-0.45)*1.5, 0.72 - (t-0.45)*0.1, 0.12 + (t-0.45)*0.2];'''
    return prelude + ramp + '\n  return [rgb[0], rgb[1], rgb[2], valid ? 1 : 0];\n}'


def data_filter(day: DateType, max_cloud: float) -> dict:
    return {"timeRange": {"from": f"{day.isoformat()}T00:00:00Z", "to": f"{day.isoformat()}T23:59:59Z"}, "maxCloudCoverage": max_cloud}


@app.get("/health")
async def health():
    return {"status": "ok", "credentials_configured": bool(os.getenv("COPERNICUS_CLIENT_ID") and os.getenv("COPERNICUS_CLIENT_SECRET"))}


@app.get("/auth/check")
async def auth_check():
    await get_token()
    return {"authenticated": True}


@app.post("/scenes")
async def scenes(req: ScenesRequest):
    body = {"collections": ["sentinel-2-l2a"], "datetime": f"{req.start_date.isoformat()}T00:00:00Z/{req.end_date.isoformat()}T23:59:59Z", "intersects": req.geometry, "limit": req.limit}
    r = await sentinel_post("/catalog/1.0.0/search", body, "application/geo+json")
    features = r.json().get("features", [])
    return {"scenes": [{"id": f.get("id"), "datetime": f.get("properties", {}).get("datetime"), "cloud_cover": f.get("properties", {}).get("eo:cloud_cover")} for f in features], "note": "Cloud cover is scene-wide, not parcel-specific. Choose a scene date and check masking."}


def mask_overlay_to_geometry(png: bytes, geometry: dict, bbox: list[float]) -> bytes:
    """Mask an RGBA Sentinel Hub PNG to a GeoJSON Polygon/MultiPolygon in CRS84."""
    with Image.open(BytesIO(png)) as source:
        rgba = source.convert("RGBA")
    width, height = rgba.size
    west, south, east, north = bbox
    if east <= west or north <= south:
        raise HTTPException(422, "Invalid parcel bounds")

    def pixels(ring):
        return [((float(lon) - west) * width / (east - west),
                 (north - float(lat)) * height / (north - south)) for lon, lat in ring]

    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    polygons = ([geometry["coordinates"]] if geometry["type"] == "Polygon"
                else geometry["coordinates"])
    for polygon in polygons:
        if not polygon:
            continue
        # Separate polygon masks ensure holes do not erase other polygons.
        polygon_mask = Image.new("L", (width, height), 0)
        polygon_draw = ImageDraw.Draw(polygon_mask)
        polygon_draw.polygon(pixels(polygon[0]), fill=255)
        for hole in polygon[1:]:
            polygon_draw.polygon(pixels(hole), fill=0)
        mask = ImageChops.lighter(mask, polygon_mask)

    # Preserve Sentinel Hub's alpha (cloud and nodata transparency).
    rgba.putalpha(ImageChops.multiply(rgba.getchannel("A"), mask))
    out = BytesIO()
    rgba.save(out, format="PNG")
    return out.getvalue()


@app.post("/overlay")
async def overlay(req: OverlayRequest):
    day = req.date or DateType.today() - timedelta(days=7)
    bbox = bbox_from_geometry(req.geometry)
    body = {"input": {"bounds": {"bbox": bbox, "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"}}, "data": [{"type": "sentinel-2-l2a", "dataFilter": data_filter(day, req.max_cloud_coverage)}]}, "output": {"width": req.width, "height": req.height, "responses": [{"identifier": "default", "format": {"type": "image/png"}}]}, "evalscript": evalscript(req.index)}
    r = await sentinel_post("/process", body, "image/png")
    return Response(content=mask_overlay_to_geometry(r.content, req.geometry, bbox), media_type="image/png", headers={"Cache-Control": "private, max-age=600", "X-BBox": ",".join(map(str, bbox))})


@app.post("/statistics")
async def statistics(req: GeometryRequest):
    day = req.date or DateType.today() - timedelta(days=7)
    bbox = bbox_from_geometry(req.geometry)
    results = {}
    for index in ("ndvi", "dvi"):
        # A numeric output band and a separate validity mask are provided by evalscript.
        # The statistical API uses output.dataMask to exclude invalid pixels.
        script = evalscript(index, stats=True).replace('output: { bands: 2, sampleType: "FLOAT32" }', 'output: [{ id: "index", bands: 1, sampleType: "FLOAT32" }, { id: "dataMask", bands: 1 }]')
        script = script.replace('return [value, valid ? 1 : 0];', 'return { index: [value], dataMask: [valid ? 1 : 0] };')
        body = {"input": {"bounds": {"geometry": req.geometry, "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"}}, "data": [{"type": "sentinel-2-l2a", "dataFilter": data_filter(day, req.max_cloud_coverage)}]}, "aggregation": {"timeRange": data_filter(day, req.max_cloud_coverage)["timeRange"], "aggregationInterval": {"of": "P1D"}, "evalscript": script, "resx": 10, "resy": 10}, "calculations": {"index": {"statistics": {"default": {"percentiles": {"k": [25, 50, 75]}}}}}}
        r = await sentinel_post("/statistics", body)
        data = r.json().get("data", [])
        outputs = [x.get("outputs", {}).get("index", {}).get("bands", {}).get("B0", {}).get("stats", {}) for x in data]
        results[index] = {"mean": outputs[0].get("mean") if outputs else None, "stDev": outputs[0].get("stDev") if outputs else None, "sampleCount": outputs[0].get("sampleCount") if outputs else None}
    return {"date": day.isoformat(), "bbox": bbox, "indices": results, "note": "Null values mean no valid observations. Statistics use 10 m pixels and exclude cloudy/shadow/snow pixels."}



# Satellite statistics are computed by Sentinel Hub on the actual GeoJSON polygon.
# The cloud mask uses the same Sentinel-2 SCL exclusions as the map overlay.
class ParcelTimeSeriesRequest(GeometryRequest):
    dates: list[DateType] = Field(min_length=1, max_length=30)
    index: Literal["ndvi", "dvi"] = "ndvi"


def parcel_stats_evalscript(index: str) -> str:
    formula = "(sample.B08 - sample.B04) / (sample.B08 + sample.B04)" if index == "ndvi" else "sample.B08 - sample.B04"
    return f"""//VERSION=3
function setup() {{
  return {{
    input: [{{ bands: ["B04", "B08", "SCL", "dataMask"], units: ["REFLECTANCE", "REFLECTANCE", "DN", "DN"] }}],
    output: [
      {{ id: "index", bands: 1, sampleType: "FLOAT32" }},
      {{ id: "dataMask", bands: 1, sampleType: "UINT8" }}
    ]
  }};
}}
function evaluatePixel(sample) {{
  let valid = sample.dataMask === 1 && ![0,1,3,8,9,10,11].includes(sample.SCL) && (sample.B08 + sample.B04) > 0;
  let value = valid ? {formula} : 0;
  return {{ index: [value], dataMask: [valid ? 1 : 0] }};
}}"""


async def parcel_stats_for_date(req: ParcelTimeSeriesRequest, day: DateType) -> dict:
    next_day = day + timedelta(days=1)
    time_range = {"from": f"{day.isoformat()}T00:00:00Z", "to": f"{next_day.isoformat()}T00:00:00Z"}
    body = {
        "input": {
            "bounds": {"geometry": req.geometry, "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"}},
            "data": [{"type": "sentinel-2-l2a", "dataFilter": {"timeRange": time_range, "maxCloudCoverage": req.max_cloud_coverage}}],
        },
        "aggregation": {
            "timeRange": time_range,
            "aggregationInterval": {"of": "P1D"},
            "evalscript": parcel_stats_evalscript(req.index),
            "resx": 0.00013, "resy": 0.00009,
        },
        "calculations": {"index": {"statistics": {"default": {"percentiles": {"k": [25, 50, 75]}}}}},
    }
    result = await sentinel_post("/statistics", body)
    return parse_statistical_response(result.json(), day)


def parse_statistical_response(payload: dict, day: DateType) -> dict:
    """Distinguish missing acquisitions, masked pixels and malformed API replies."""
    entries = payload.get("data")
    if not isinstance(entries, list):
        raise HTTPException(502, "Risposta statistica Sentinel priva del campo data")
    empty = {"date": day.isoformat(), "mean": None, "min": None, "max": None,
             "valid_percent": None, "sample_count": None, "valid_count": None}
    if not entries:
        return {**empty, "status": "no_acquisition"}

    for entry in entries:
        stats = (entry.get("outputs") or {}).get("index", {}).get("bands", {}).get("B0", {}).get("stats")
        if not isinstance(stats, dict):
            continue
        count, nodata = stats.get("sampleCount"), stats.get("noDataCount")
        valid_count = (count - nodata if isinstance(count, (int, float)) and
                       isinstance(nodata, (int, float)) else None)
        if valid_count is not None:
            valid_count = max(0, valid_count)
        valid_percent = (100 * valid_count / count if valid_count is not None and count else None)
        mean = stats.get("mean")
        if isinstance(mean, (int, float)) and (valid_count is None or valid_count > 0):
            return {"date": day.isoformat(), "mean": mean, "min": stats.get("min"),
                    "max": stats.get("max"), "valid_percent": valid_percent,
                    "sample_count": count, "valid_count": valid_count, "status": "ok"}
        if isinstance(count, (int, float)) and valid_count == 0:
            return {**empty, "sample_count": count, "valid_count": 0,
                    "valid_percent": 0.0 if count else None, "status": "no_valid_pixels"}
    raise HTTPException(502, "Formato statistiche Sentinel inatteso: controllare outputs.index.bands.B0.stats")


@app.post("/parcel-timeseries")
async def parcel_timeseries(req: ParcelTimeSeriesRequest):
    unique_days = sorted(set(req.dates))
    # Sequential calls deliberately limit instantaneous Copernicus quota consumption.
    observations = []
    for day in unique_days:
        try:
            observations.append(await parcel_stats_for_date(req, day))
            print(f"[NDVI] {day.isoformat()} -> {observations[-1]}", flush=True)
        except HTTPException as e:
            print(f"[NDVI ERRORE] {day.isoformat()} -> {e.detail}", flush=True)
            # Do not silently fabricate observations. A failed date is explicit.
            observations.append({"date": day.isoformat(), "mean": None, "min": None,
                                 "max": None, "valid_percent": None, "status": "error", "error": e.detail})
    return {"index": req.index, "observations": observations,
            "note": "Statistics request 10m sampling and the polygon geometry. Scene-wide cloud cover differs from valid pixel coverage."}


# AgroPlan weather: Open-Meteo archive + forecast, no client-side API keys.
class WeatherRequest(BaseModel):
    latitude: float = Field(ge=35, le=48)
    longitude: float = Field(ge=6, le=19)
    history_days: int = Field(default=60, ge=7, le=180)

_weather_cache = {}
_weather_locks = {}
WEATHER_CACHE_SECONDS = 3600

@app.post("/weather")
async def parcel_weather(req: WeatherRequest):
    today = DateType.today()
    key = (round(req.latitude, 5), round(req.longitude, 5),
           req.history_days, today.isoformat())

    now = time.monotonic()
    cached = _weather_cache.get(key)
    if cached and now - cached["time"] < WEATHER_CACHE_SECONDS:
        return cached["data"]

    lock = _weather_locks.setdefault(key, asyncio.Lock())

    async with lock:
        now = time.monotonic()
        cached = _weather_cache.get(key)
        if cached and now - cached["time"] < WEATHER_CACHE_SECONDS:
            return cached["data"]

        archive_end = today - timedelta(days=5)
        archive_start = archive_end - timedelta(days=req.history_days - 1)
        daily = "temperature_2m_max,temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration"
        common = {
            "latitude": req.latitude,
            "longitude": req.longitude,
            "daily": daily,
            "timezone": "Europe/Rome",
        }

        try:
            async with httpx.AsyncClient(timeout=35) as client:
                a, f = await asyncio.gather(
                    client.get(
                        "https://archive-api.open-meteo.com/v1/archive",
                        params={
                            **common,
                            "start_date": archive_start.isoformat(),
                            "end_date": archive_end.isoformat(),
                        },
                    ),
                    client.get(
                        "https://api.open-meteo.com/v1/forecast",
                        params={
                            **common,
                            "forecast_days": 7,
                            "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
                        },
                    ),
                )

            if a.status_code == 429 or f.status_code == 429:
                raise HTTPException(
                    status_code=503,
                    detail="Servizio meteorologico temporaneamente limitato. Riprova più tardi.",
                )

            a.raise_for_status()
            f.raise_for_status()

            historic = a.json().get("daily", {})
            future = f.json()

            if not historic.get("time"):
                raise HTTPException(
                    status_code=502,
                    detail="Storico meteo non disponibile",
                )

            def rows(raw):
                keys = [
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_sum",
                    "et0_fao_evapotranspiration",
                ]
                return [
                    {
                        "date": d,
                        **{
                            k: (raw.get(k) or [None] * len(raw["time"]))[i]
                            for k in keys
                        },
                    }
                    for i, d in enumerate(raw["time"])
                ]

            history = rows(historic)

            def rain_total(days):
                vals = [r["precipitation_sum"] for r in history[-days:]]
                return (
                    round(sum(x for x in vals if isinstance(x, (int, float))), 1)
                    if all(isinstance(x, (int, float)) for x in vals)
                    else None
                )

            result = {
                "source": "Open-Meteo",
                "latitude": req.latitude,
                "longitude": req.longitude,
                "historical_end": archive_end.isoformat(),
                "history": history,
                "forecast": rows(future.get("daily", {"time": []})),
                "current": future.get("current", {}),
                "rain_7d_mm": rain_total(7),
                "rain_15d_mm": rain_total(15),
                "rain_30d_mm": rain_total(30),
                "note": (
                    "Dati meteorologici modellati su griglia, non misurazioni in campo. "
                    "Le piogge cumulate terminano alla data historical_end; "
                    "gli ultimi giorni non sono inclusi."
                ),
            }

            _weather_cache[key] = {
                "time": time.monotonic(),
                "data": result,
            }

            return result

        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail="Servizio meteorologico momentaneamente non disponibile.",
            ) from exc

from crop_api import register_crop_routes
register_crop_routes(app)

app.include_router(soil_router)

from agronomy_engine import register_agronomy_routes
register_agronomy_routes(app, parcel_weather, WeatherRequest)
