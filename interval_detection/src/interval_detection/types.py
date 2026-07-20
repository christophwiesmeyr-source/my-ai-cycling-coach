"""Public types for the interval detection package."""

from typing import NamedTuple


class Interval(NamedTuple):
    """A detected structured work interval.

    Times are in seconds since the start of the activity. This is the stable
    output contract of the package — keep it small.
    """

    start_s: float
    end_s: float

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s
