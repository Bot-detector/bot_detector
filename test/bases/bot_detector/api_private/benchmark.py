import logging
from time import perf_counter


class Benchmark:
    results = []

    def __init__(self, name, suppress_logging=False):
        self.name = name
        self.suppress_logging = suppress_logging
        if suppress_logging:
            self.original_level = self.set_logging_level("httpcore", logging.INFO)

    async def __aenter__(self):
        self.time_start = perf_counter()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        duration = perf_counter() - self.time_start
        self.results.append((self.name, duration))
        if self.suppress_logging:
            self.set_logging_level("httpcore", self.original_level)
        return False

    @classmethod
    def output_results(cls):
        print("{:<10} {:<10}".format("Name", "Duration"))
        durations = []
        for name, duration in cls.results:
            print("{:<10} {:<10.3f}".format(name, duration))
            durations.append(duration)
        return durations

    @staticmethod
    def set_logging_level(logger_name, level):
        logger = logging.getLogger(logger_name)
        original_level = logger.level
        logger.setLevel(level)
        return original_level
