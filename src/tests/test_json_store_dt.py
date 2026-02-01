from datetime import datetime, timezone
from app.storage.json_store import _str_to_dt

def run():
    cases = [
        (None, None),
        (datetime(2026, 1, 31, 12, 34, 56), datetime(2026, 1, 31, 12, 34, 56)),
        ("2026-01-31T12:34:56", datetime(2026, 1, 31, 12, 34, 56)),
        ("2026-01-31T12:34:56Z", datetime(2026, 1, 31, 12, 34, 56, tzinfo=timezone.utc).astimezone(None)),
        (1700000000, datetime.fromtimestamp(1700000000, tz=timezone.utc).astimezone(None)),
        ({}, None),
    ]
    for inp, expected in cases:
        out = _str_to_dt(inp)
        if expected is None:
            assert out is None, f"{inp} -> {out}, expected None"
        else:
            assert out is not None and out.replace(tzinfo=None) == expected.replace(tzinfo=None), f"{inp} -> {out}, expected {expected}"

if __name__ == "__main__":
    run()
    print("ok")
