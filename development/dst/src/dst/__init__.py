"""DST: deterministic discrete-time simulation toolkit.

Simulate long-running async systems in virtual time. One VirtualClock
is the single timeline; VirtualEventLoop runs unmodified asyncio code
on it (``await asyncio.sleep(3600)`` costs one clock jump), Machine
accounts cpu/memory/network/disk costs and injects seeded faults, and
``virtual_time`` patches the sync ``time`` module for blocking legacy
code. The runner turns a scenario coroutine into a SimResult.
"""

from .clock import VirtualClock
from .loop import DSTIdleError, VirtualEventLoop
from .machine import (
    CpuConfig,
    CpuGrant,
    DiskConfig,
    IoError,
    IoResult,
    Machine,
    MachineConfig,
    MemoryConfig,
    NetworkConfig,
    ProcessConfig,
)  # noqa: F401
from .runner import SimResult, run
from .timepatch import virtual_time
from .units import GB, KB, MB  # noqa: F401

__all__ = [
    "CpuConfig",
    "CpuGrant",
    "DSTIdleError",
    "DiskConfig",
    "GB",
    "IoError",
    "IoResult",
    "KB",
    "MB",
    "Machine",
    "MachineConfig",
    "MemoryConfig",
    "NetworkConfig",
    "ProcessConfig",
    "SimResult",
    "VirtualClock",
    "VirtualEventLoop",
    "run",
    "virtual_time",
]
