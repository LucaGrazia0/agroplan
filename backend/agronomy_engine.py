
from datetime import date
from typing import Optional
import math

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from storage import connect
from auth import CurrentUser, require_parcel
from weather_history import daily_window
from agronomy_alerts import build_alerts

router = APIRouter(prefix="/agronomy", tags=["Agronomy"])


class AgronomyRequest(BaseModel):
    parcel_id: str = Field(min_length=1)
    latitude: float = Field(ge=35, le=48)
    longitude: float = Field(ge=6, le=19)
    season: Optional[str] = None
    history_days: int = Field(default=60, ge=30, le=180)
    include_satellite: bool = False


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def round_or_none(value, digits=1):
    return round(value, digits) if value is not None else None


def crop_context(parcel_id, season):
    with connect() as conn:
        if season:
            cycle = conn.execute(
                """
                SELECT * FROM agr_crop_cycles
                WHERE parcel_id=? AND season=?
                """,
                (parcel_id, season),
            ).fetchone()
        else:
            cycle = conn.execute(
                """
                SELECT * FROM agr_crop_cycles
                WHERE parcel_id=?
                ORDER BY season DESC
                LIMIT 1
                """,
                (parcel_id,),
            ).fetchone()

        if cycle is None:
            return None

        cycle = dict(cycle)

        observation = conn.execute(
            """
            SELECT * FROM agr_bbch_observations
            WHERE cycle_id=?
            ORDER BY observed_at DESC, id DESC
            LIMIT 1
            """,
            (cycle["id"],),
        ).fetchone()

        return {
            "cycle_id": cycle["id"],
            "season": cycle["season"],
            "crop": cycle["crop"],
            "variety": cycle["variety"],
            "sowing_date": cycle["sowing_date"],
            "latest_bbch": dict(observation) if observation else None,
        }


def calculate_window(history, days, end=None):
    rows = daily_window(history, days, end)

    keys = {
        "rain": "precipitation_sum",
        "et0": "et0_fao_evapotranspiration",
        "tmax": "temperature_2m_max",
        "tmin": "temperature_2m_min",
    }

    values = {
        name: [finite(row.get(key)) for row in rows]
        for name, key in keys.items()
    }

    complete = {
        name: len(rows) == days and all(v is not None for v in data)
        for name, data in values.items()
    }

    rain = sum(values["rain"]) if complete["rain"] else None
    et0 = sum(values["et0"]) if complete["et0"] else None

    temperatures_complete = complete["tmax"] and complete["tmin"]

    average_temperature = (
        sum(
            (maximum + minimum) / 2
            for maximum, minimum in zip(
                values["tmax"], values["tmin"]
            )
        ) / days
        if temperatures_complete
        else None
    )

    return {
        "period_days": days,
        "start_date": rows[0]["date"] if len(rows) == days else None,
        "end_date": rows[-1]["date"] if len(rows) == days else None,
        "available_days": len(rows),
        "rain_mm": round_or_none(rain),
        "et0_mm": round_or_none(et0),
        "climatic_balance_mm": (
            round_or_none(rain - et0)
            if rain is not None and et0 is not None
            else None
        ),
        "mean_temperature_c": round_or_none(average_temperature),
        "max_temperature_c": (
            round_or_none(max(values["tmax"]))
            if complete["tmax"] else None
        ),
        "min_temperature_c": (
            round_or_none(min(values["tmin"]))
            if complete["tmin"] else None
        ),
        "data_complete": all(complete.values()),
        "coverage": {
            name: {
                "valid_days": sum(v is not None for v in data),
                "expected_days": days,
            }
            for name, data in values.items()
        },
    }


def build_indicators(weather, crop):
    history = weather.get("history")

    if not isinstance(history, list):
        raise HTTPException(
            status_code=502,
            detail="Storico meteorologico non valido",
        )

    windows = {
        str(days): calculate_window(history, days, date.fromisoformat(weather["historical_end"]))
        for days in (7, 15, 30)
    }

    warnings = []

    if crop is None:
        warnings.append(
            "Nessun ciclo colturale registrato per la particella."
        )
    elif crop["latest_bbch"] is None:
        warnings.append(
            "Fase BBCH non registrata: valutazioni fenologiche non disponibili."
        )
    else:
        observation_date = date.fromisoformat(
            crop["latest_bbch"]["observed_at"]
        )
        end = date.fromisoformat(weather["historical_end"])

        if observation_date > end:
            warnings.append(
                "L'ultima osservazione BBCH è successiva alla fine "
                "dello storico meteorologico."
            )

    for days, result in windows.items():
        if not result["data_complete"]:
            warnings.append(
                f"Serie meteorologica incompleta per il periodo di {days} giorni."
            )

    return {
        "source": weather.get("source", "Sconosciuta"),
        "historical_end": weather.get("historical_end"),
        "crop_context": crop,
        "windows": windows,
        "monitoring_alerts": build_alerts(weather, crop),
        "warnings": warnings,
        "interpretation": {
            "climatic_balance": (
                "Precipitazioni meno evapotraspirazione di riferimento "
                "(P - ET0). Un valore negativo non dimostra da solo "
                "stress idrico della coltura."
            ),
            "disease_risk": (
                "Non calcolato: servono modelli specifici per patogeno "
                "e ulteriori dati meteorologici."
            ),
            "water_stress": (
                "Non calcolato: servono almeno coefficienti colturali, "
                "riserva idrica del suolo e informazioni sulle irrigazioni."
            ),
        },
    }


def register_agronomy_routes(app, weather_handler, weather_request_class, satellite_handler=None):
    @router.get('/overview')
    def overview(user: CurrentUser):
        from crop_analysis import farm_overview
        return farm_overview(user)

    @router.post("/analyze")
    async def analyze(req: AgronomyRequest, user: CurrentUser):
        parcel = require_parcel(req.parcel_id, user)
        crop = crop_context(req.parcel_id, req.season)
        import json
        payload = json.loads(parcel['payload']) if parcel['payload'] else {}
        points = payload.get('points', [])
        latitude = sum(p['lat'] for p in points)/len(points) if points else req.latitude
        longitude = sum(p['lng'] for p in points)/len(points) if points else req.longitude
        try:
            weather = await weather_handler(
                weather_request_class(latitude=latitude, longitude=longitude, history_days=req.history_days)
            )
            result = build_indicators(weather, crop)
        except HTTPException:
            result = {'crop_context': crop, 'windows': {}, 'monitoring_alerts': [],
                      'warnings': ['Meteo non disponibile: la sintesi usa solo i record salvati.'], 'source': 'Record aziendali'}
        from crop_analysis import saved_context, build_crop_review
        if req.include_satellite and satellite_handler and points:
            try:
                await satellite_handler(req.parcel_id, points)
            except HTTPException:
                result['warnings'].append('Aggiornamento satellitare non disponibile: mantengo le osservazioni salvate.')
        soil, satellite = saved_context(req.parcel_id)
        result['crop_review'] = build_crop_review(crop, soil, satellite, result['windows'], bool(points))
        return {
            "parcel_id": req.parcel_id,
            "latitude": latitude,
            "longitude": longitude,
            **result,
        }

    app.include_router(router)
