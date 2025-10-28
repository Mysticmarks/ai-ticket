from ai_ticket.observability.metrics import MetricsStore
from ai_ticket.observability.persistence import SQLiteMetricsPersistence


def test_metrics_store_persists_across_instances(tmp_path):
    db_path = tmp_path / "metrics.db"
    persistence = SQLiteMetricsPersistence(db_path)
    store = MetricsStore(persistence=persistence, retention_seconds=900)
    store.record_event(latency_s=0.2, success=True)
    store.record_event(latency_s=0.3, success=False, error_code="failure", message="oops")

    snapshot = store.snapshot()
    assert snapshot["totals"]["requests"] == 2
    assert snapshot["totals"]["errors"] == 1

    persistence.close()

    restored_persistence = SQLiteMetricsPersistence(db_path)
    restored_store = MetricsStore(persistence=restored_persistence, retention_seconds=900)
    restored_snapshot = restored_store.snapshot()

    assert restored_snapshot["totals"]["requests"] == 2
    assert restored_snapshot["totals"]["errors"] == 1
    assert restored_snapshot["recentErrors"][0]["code"] == "failure"

    restored_persistence.close()
