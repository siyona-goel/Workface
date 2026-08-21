"""Quick smoke test for Day-2 client.

Run from repo root with REPLAY_MODE=true (default):

    python -m apps.api.fortyguard.example_usage

Or from notebooks / scripts:
    from apps.api.fortyguard import FortyGuardClient
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# allow running as script without installing the package
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from apps.api.fortyguard import FortyGuardClient

# minimal body so hash is stable
HEATMAP_BODY = {
    "polygon_aoi": {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-74.0170, 40.7050],
                            [-74.0030, 40.7050],
                            [-74.0030, 40.7180],
                            [-74.0170, 40.7180],
                            [-74.0170, 40.7050],
                        ]
                    ],
                },
            }
        ],
    },
    "date_time": {
        "start_date": "2024-07-15",
        "start_time": "14:00",
        "filter_type": 1,
    },
    "granularity": 100,
}


async def main() -> None:
    client = FortyGuardClient()  # reads REPLAY_MODE + key from env
    print(f"REPLAY_MODE = {client.replay_mode}")

    try:
        result = await client.call("heatmap", HEATMAP_BODY)
        status = (result.get("data") or {}).get("status")
        print(f"heatmap → {status}")
    except FileNotFoundError as e:
        print(f"Replay miss (expected until fixtures are in data/fixtures/): {e}")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
