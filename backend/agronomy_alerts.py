"""Segnalazioni esplorative, NON diagnosi o modelli epidemiologici validati."""
import math
from datetime import date
from weather_history import daily_window


def _num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if math.isfinite(v) else None


def _alert(category, title, status, evidence, action, limitations):
    return {"category": category, "title": title, "status": status,
            "evidence": evidence, "recommended_check": action,
            "limitations": limitations}


def build_alerts(weather, crop):
    """Produce indizi di monitoraggio senza classificare rischio fitopatologico."""
    alerts = []
    history = weather.get('history')
    if not isinstance(history, list):
        return alerts
    try:
        end = date.fromisoformat(weather.get('historical_end', ''))
    except (ValueError, TypeError):
        end = None
    rows = daily_window(history, 7, end)
    if not crop:
        return [_alert('general', 'Coltura non registrata', 'dati_insufficienti', [],
                       'Registra la coltura e il ciclo colturale.',
                       'Nessuna valutazione specifica possibile.')]
    name = str(crop.get('crop') or '').strip().lower()
    bbch_record = crop.get('latest_bbch') or {}
    bbch = bbch_record.get('bbch')
    try:
        bbch = int(bbch) if bbch is not None else None
    except (ValueError, TypeError):
        bbch = None
    crop_family = ('cereale' if any(x in name for x in ('frumento','grano','wheat','orzo','barley','triticale'))
                   else 'mais' if any(x in name for x in ('mais','maize','corn')) else 'altra')
    if len(rows) == 7:
        rain = [_num(r.get('precipitation_sum')) for r in rows]
        tmax = [_num(r.get('temperature_2m_max')) for r in rows]
        tmin = [_num(r.get('temperature_2m_min')) for r in rows]
        if all(v is not None for v in rain+tmax+tmin):
            wet_days = sum(v >= 1 for v in rain)
            rain_total = round(sum(rain), 1)
            mean_t = round(sum((a+b)/2 for a,b in zip(tmax,tmin))/7, 1)
            if crop_family == 'cereale' and bbch is not None and 20 <= bbch <= 79:
                if wet_days >= 3 and 8 <= mean_t <= 25:
                    alerts.append(_alert('malattie', 'Controllo visivo delle malattie fogliari',
                        'attenzione', [f'{wet_days} giorni con almeno 1 mm di pioggia negli ultimi 7',
                                     f'Temperatura media indicativa {mean_t} °C', f'BBCH {bbch}'],
                        'Ispeziona foglie inferiori e superiori per eventuali sintomi; consulta i bollettini fitosanitari locali.',
                        'Indicatore esplorativo: pioggia e temperatura NON stimano probabilità di infezione; mancano bagnatura fogliare, inoculo e modelli validati.'))
            if crop_family in ('cereale','mais') and wet_days >= 3:
                alerts.append(_alert('infestanti', 'Verifica emergenza infestanti', 'monitoraggio',
                    [f'{rain_total} mm di pioggia negli ultimi 7 giorni', f'{wet_days} giorni piovosi'],
                    'Effettua un sopralluogo per identificare specie e stadio delle infestanti.',
                    'La pioggia non dimostra presenza di infestanti; mancano rilievi di campo e temperatura del suolo.'))
        else:
            alerts.append(_alert('meteo', 'Serie giornaliera incompleta', 'dati_insufficienti', [],
                'Verifica la disponibilità di precipitazioni e temperature giornaliere.',
                'Nessun indicatore meteorologico derivato calcolato.'))
    else:
        alerts.append(_alert('meteo', 'Storico recente insufficiente', 'dati_insufficienti',
            [f'{len(rows)} giorni disponibili su 7'], 'Riprova quando sono disponibili 7 giorni.',
            'Nessun indicatore meteorologico derivato calcolato.'))
    alerts.append(_alert('nutrizione', 'Verifica stato nutrizionale', 'da_verificare',
        ([f'Coltura: {crop.get("crop")}', f'BBCH: {bbch}'] if bbch is not None else [f'Coltura: {crop.get("crop")}']),
        'Confronta analisi di laboratorio, sintomi osservati e andamento della vegetazione.',
        'Nessuna carenza diagnosticata: dati pedologici cartografici e meteo non sostituiscono analisi fogliari o del terreno.'))
    return alerts
