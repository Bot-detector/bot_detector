"""Virtual machine: the resource model of the box a scenario runs on.

The Machine composes subsystems on the virtual timeline:

- ``cpu``: serial work accounting with cores and background load
- ``memory``: RAM accounting and pressure
- ``network``: latency, bandwidth, packet loss, partitions
- ``disk``: latency and failures
- ``processes``: gc-pause/freeze shaped stall injection
- ``random``: one seeded RNG behind every draw

Every draw comes from one RNG in a fixed order (stall -> fail ->
latency), and the virtual loop is single-threaded, so a run with the
same seed and call sequence replays exactly.
"""

from ..clock import VirtualClock
from ..loop import running_clock
from .config import (
    CpuConfig,
    DiskConfig,
    MachineConfig,
    MemoryConfig,
    NetworkConfig,
    ProcessConfig,
)
from .cpu import Cpu
from .disk import Disk
from .memory import Memory
from .network import Network
from .processes import Processes
from .randomness import Randomness
from .results import CpuGrant, IoError, IoResult

__all__ = [
    "Cpu",
    "CpuConfig",
    "CpuGrant",
    "Disk",
    "DiskConfig",
    "IoError",
    "IoResult",
    "Machine",
    "MachineConfig",
    "Memory",
    "MemoryConfig",
    "Network",
    "NetworkConfig",
    "ProcessConfig",
    "Processes",
    "Randomness",
]


class Machine:
    """Resource model of one machine on the virtual timeline.

    Bind it to a clock explicitly, or construct it inside a
    ``dst.run`` scenario and it picks up the running VirtualEventLoop's
    clock (same convention as ``virtual_time``).
    """

    def __init__(
        self, config: MachineConfig | None = None, clock: VirtualClock | None = None
    ):
        self.config = config if config is not None else MachineConfig()
        self.clock = clock if clock is not None else running_clock()
        self.random = Randomness(self.config.seed)
        self.processes = Processes(self.config.processes, self.random)
        self.cpu = Cpu(self.config.cpu, self.clock, self.processes)
        self.memory = Memory(self.config.memory)
        self.network = Network(self.config.network, self.random, self.processes)
        self.disk = Disk(self.config.disk, self.random, self.processes)
