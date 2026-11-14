import logging

from bot_detector.database.ban_broadcast import BanCounts, BannedBot
from bot_detector.discord_webhook import Embed, EmbedField, utcnow

logger = logging.getLogger(__name__)

THUMBNAIL_TOTALS = "https://c.tenor.com/V71SmWqyYHkAAAAM/kermit-freaking.gif"
THUMBNAIL_NAMES = "https://i.imgur.com/PPnZRHW.gif"
THUMBNAIL_COMPLETE = "https://oldschool.runescape.wiki/images/5/58/Crazy_dance.gif"

EMBED_COLOR = 0x000000


def chunk_bots(
    bots: list[BannedBot],
    max_names: int = 50,
    max_chars: int = 1000,
) -> list[list[BannedBot]]:
    """Split bots into embed-sized chunks.

    Discord caps a field value at 1024 chars, so chunks respect both a name
    count limit and the length of the joined name string. A single name
    longer than max_chars becomes its own chunk (never an empty one).
    """
    if max_names < 1 or max_chars < 1:
        raise ValueError("max_names and max_chars must both be >= 1")

    chunks: list[list[BannedBot]] = []
    current: list[BannedBot] = []

    for bot in bots:
        candidate = [*current, bot]
        joined = ", ".join(b.name for b in candidate)
        if len(candidate) > max_names or len(joined) > max_chars:
            if current:
                chunks.append(current)
            current = [bot]
            continue
        current = candidate

    if current:
        chunks.append(current)
    return chunks


def build_totals_embed(counts: BanCounts, bot_bans: int) -> Embed:
    return Embed(
        title="Pending Bans Stats",
        description="Latest Ban Totals From Our Hiscores Scrapes",
        color=EMBED_COLOR,
        timestamp=utcnow(),
        thumbnail_url=THUMBNAIL_TOTALS,
        fields=(
            EmbedField(name="Total Unapplied Bans", value=f"{counts.total_bans:,}"),
            EmbedField(
                name="Predicted as Real Player (Not Counted)",
                value=f"{counts.real_player_bans:,}",
            ),
            EmbedField(
                name="No Hiscore Data (Not Counted)",
                value=f"{counts.no_data_bans:,}",
            ),
            EmbedField(name="Predicted as Bots (These Count)", value=f"{bot_bans:,}"),
        ),
    )


def build_names_embed(chunk: list[BannedBot]) -> Embed:
    names = ", ".join(bot.name for bot in chunk)
    return Embed(
        title="All Ye Bots Lose All Hope!",
        description=f"{len(chunk)} Accounts",
        color=EMBED_COLOR,
        timestamp=utcnow(),
        thumbnail_url=THUMBNAIL_NAMES,
        fields=(EmbedField(name="Bans Being Added", value=names),),
    )


def build_complete_embed(num_bans: int) -> Embed:
    return Embed(
        title="Bans Added!",
        description="Bans were added to the project's total. Time to check your kc! ",
        color=EMBED_COLOR,
        timestamp=utcnow(),
        thumbnail_url=THUMBNAIL_COMPLETE,
        fields=(EmbedField(name="Total Bans Added:", value=f"{num_bans:,}"),),
    )
