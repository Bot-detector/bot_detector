import discord
from bot_detector.public_api import ReportScoreResponse


def resolve_primary_rsn(accounts: list[dict]) -> str | None:
    for account in accounts:
        if account.get("primary_rsn") == 1:
            return account.get("name")
    if accounts:
        return accounts[0].get("name")
    return None


def build_kc_embed(
    primary_rsn: str | None, data: list[ReportScoreResponse]
) -> discord.Embed:
    reports_submitted = sum(d.count for d in data if not d.manual_detect)
    possible_bans = sum(
        d.count
        for d in data
        if not d.manual_detect and not d.confirmed_ban and d.possible_ban
    )
    confirmed_bans = sum(
        d.count
        for d in data
        if not d.manual_detect and d.confirmed_ban and d.possible_ban
    )

    manual_confirmed_ban = sum(
        d.count for d in data if d.manual_detect and d.confirmed_ban
    )
    manual_confirmed_player = sum(
        d.count
        for d in data
        if d.manual_detect and not d.confirmed_ban and d.confirmed_player
    )
    manual_flags = sum(d.count for d in data if d.manual_detect)
    confirmed_manual_flags = manual_confirmed_ban + manual_confirmed_player
    manual_flag_accuracy = (
        (manual_confirmed_ban / confirmed_manual_flags) * 100
        if confirmed_manual_flags
        else 0
    )

    embed = discord.Embed(title=f"{primary_rsn}'s Stats", color=0x00FF00)
    embed.add_field(
        name="Reports Submitted (Auto):",
        value=f"{reports_submitted:,}",
        inline=False,
    )
    embed.add_field(
        name="Possible Bans (Auto):",
        value=f"{possible_bans:,}",
        inline=False,
    )
    embed.add_field(
        name="Confirmed Bans (Auto):",
        value=f"{confirmed_bans:,}",
        inline=False,
    )

    if manual_flags:
        embed.add_field(name="Manual Flags:", value=f"{manual_flags:,}", inline=False)
        embed.add_field(
            name="Manual Flag Accuracy:",
            value=f"{manual_flag_accuracy:.2f}%",
            inline=False,
        )

    embed.set_thumbnail(
        url="https://user-images.githubusercontent.com/5789682/117364618-212a3200-ae8c-11eb-8b42-9ef5e225930d.gif"
    )

    if reports_submitted == 0:
        embed.set_footer(
            text=(
                "If you have the plugin installed but are not seeing your KC increase, "
                "you may have to disable Anonymous Mode in your plugin settings."
            ),
            icon_url="https://raw.githubusercontent.com/Bot-detector/bot-detector/master/src/main/resources/warning.png",
        )
    return embed
