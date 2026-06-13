"""Write run metadata to data/run_log.json and data/last_run.txt after each run."""
import json
import os
from datetime import datetime, timezone, timedelta

RUN_LOG_PATH = "data/run_log.json"
LAST_RUN_PATH = "data/last_run.txt"

IST = timezone(timedelta(hours=5, minutes=30))


def write_run_log(run_data: dict) -> None:
    """Append run metadata to run_log.json and update last_run.txt.

    item_hashes are intentionally stripped here — they live in
    data/seen_hashes.json (written by dedup.write_seen_hashes).
    """
    os.makedirs("data", exist_ok=True)
    now = datetime.now(IST).isoformat()

    # Strip dedup hashes — not run history
    history_data = {k: v for k, v in run_data.items() if k != "item_hashes"}

    # run_log.json — human-readable run history only
    log = {"runs": []}
    if os.path.exists(RUN_LOG_PATH):
        try:
            with open(RUN_LOG_PATH) as f:
                log = json.load(f)
        except Exception:
            log = {"runs": []}
    log["runs"].append({"run_id": now, **history_data})
    log["runs"] = log["runs"][-500:]
    with open(RUN_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2, default=str)

    # last_run.txt — simple timestamp for quick status checks
    with open(LAST_RUN_PATH, "w") as f:
        f.write(
            f"{now}\n"
            f"status: {run_data.get('status', 'unknown')}\n"
            f"posts: {run_data.get('posts_published', 0)}\n"
        )
