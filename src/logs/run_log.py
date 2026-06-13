"""Write run metadata to data/run_log.json and data/last_run.txt after each run."""
import json
import os
from datetime import datetime, timezone

RUN_LOG_PATH = "data/run_log.json"
LAST_RUN_PATH = "data/last_run.txt"


def write_run_log(run_data: dict) -> None:
    """Append run metadata to run_log.json and update last_run.txt."""
    os.makedirs("data", exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    # run_log.json
    log = {"runs": []}
    if os.path.exists(RUN_LOG_PATH):
        try:
            with open(RUN_LOG_PATH) as f:
                log = json.load(f)
        except Exception:
            log = {"runs": []}
    log["runs"].append({"run_id": now, **run_data})
    log["runs"] = log["runs"][-500:]
    with open(RUN_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2, default=str)

    # last_run.txt — simple timestamp for quick status checks
    with open(LAST_RUN_PATH, "w") as f:
        f.write(f"{now}\nstatus: {run_data.get('status', 'unknown')}\nposts: {run_data.get('posts_published', 0)}\n")
