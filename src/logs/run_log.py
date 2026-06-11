"""Write run metadata to data/run_log.json after each run."""
import json
import os
from datetime import datetime, timezone

RUN_LOG_PATH = "data/run_log.json"


def write_run_log(run_data: dict):
    """Append run metadata to run_log.json."""
    log = {"runs": []}
    if os.path.exists(RUN_LOG_PATH):
        with open(RUN_LOG_PATH) as f:
            log = json.load(f)
    log["runs"].append({
        "run_id": datetime.now(timezone.utc).isoformat(),
        **run_data
    })
    # Keep only last 500 runs (~3 months at 6/day)
    log["runs"] = log["runs"][-500:]
    os.makedirs("data", exist_ok=True)
    with open(RUN_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2, default=str)
