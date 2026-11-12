from datetime import date
from io import BytesIO
from PIL import Image
import main
from fastapi import HTTPException

DAY = date(2026, 7, 31)

def test_stats_valid():
    payload = {"data": [{"outputs": {"index": {"bands": {"B0": {"stats": {"mean": 0.61, "min": 0.2, "max": 0.8, "sampleCount": 100, "noDataCount": 20}}}}}}]}
    result = main.parse_statistical_response(payload, DAY)
    assert result["mean"] == 0.61 and result["valid_count"] == 80 and result["status"] == "ok"

def test_no_acquisition():
    assert main.parse_statistical_response({"data": []}, DAY)["status"] == "no_acquisition"

def test_bad_response():
    try:
        main.parse_statistical_response({"data": [{"outputs": {}}]}, DAY)
        assert False, 'Expected HTTPException'
    except HTTPException as e:
        assert e.status_code == 502

def test_overlay_mask():
    im = Image.new('RGBA', (20, 20), (100, 150, 50, 255))
    b = BytesIO(); im.save(b, format='PNG')
    geom = {'type': 'Polygon', 'coordinates': [[[0,0],[0.5,0],[0.5,1],[0,1],[0,0]]]}
    out = Image.open(BytesIO(main.mask_overlay_to_geometry(b.getvalue(), geom, [0,0,1,1])))
    assert out.getpixel((18,10))[3] == 0
    assert out.getpixel((3,10))[3] == 255
