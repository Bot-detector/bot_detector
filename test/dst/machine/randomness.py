"""One seeded RNG behind every machine draw.

Every randomness source on the machine (process stalls, packet loss,
latency jitter) draws from this one instance in call order, so a run
with the same seed and call sequence replays exactly. Scenarios can
draw from it too instead of keeping private ``random.Random`` state.
"""

import random


class Randomness:
    """Seeded uniform draws with a draw counter for auditing."""

    def __init__(self, seed: int) -> None:
        self.seed = seed
        self.draws = 0
        self._rng = random.Random(seed)

    def random(self) -> float:
        self.draws += 1
        return self._rng.random()

    def uniform(self, lo: float, hi: float) -> float:
        self.draws += 1
        return self._rng.uniform(lo, hi)
