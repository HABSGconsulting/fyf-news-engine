"""more_reads.py — builds YAML digest from MoreReadsItem list."""
from datetime import datetime, timezone
from src.ai.schema import MoreReadsItem
from config.settings import MORE_READS_DATA_PATH


def _ys(v) -> str:
    """Wrap value in YAML double-quotes, escaping any inner double-quotes."""
    return '"' + str(v).replace('"', '\\"') + '"'


def build_more_reads(items: list[MoreReadsItem], run_dt: datetime | None = None) -> tuple[str, str]:
    """
    Returns (relative_path, yaml_content).
    Writes one YAML file per run under data/more-reads/YYYY/MM/.
    """
    if run_dt is None:
        run_dt = datetime.now(timezone.utc)

    ts = run_dt.strftime("%Y%m%d-%H%M")
    year_month = run_dt.strftime("%Y/%m")
    rel_path = f"{MORE_READS_DATA_PATH}/{year_month}/{ts}.yaml"

    lines = ["items:"]
    for item in items:
        lines.append(f"  - title: {_ys(item.title)}")
        lines.append(f"    url: {_ys(item.url)}")
        lines.append(f"    one_liner: {_ys(item.one_liner)}")
        lines.append(f"    category: {_ys(item.category.value)}")

    content = "\n".join(lines) + "\n"
    return rel_path, content
