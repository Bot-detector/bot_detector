"""DST: deterministic discrete-time simulation toolkit.

Simulate long-running async systems in virtual time. One VirtualClock
is the single timeline; VirtualEventLoop runs unmodified asyncio code
on it (``await asyncio.sleep(3600)`` costs one clock jump), VirtualMachine
accounts cpu/io costs and injects seeded faults, and ``virtual_time``
patches the sync ``time`` module for blocking legacy code. The runner
turns a scenario coroutine into a SimResult.
"""

from .clock import VirtualClock
from .loop import DSTIdleError, VirtualEventLoop
from .machine import IoConfig, IoError, MachineConfig, VirtualMachine  # noqa: F401
from .machine import FaultSchedule  # noqa: F401
from .runner import SimResult, run
from .timepatch import virtual_time

__all__ = [
    "DSTIdleError",
    "FaultSchedule",
    "IoConfig",
    "IoError",
    "MachineConfig",
    "SimResult",
    "VirtualClock",
    "VirtualEventLoop",
    "VirtualMachine",
    "run",
    "virtual_time",
]
