import asyncio
import logging
import time

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ts up to this far beyond now is tolerated clock skew and emits
# immediately; beyond that it is bogus (bad client) and would stall the
# stream for the whole delay, so it is dropped
FUTURE_LIMIT_S = 10 * 60.0


def message_ts(message: BaseModel) -> float | None:
    """Best-effort event timestamp (epoch seconds) from the payload.

    Known shape: ReportsToInsertStruct.report.ts. Returns None when the
    model carries no usable ts.
    """
    report = getattr(message, "report", None)
    ts = getattr(report, "ts", None)
    if isinstance(ts, (int, float)) and not isinstance(ts, bool) and ts >= 0:
        return float(ts)
    return None


class DelayAdapter:
    """Per-topic emission delay for a kafka queue.

    Holds each past-dated message until it is `delay_s` old (based on
    the ts in the message payload), so the topic streams `delay_s`
    behind live. A ts up to `FUTURE_LIMIT_S` beyond now is treated as
    clock skew and emits immediately; beyond that, or without a usable
    ts, the message is dropped: waiting on it would stall the whole
    group's stream.

    delay_s <= 0 gates nothing and passes everything through.
    """

    def __init__(self, delay_s: float):
        self.delay_s = delay_s

    async def hold(self, message: BaseModel | Exception | None) -> bool:
        """Wait out the delay; return False when the message must be dropped."""
        if self.delay_s <= 0 or not isinstance(message, BaseModel):
            return True
        ts = message_ts(message)
        if ts is None:
            logger.warning("delayed topic message without ts, dropping")
            return False
        now = time.time()
        if ts > now + FUTURE_LIMIT_S:
            logger.warning(f"delayed topic message with future ts={ts}, dropping")
            return False
        if ts >= now:
            return True
        wait = ts - (now - self.delay_s)
        if wait > 0:
            await asyncio.sleep(wait)
        return True
