"""Seeded, percentage-based event injection for the firehose sim.

One RNG (seeded once) drives every injected event, so a run with the
same seed and schedule replays the same error/poison stream:

    schedule = EventSchedule(seed=42, error_pct=0.02, poison_pct=0.1)
    injector = EventInjector(schedule)
    event = injector.next_event()  # "error" | "poison" | None
"""

import random
from typing import Literal

from pydantic import BaseModel, Field


class EventSchedule(BaseModel):
    """Percentage-based fault schedule.

    error_pct/poison_pct are probabilities per consumed message, not
    absolute rates: at 200 msg/s, poison_pct=0.1 yields ~0.2 poison/s.
    """

    seed: int = 0
    error_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    poison_pct: float = Field(default=0.0, ge=0.0, le=100.0)


class EventInjector:
    """Draws injected events from one seeded RNG.

    A single uniform draw per call: [0, error_pct) -> "error",
    [error_pct, error_pct + poison_pct) -> "poison", else None. The
    same seed and call sequence always produce the same stream.
    """

    def __init__(self, schedule: EventSchedule):
        if schedule.error_pct + schedule.poison_pct > 100.0:
            raise ValueError(
                f"error_pct + poison_pct must be <= 100, got "
                f"{schedule.error_pct} + {schedule.poison_pct}"
            )
        self.schedule = schedule
        self._rng = random.Random(schedule.seed)
        self.draws = 0
        self.errors = 0
        self.poisons = 0

    def next_event(self) -> Literal["error", "poison"] | None:
        self.draws += 1
        roll = self._rng.random() * 100.0
        if roll < self.schedule.error_pct:
            self.errors += 1
            return "error"
        if roll < self.schedule.error_pct + self.schedule.poison_pct:
            self.poisons += 1
            return "poison"
        return None
