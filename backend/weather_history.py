"""Calendar-aware windows. Missing and duplicate dates are never fabricated."""
from datetime import date, timedelta
import math


def daily_window(history, days, end=None):
    by_date = {}
    duplicates = set()
    for row in history:
        if not isinstance(row, dict):
            continue
        try:
            day = date.fromisoformat(row.get('date', ''))
        except (ValueError, TypeError):
            continue
        if day in by_date:
            duplicates.add(day)
        by_date[day] = row
    if not by_date:
        return []
    end = end or max(by_date)
    first = end - timedelta(days=days - 1)
    # Duplicate dates are ambiguous even when they happen to have equal values.
    return [by_date[day] for day in sorted(by_date)
            if first <= day <= end and day not in duplicates]


def observation_context(history, observed):
    """The 14 calendar days BEFORE the visit; partial sums stay partial.

    Window length is an application choice, not a diagnostic threshold.
    Forecasts and the visit day are deliberately excluded. Conflicting daily
    records are excluded by daily_window, never resolved by choosing a value.
    """
    end = observed - timedelta(days=1)
    start = observed - timedelta(days=14)
    expected = [(start + timedelta(days=i)).isoformat() for i in range(14)]
    keys = {'rain': 'precipitation_sum', 'et0': 'et0_fao_evapotranspiration',
            'tmax': 'temperature_2m_max', 'tmin': 'temperature_2m_min'}
    series = {key: {} for key in keys}
    for row in daily_window(history, 14, end):
        for key, field in keys.items():
            value = row.get(field)
            if (isinstance(value, (int, float)) and not isinstance(value, bool)
                    and math.isfinite(value) and (key not in {'rain', 'et0'} or value >= 0)):
                series[key][row['date']] = value
    available = sorted(set().union(*(set(values) for values in series.values())))
    paired = sorted(set(series['rain']) & set(series['et0']))
    paired_rain = sum(series['rain'][d] for d in paired) if paired else None
    paired_et0 = sum(series['et0'][d] for d in paired) if paired else None
    coverage = {key: {'valid_days': len(values), 'missing_dates': [d for d in expected if d not in values]}
                for key, values in series.items()}
    missing = [d for d in expected if d not in available]
    last = available[-1] if available else None
    return {
        'observation_date': observed.isoformat(), 'start_date': start.isoformat(), 'end_date': end.isoformat(),
        'expected_days': 14, 'available_days': len(available), 'available_dates': available,
        'available_start': available[0] if available else None, 'available_through': last,
        'missing_dates': missing, 'trailing_missing_dates': [d for d in missing if last and d > last],
        'internal_missing_dates': [d for d in missing if last and d <= last],
        'coverage': coverage, 'data_complete': all(v['valid_days'] == 14 for v in coverage.values()),
        'rain_mm': round(sum(series['rain'].values()), 2) if series['rain'] else None,
        'et0_mm': round(sum(series['et0'].values()), 2) if series['et0'] else None,
        'paired_days': len(paired), 'paired_dates': paired,
        'paired_rain_mm': round(paired_rain, 2) if paired else None,
        'paired_et0_mm': round(paired_et0, 2) if paired else None,
        'climatic_balance_mm': round(paired_rain - paired_et0, 2) if paired else None,
        'max_temperature_c': max(series['tmax'].values()) if series['tmax'] else None,
        'min_temperature_c': min(series['tmin'].values()) if series['tmin'] else None,
    }


def context_description(context):
    c = context
    text = (f"Rilievo del {c['observation_date']}; contesto dei 14 giorni precedenti, "
            f"dal {c['start_date']} al {c['end_date']}. "
            f"Giorni con dati: {c['available_days']}/14; meteo disponibile fino al {c['available_through'] or 'nessun giorno nel periodo'}. ")
    if c['missing_dates']:
        text += 'Giorni senza dati: ' + ', '.join(c['missing_dates']) + '. '
    if c['trailing_missing_dates']:
        text += 'Lo storico non include ancora gli ultimi giorni: il ritardo non richiede di cambiare la data del rilievo. '
    if c['paired_days']:
        text += (f"P − ET₀ sui soli {c['paired_days']} giorni con entrambe le misure: "
                 f"{c['climatic_balance_mm']:g} mm (P {c['paired_rain_mm']:g}, ET₀ {c['paired_et0_mm']:g} mm). ")
    else:
        text += 'P − ET₀ non calcolabile: mancano giorni con entrambe le misure. '
    return text.strip()
