"""Run Sprint 3 end to end: screener, composite score, peer percentiles, radar charts, Excel reports."""
from pathlib import Path

from src.analytics.metrics import latest_snapshot
from src.analytics.peer import CORE_METRICS, compute_percentiles, write_peer_percentiles
from src.analytics.peer_report import write_peer_workbook
from src.analytics.radar import generate_radar_charts
from src.data.loader import load_clean
from src.dq.rules import run_all as run_dq
from src.screener.engine import add_composite_score, load_config, run_all_presets
from src.screener.export import write_screener_workbook

ROOT = Path(__file__).parent


def main() -> None:
    tables, clean_log = load_clean()
    cfg = load_config()
    scored = add_composite_score(latest_snapshot(tables), cfg)

    results = run_all_presets(scored, cfg)
    write_screener_workbook(results, ROOT / "output/screener_output.xlsx", cfg)
    for name, df in results.items():
        print(f"{name:22s} {len(df):3d} companies")

    pp = compute_percentiles(scored, tables["peer_groups"], CORE_METRICS)
    n = write_peer_percentiles(pp, ROOT / "data/nifty100.db")
    print(f"peer_percentiles rows: {n}")
    write_peer_workbook(scored, tables["peer_groups"], ROOT / "output/peer_comparison.xlsx")
    print("radar charts:", generate_radar_charts(scored, tables["peer_groups"], ROOT / "reports/radar_charts", cfg))

    clean_log.to_csv(ROOT / "output/cleaning_log.csv", index=False)
    run_dq(tables).to_csv(ROOT / "output/dq_summary.csv", index=False)
    scored.to_csv(ROOT / "output/kpi_latest_scored.csv", index=False)


if __name__ == "__main__":
    main()
