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


def _weather_rows(raw):
    keys = (
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "et0_fao_evapotranspiration",
    )
    dates = raw.get("time", [])
    return [
        {
            "date": day,
            **{
                key: (
                    raw[key][i]
                    if isinstance(raw.get(key), list)
                    and i < len(raw[key])
                    else None
                )
                for key in keys
            },
        }
        for i, day in enumerate(dates)
    ]


def _weather_result(req, end_date, history, source,
                    forecast=None, current=None, note=""):
    def rain_total(days):
        rows = history[-days:]
        values = [r.get("precipitation_sum") for r in rows]
        if len(rows) != days or any(
            not isinstance(v, (int, float)) or isinstance(v, bool)
            for v in values
        ):
            return None
        return round(sum(values), 1)

    return {
        "source": source,
        "latitude": req.latitude,
        "longitude": req.longitude,
        "historical_end": end_date.isoformat(),
        "history": history,
        "forecast": forecast if forecast is not None else [],
        "current": current if current is not None else {},
        "rain_7d_mm": rain_total(7),
        "rain_15d_mm": rain_total(15),
        "rain_30d_mm": rain_total(30),
        "note": note,
    }


async def _nasa_weather(req, today):
    # NASA POWER can publish daily values with a delay.
    # Keep a conservative end date; do not fabricate missing days.
    # Richiedi giorni recenti, poi individua l'ultima data completa.
    end_date = today - timedelta(days=1)
    start_date = end_date - timedelta(days=req.history_days + 14)

    params = {
        "parameters": "T2M_MAX,T2M_MIN,PRECTOTCORR",
        "community": "AG",
        "latitude": req.latitude,
        "longitude": req.longitude,
        "start": start_date.strftime("%Y%m%d"),
        "end": end_date.strftime("%Y%m%d"),
        "format": "JSON",
    }

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.get(
                "https://power.larc.nasa.gov/api/temporal/daily/point",
                params=params,
            )
            response.raise_for_status()
            payload = response.json()

        parameters = payload["properties"]["parameter"]

        def valid(value):
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and value > -900
            ):
                return value
            return None

        valid_dates = []
        for offset in range((end_date - start_date).days + 1):
            day = start_date + timedelta(days=offset)
            key = day.strftime("%Y%m%d")
            if all(
                valid(parameters.get(name, {}).get(key)) is not None
                for name in ("T2M_MAX", "T2M_MIN", "PRECTOTCORR")
            ):
                valid_dates.append(day)

        if not valid_dates:
            raise ValueError("Nessuna giornata NASA POWER completa")

        end_date = max(valid_dates)
        start_date = end_date - timedelta(days=req.history_days - 1)

        history = []
        for offset in range(req.history_days):
            day = start_date + timedelta(days=offset)
            key = day.strftime("%Y%m%d")
            history.append({
                "date": day.isoformat(),
                "temperature_2m_max": valid(
                    parameters.get("T2M_MAX", {}).get(key)
                ),
                "temperature_2m_min": valid(
                    parameters.get("T2M_MIN", {}).get(key)
                ),
                "precipitation_sum": valid(
                    parameters.get("PRECTOTCORR", {}).get(key)
                ),
                "et0_fao_evapotranspiration": None,
            })

        if not any(
            row["precipitation_sum"] is not None
            for row in history
        ):
            raise ValueError("NASA POWER non ha restituito precipitazioni valide")

        return _weather_result(
            req, end_date, history, "NASA POWER",
            note=(
                "Fallback NASA POWER: dati storici modellati su griglia. "
                "Previsioni e condizioni attuali non disponibili. "
                "ET0 non calcolata: il bilancio climatico P - ET0 "
                "non è disponibile. Lo storico termina alla data "
                "historical_end e può avere un ritardo di pubblicazione."
            ),
        )

    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Open-Meteo non disponibile e fallback NASA POWER non riuscito.",
        ) from exc





async def _met_norway_weather(req):
    """Meteo attuale e previsioni MET Norway per AgroPlan."""
    from datetime import datetime, timezone, timedelta, time as dt_time
    from zoneinfo import ZoneInfo

    headers = {
        "User-Agent": "AgroPlan/0.1 (agricultural weather application)"
    }
    params = {
        "lat": round(req.latitude, 5),
        "lon": round(req.longitude, 5),
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            "https://api.met.no/weatherapi/locationforecast/2.0/compact",
            params=params,
            headers=headers,
        )
        response.raise_for_status()

    entries = response.json()["properties"]["timeseries"]
    now = datetime.now(timezone.utc)
    tz = ZoneInfo("Europe/Rome")

    first_day = now.astimezone(tz).date()
    last_day = first_day + timedelta(days=6)

    current = {}
    temperatures = {}
    candidates = []

    for entry in entries:
        timestamp = datetime.fromisoformat(
            entry["time"].replace("Z", "+00:00")
        )
        if timestamp < now:
            continue

        details = entry["data"]["instant"]["details"]

        if not current:
            wind = details.get("wind_speed")
            current = {
                "time": entry["time"],
                "temperature_2m": details.get("air_temperature"),
                "relative_humidity_2m": details.get("relative_humidity"),
                "wind_speed_10m": (
                    round(wind * 3.6, 1) if wind is not None else None
                ),
                "precipitation": None,
            }

        day = timestamp.astimezone(tz).date()
        temperature = details.get("air_temperature")

        if first_day <= day <= last_day and temperature is not None:
            temperatures.setdefault(day, []).append(temperature)

        # Raccolta degli intervalli disponibili.
        for hours in (1, 6):
            period = entry["data"].get(f"next_{hours}_hours", {})
            rain = period.get("details", {}).get("precipitation_amount")

            if rain is not None:
                candidates.append((
                    timestamp,
                    timestamp + timedelta(hours=hours),
                    float(rain),
                    hours,
                ))

    # Preferisce intervalli brevi e non sovrapposti.
    selected = []
    for interval in sorted(candidates, key=lambda x: (x[3], x[0])):
        start, end, rain, hours = interval

        if any(
            start < other_end and end > other_start
            for other_start, other_end, _, _ in selected
        ):
            continue

        selected.append(interval)

    forecast = []

    for offset in range(7):
        day = first_day + timedelta(days=offset)

        day_start = datetime.combine(
            day, dt_time.min, tzinfo=tz
        ).astimezone(timezone.utc)

        day_end = datetime.combine(
            day + timedelta(days=1), dt_time.min, tzinfo=tz
        ).astimezone(timezone.utc)

        # Per oggi consideriamo soltanto il periodo futuro.
        period_start = max(day_start, now)

        rain_total = 0.0
        coverage = []

        for start, end, rain, hours in selected:
            overlap_start = max(start, period_start)
            overlap_end = min(end, day_end)

            if overlap_end <= overlap_start:
                continue

            overlap_seconds = (overlap_end - overlap_start).total_seconds()
            interval_seconds = (end - start).total_seconds()

            rain_total += rain * overlap_seconds / interval_seconds
            coverage.append((overlap_start, overlap_end))

        cursor = period_start
        for start, end in sorted(coverage):
            if start > cursor:
                break
            cursor = max(cursor, end)

        complete = cursor >= day_end
        temps = temperatures.get(day, [])

        forecast.append({
            "date": day.isoformat(),
            "temperature_2m_max": max(temps) if temps else None,
            "temperature_2m_min": min(temps) if temps else None,
            "precipitation_sum": (
                round(rain_total, 1) if complete else None
            ),
            "et0_fao_evapotranspiration": None,
        })

    return current, forecast

@app.post("/weather")
async def parcel_weather(req: WeatherRequest):
    today = DateType.today()
    key = (
        round(req.latitude, 5),
        round(req.longitude, 5),
        req.history_days,
        today.isoformat(),
    )

    cached = _weather_cache.get(key)
    if cached and time.monotonic() - cached["time"] < WEATHER_CACHE_SECONDS:
        return cached["data"]

    lock = _weather_locks.setdefault(key, asyncio.Lock())

    async with lock:
        cached = _weather_cache.get(key)
        if cached and time.monotonic() - cached["time"] < WEATHER_CACHE_SECONDS:
            return cached["data"]

        try:
            result = await _nasa_weather(req, today)
        except HTTPException:
            print('[METEO] NASA non disponibile; provo Open-Meteo', flush=True)
            result = None

        if result is None:
            end_date = today - timedelta(days=5)
            start_date = end_date - timedelta(days=req.history_days - 1)

            daily = (
                "temperature_2m_max,temperature_2m_min,"
                "precipitation_sum,et0_fao_evapotranspiration"
            )

            common = {
                "latitude": req.latitude,
                "longitude": req.longitude,
                "daily": daily,
                "timezone": "Europe/Rome",
            }

            try:
                async with httpx.AsyncClient(timeout=35) as client:
                    archive, future = await asyncio.gather(
                        client.get(
                            "https://archive-api.open-meteo.com/v1/archive",
                            params={
                                **common,
                                "start_date": start_date.isoformat(),
                                "end_date": end_date.isoformat(),
                            },
                        ),
                        client.get(
                            "https://api.open-meteo.com/v1/forecast",
                            params={
                                **common,
                                "forecast_days": 7,
                                "current": (
                                    "temperature_2m,relative_humidity_2m,"
                                    "precipitation,wind_speed_10m"
                                ),
                            },
                        ),
                    )

                archive.raise_for_status()
                future.raise_for_status()

                historic = archive.json().get("daily", {})
                forecast = future.json()

                if not historic.get("time"):
                    raise ValueError("Storico Open-Meteo vuoto")

                result = _weather_result(
                    req,
                    end_date,
                    _weather_rows(historic),
                    "Open-Meteo",
                    forecast=_weather_rows(
                        forecast.get("daily", {"time": []})
                    ),
                    current=forecast.get("current", {}),
                    note=(
                        "Dati meteorologici modellati su griglia. "
                        "Lo storico termina alla data historical_end; "
                        "gli ultimi giorni non sono inclusi."
                    ),
                )

            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                print(
                    f"[METEO] Open-Meteo non disponibile: "
                    f"{type(exc).__name__}; provo NASA POWER",
                    flush=True,
                )
                raise HTTPException(status_code=503, detail='Fonti meteo non disponibili')

        # MET Norway fornisce condizioni attuali e previsioni.
        # Lo storico rimane quello già recuperato.
        try:
            met_current, met_forecast = await _met_norway_weather(req)
            if met_forecast:
                result["current"] = met_current
                result["forecast"] = met_forecast
                result["forecast_source"] = "MET Norway"
                result["note"] += (
                    " Condizioni attuali e previsioni: MET Norway. "
                    "Le precipitazioni giornaliere possono essere "
                    "parziali quando mancano intervalli orari."
                )
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            print(
                f"[METEO] MET Norway non disponibile: {exc}",
                flush=True,
            )

        _weather_cache[key] = {
            "time": time.monotonic(),
            "data": result,
        }
        return result


from crop_api import register_crop_routes
register_crop_routes(app)

app.include_router(soil_router)

from agronomy_engine import register_agronomy_routes
register_agronomy_routes(app, parcel_weather, WeatherRequest)
