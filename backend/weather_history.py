"""Calendar-aware windows. Missing and duplicate dates are never fabricated."""
from datetime import date, timedelta


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
