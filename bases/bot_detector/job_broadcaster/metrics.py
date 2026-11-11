import logging

from prometheus_client import Counter, start_http_server

logger = logging.getLogger(__name__)


def start_metrics_server(port: int) -> None:
    start_http_server(port)
    logger.info(f"metrics server started on port {port}")


bans_applied_counter = Counter(
    name="job_broadcaster_bans_applied",
    documentation="Number of player bans applied (confirmed_ban set)",
)

embeds_sent_counter = Counter(
    name="job_broadcaster_embeds_sent",
    documentation="Number of Discord embeds posted successfully",
)

embeds_failed_counter = Counter(
    name="job_broadcaster_embeds_failed",
    documentation="Number of Discord embeds that failed to post",
)
