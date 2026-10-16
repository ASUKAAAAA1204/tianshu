from __future__ import annotations

import concurrent.futures
import sys
import time
from urllib.request import Request, urlopen


def probe(base_url: str) -> tuple[int, float]:
    started = time.perf_counter()
    with urlopen(Request(base_url.rstrip("/") + "/api/health", method="GET"), timeout=5) as response:
        response.read()
        return response.status, time.perf_counter() - started


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
    total = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    workers = min(16, max(1, total))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda _: probe(base_url), range(total)))
    codes = [code for code, _ in results]
    durations = sorted(duration for _, duration in results)
    p95 = durations[max(0, int(len(durations) * 0.95) - 1)]
    print({"total": total, "success": codes.count(200), "p95_s": round(p95, 3), "max_s": round(max(durations), 3)})
    return 0 if all(code == 200 for code in codes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
