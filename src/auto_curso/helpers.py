from __future__ import annotations


def format_seconds(seconds: float) -> str:
    """Formata um número de segundos em um formato de tempo HH:MM:SS.

    Args:
        seconds (float): O número de segundos a ser formatado.

    Returns:
        str: O tempo formatado em HH:MM:SS.
    """

    if seconds != seconds or seconds < 0:  # NaN check
        return "00:00"
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
