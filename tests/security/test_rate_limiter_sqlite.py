import time

from ai_ticket.security import SQLiteRateLimiter


def test_sqlite_rate_limiter_enforces_limits_across_instances(tmp_path):
    db_path = tmp_path / "rate.db"
    limiter_one = SQLiteRateLimiter(db_path, limit=2, window_seconds=1)
    limiter_two = SQLiteRateLimiter(db_path, limit=2, window_seconds=1)

    assert limiter_one.allow("client")[0]
    assert limiter_two.allow("client")[0]

    allowed, retry_after = limiter_one.allow("client")
    assert not allowed
    assert retry_after is not None

    time.sleep(1.05)
    assert limiter_two.allow("client")[0]

    limiter_one.close()
    limiter_two.close()
