"""Background process faults: gc-pause / freeze shaped stalls."""

import asyncio

from .config import ProcessConfig
from .randomness import Randomness


class Processes:
    """Stall injection for everything that runs on the machine.

    ``roll_stall()`` is drawn first on every cpu/network/disk
    operation (fixed draw order: stall -> fail -> latency), and a
    positive result is added to that operation's duration.
    """

    def __init__(self, config: ProcessConfig, rng: Randomness) -> None:
        self.config = config
        self._rng = rng
        self.stalls = 0
        self.stall_s = 0.0

    def roll_stall(self) -> float:
        """Draw one stall roll; returns the stall seconds (0.0 = none)."""
        if self._rng.random() * 100.0 < self.config.stall_pct:
            self.stalls += 1
            self.stall_s += self.config.stall_s
            return self.config.stall_s
        return 0.0

    async def pause(self) -> float:
        """Roll a stall and wait it out; for explicit scenario use."""
        stall_s = self.roll_stall()
        if stall_s > 0.0:
            await asyncio.sleep(stall_s)
        return stall_s
