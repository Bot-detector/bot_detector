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

db_retries_counter = Counter(
    name="job_broadcaster_db_retries",
    documentation="Number of DB transaction retries after transient errors",
)

embeds_sent_counter = Counter(
    name="job_broadcaster_embeds_sent",
    documentation="Number of Discord embeds posted successfully",
)

embeds_failed_counter = Counter(
    name="job_broadcaster_embeds_failed",
    documentation="Number of Discord embeds that failed to post",
)

ban_events_produced_counter = Counter(
    name="job_broadcaster_ban_events_produced",
    documentation="Number of players.banned events published for applied bans",
)

ban_events_failed_counter = Counter(
    name="job_broadcaster_ban_events_failed",
    documentation="Number of players.banned events given up on after retries",
)
