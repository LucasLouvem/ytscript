from typing import NamedTuple


class Segment(NamedTuple):
    start: float
    text: str
    duration: float = 0.0
