"""F2 starvation hunt: sustained load, mixed fleet, count the victims.

The open F2 defect (see the retired perf analysis): under sustained
load exactly one connection stops receiving while the server believes
it delivered - never seed-correlated, victim index varies per run.

Method: a producer paces 50 msg/s into players.scraped for the whole
window while a mixed fleet (fast clients and increasingly slow ones)
stays connected and drains. Nobody should be kicked: every client,
even the slowest, outruns the feed. After the window, a client that
received far less than the fleet median is a starvation victim.

Run inside the smoke container:

    SMOKE_MODE=hunt python src/smoke.py

Exit 0 when no victim appeared; exit 1 prints the victims.
"""

import asyncio
import json
import os
import time

from kafka import KafkaProducer

from smoke import Client

WAIT = float(os.environ.get("HUNT_DURATION_S", "60"))
FLEET_SIZE = int(os.environ.get("HUNT_CLIENTS", "12"))
FEED_RATE_S = float(os.environ.get("HUNT_FEED_RATE_S", "50"))
PRODUCE_WINDOW = 1.0  # seconds between producer slices

SLOW_STEPS = (0.0, 0.005, 0.02)  # per-message delays rotated over the fleet


def build_fleet() -> list[Client]:
    fleet = []
    for i in range(FLEET_SIZE):
        slow = SLOW_STEPS[i % len(SLOW_STEPS)]
        fleet.append(Client(f"hunt-{i}", "fast", slow_s=slow))
    return fleet


async def produce_sustained(template: dict, stop_at: float) -> int:
    producer = KafkaProducer(
        bootstrap_servers=os.environ.get("KAFKA_BROKER", "kafka:9092"),
        value_serializer=lambda x: json.dumps(x).encode(),
        acks=1,
    )
    sent = 0
    while time.monotonic() < stop_at:
        for _ in range(max(1, int(FEED_RATE_S * PRODUCE_WINDOW))):
            message = json.loads(json.dumps(template))
            name = message["player_data"]["name"]
            message["player_data"]["name"] = f"{name}-hunt-{sent}"
            producer.send(topic="players.scraped", value=message)
            sent += 1
        await asyncio.sleep(PRODUCE_WINDOW)
    producer.flush()
    producer.close()
    return sent


def analyze(fleet: list[Client]) -> dict:
    """F2 signature: a fast client far below the fast fleet's median.

    Slow clients lag by design (they pace themselves below the feed),
    so only fast clients can be starvation victims.
    """
    fast = [c for c in fleet if c.slow_s == 0.0]
    fast_counts = sorted(len(c.messages) for c in fast)
    fast_median = fast_counts[len(fast_counts) // 2] if fast_counts else 0
    victims_list = [c.name for c in fast if len(c.messages) < fast_median * 0.5]
    return {
        "fast_min": fast_counts[0] if fast_counts else 0,
        "fast_median": fast_median,
        "fast_max": fast_counts[-1] if fast_counts else 0,
        "victims": victims_list,
        "clean": bool(fast) and not victims_list and fast_median > 0,
    }


async def main() -> dict:
    fleet = build_fleet()
    for client in fleet:
        await client.connect()
    stop_at = time.monotonic() + WAIT

    async def feed_template() -> None:
        # grab one real payload from any client stream as the template
        while template_holder[0] is None and time.monotonic() < stop_at:
            for client in fleet:
                if client.messages:
                    template_holder[0] = json.loads(client.messages[0])
                    return
            await asyncio.sleep(0.2)

    template_holder: list = [None]
    template_task = asyncio.create_task(feed_template())
    await template_task
    produced = (
        await produce_sustained(template_holder[0], stop_at)
        if template_holder[0]
        else 0
    )

    for client in fleet:
        await client.close()
    await asyncio.sleep(3)

    counts = {c.name: len(c.messages) for c in fleet}
    analysis = analyze(fleet)
    report = {
        "mode": "hunt",
        "produced": produced,
        "duration_s": WAIT,
        "fleet": counts,
        "fleet_close_codes": {c.name: c.close_code for c in fleet},
        "fast_min": analysis["fast_min"],
        "fast_median": analysis["fast_median"],
        "fast_max": analysis["fast_max"],
        "victims": analysis["victims"],
        "clean": analysis["clean"],
    }
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    results = asyncio.run(main())
    raise SystemExit(0 if results.get("clean") else 1)
