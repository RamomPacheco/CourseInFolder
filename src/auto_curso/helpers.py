from __future__ import annotations


def format_seconds(seconds: float) -> str:
    if seconds != seconds or seconds < 0:  # NaN check
        return "00:00"
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
