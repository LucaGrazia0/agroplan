"""Local offline smoke tests (no credentials or network needed)."""
from datetime import date
from main import app, bbox_from_geometry, evalscript, OverlayRequest

polygon = {"type": "Polygon", "coordinates": [[[10.0, 45.0], [10.01, 45.0], [10.01, 45.01], [10.0, 45.01], [10.0, 45.0]]]}
assert bbox_from_geometry(polygon) == [10.0, 45.0, 10.01, 45.01]
assert "sample.B08 - sample.B04" in evalscript("ndvi")
assert "sample.B08 - sample.B04" in evalscript("dvi")
assert OverlayRequest(geometry=polygon, index="ndvi", date=date(2026, 10, 1)).width == 512
assert any(route.path == "/overlay" for route in app.routes)
print("PASS: geometry, evalscripts, validation, routes")
