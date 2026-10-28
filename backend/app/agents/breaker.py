"""Circuit breaker (spec 8.8): three failures in 60 seconds send an agent's work to its
fallback for 60 seconds; then one trial call checks whether it has recovered.

The dev panel's failure switch forces the narrator's breaker open, so the demo can show the
feed carrying on with template lines.
"""

import time
from collections import deque
from collections.abc import Callable

FAILURES = 3
WINDOW_S = 60.0
OPEN_S = 60.0


class Breaker:
    def __init__(self, now: Callable[[], float] = time.monotonic) -> None:
        self.now = now
        self.failures: deque[float] = deque()
        self.opened_at: float | None = None
        self.forced = False
        self.trial = False          # a half-open trial call is in flight
        self.trips = 0

    @property
    def state(self) -> str:
        if self.forced:
            return "forced"
        if self.opened_at is None:
            return "closed"
        return "half_open" if self.now() - self.opened_at >= OPEN_S else "open"

    def allow(self) -> bool:
        """Whether a call may go out now. In half-open, only one trial at a time."""
        state = self.state
        if state == "closed":
            return True
        if state == "half_open" and not self.trial:
            self.trial = True
            return True
        return False

    def record(self, ok: bool) -> None:
        now = self.now()
        if self.state == "half_open" or self.trial:
            self.trial = False
            if ok:
                self.opened_at = None
                self.failures.clear()
            else:
                self.opened_at = now
            return
        if ok:
            return
        self.failures.append(now)
        while self.failures and now - self.failures[0] > WINDOW_S:
            self.failures.popleft()
        if len(self.failures) >= FAILURES:
            self.opened_at = now
            self.failures.clear()
            self.trips += 1

    def force(self, on: bool) -> None:
        self.forced = on
        self.trial = False
