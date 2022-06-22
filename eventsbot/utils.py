import re


def duration_to_seconds(duration: str) -> int:
    """Convert a given duration to seconds."""

    units = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    regex = re.compile(r"(\d+)([dhms])")

    seconds = 0
    for match in regex.findall(duration):
        seconds += int(match[0]) * units[match[1]]

    return seconds
