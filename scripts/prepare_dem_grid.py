"""下载并裁剪梁平区域 SRTM 高程，生成离线 DEM 网格。

输出为轻量 JSON 网格，不依赖 GDAL/rasterio，便于比赛现场离线读取。
"""

from __future__ import annotations

import array
import gzip
import json
import math
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "demo" / "liangping_dem_grid.json"
BBOX = {"min_lat": 30.50, "max_lat": 30.88, "min_lng": 107.40, "max_lng": 108.05}
SAMPLE_STEP = 12  # SRTM1约30米采样，12点下采样为约360米网格
NROWS = 3601
TILE_DIR = ROOT / "data" / "source" / "dem"


def tile_name(lat: int, lng: int) -> str:
    return f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}{'E' if lng >= 0 else 'W'}{abs(lng):03d}"


def download_tile(lat: int, lng: int) -> bytes:
    name = tile_name(lat, lng)
    path = TILE_DIR / f"{name}.hgt.gz"
    if not path.exists():
        url = f"https://s3.amazonaws.com/elevation-tiles-prod/skadi/{name[:3]}/{name}.hgt.gz"
        request = Request(url, headers={"User-Agent": "LiangpingLowAltitudeResearch/0.1"})
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(urlopen(request, timeout=120).read())
    return gzip.decompress(path.read_bytes())


def sample_tile(raw: bytes, tile_lat: int, tile_lng: int, lat: float, lng: float) -> int | None:
    if not (tile_lat <= lat <= tile_lat + 1 and tile_lng <= lng <= tile_lng + 1):
        return None
    row = min(NROWS - 1, max(0, round((tile_lat + 1 - lat) * 3600)))
    col = min(NROWS - 1, max(0, round((lng - tile_lng) * 3600)))
    offset = (row * NROWS + col) * 2
    value = int.from_bytes(raw[offset:offset + 2], byteorder="big", signed=True)
    return None if value <= -32768 else value


def main() -> None:
    tiles = {(math.floor(BBOX["min_lat"]), math.floor(BBOX["min_lng"])), (math.floor(BBOX["min_lat"]), math.floor(BBOX["max_lng"]))}
    raw_tiles = {(lat, lng): download_tile(lat, lng) for lat, lng in tiles}
    latitudes = []
    longitudes = []
    elevations = []
    lat = BBOX["max_lat"]
    while lat >= BBOX["min_lat"] - 1e-9:
        latitudes.append(round(lat, 6))
        lat -= SAMPLE_STEP / 3600
    lng = BBOX["min_lng"]
    while lng <= BBOX["max_lng"] + 1e-9:
        longitudes.append(round(lng, 6))
        lng += SAMPLE_STEP / 3600
    for latitude in latitudes:
        row = []
        for longitude in longitudes:
            value = None
            for (tile_lat, tile_lng), raw in raw_tiles.items():
                value = sample_tile(raw, tile_lat, tile_lng, latitude, longitude)
                if value is not None:
                    break
            row.append(value)
        elevations.append(row)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({
        "type": "ElevationGrid",
        "metadata": {
            "name": "梁平区域SRTM高程参考网格",
            "source": "NASA SRTM via AWS Terrain Tiles",
            "source_url": "https://registry.opendata.aws/terrain-tiles/",
            "bbox": BBOX,
            "sample_step": SAMPLE_STEP,
            "approx_resolution_m": round(SAMPLE_STEP * 30.87, 1),
            "vertical_datum": "EGM96参考高程",
            "quality_level": "regional_reference",
            "usage": "地形风险和相对地面高度参考，不替代测绘成果",
        },
        "latitudes": latitudes,
        "longitudes": longitudes,
        "elevations_m": elevations,
    }, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUTPUT} grid={len(latitudes)}x{len(longitudes)}")


if __name__ == "__main__":
    main()
