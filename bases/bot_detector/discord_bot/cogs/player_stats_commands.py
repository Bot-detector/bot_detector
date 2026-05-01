import logging
from datetime import datetime, timezone
from inspect import cleandoc
from typing import Any

import discord
from bot_detector.discord_bot.dependencies import BotDependencies
from bot_detector.discord_bot.utils import VERIFIED_PLAYER_ROLE
from discord import Color, Embed
from discord.ext import commands
from discord.ext.commands import Cog, Context

logger = logging.getLogger(__name__)

BOT_HUNTER_ROLES = [
    {
        "role_id": 825165287526498314,
        "role_name": "Bot Hunter I",
        "min": 1,
        "max": 5,
    },
    {
        "role_id": 825165422721499167,
        "role_name": "Bot Hunter II",
        "min": 5,
        "max": 10,
    },
    {
        "role_id": 825165526262874133,
        "role_name": "Bot Hunter III",
        "min": 10,
        "max": 25,
    },
    {
        "role_id": 825169068667305995,
        "role_name": "Bot Hunter IV",
        "min": 25,
        "max": 50,
    },
    {
        "role_id": 825165991503069225,
        "role_name": "Bot Hunter V",
        "min": 50,
        "max": 100,
    },
    {
        "role_id": 825166170989658112,
        "role_name": "Bot Hunter VI",
        "min": 100,
        "max": 250,
    },
    {
        "role_id": 825166288321642507,
        "role_name": "Bot Hunter VII",
        "min": 250,
        "max": 500,
    },
    {
        "role_id": 825166386862489623,
        "role_name": "Bot Hunter VIII",
        "min": 500,
        "max": 1000,
    },
    {
        "role_id": 825166550947332136,
        "role_name": "Bot Hunter IX",
        "min": 1000,
        "max": 2500,
    },
    {
        "role_id": 825166673337384990,
        "role_name": "Bot Hunter X",
        "min": 2500,
        "max": 5000,
    },
    {
        "role_id": 825166781056286751,
        "role_name": "Bot Hunter XI",
        "min": 5000,
        "max": 10000,
    },
    {
        "role_id": 825167037323673631,
        "role_name": "Bot Hunter XII",
        "min": 10000,
        "max": 25000,
    },
    {
        "role_id": 825167642184777738,
        "role_name": "Bot Hunter XIII",
        "min": 25000,
        "max": 50000,
    },
    {
        "role_id": 825167838753849384,
        "role_name": "Bot Hunter XIV",
        "min": 50000,
        "max": 100000,
    },
    {
        "role_id": 825168089363644427,
        "role_name": "Bot Hunter XV",
        "min": 100000,
        "max": 250000,
    },
    {
        "role_id": 825168309158281247,
        "role_name": "Bot Hunter XVI",
        "min": 250000,
        "max": 500000,
    },
    {
        "role_id": 825168632615010371,
        "role_name": "Bot Hunter XVII",
        "min": 500000,
        "max": 750000,
    },
    {
        "role_id": 825168881059758083,
        "role_name": "Bot Hunter XVIII",
        "min": 750000,
        "max": 1000000,
    },
    {
        "role_id": 825169438835081216,
        "role_name": "Bot Hunter XIX",
        "min": 1000000,
        "max": 2000000,
    },
    {
        "role_id": 825169641491791902,
        "role_name": "Bot Hunter XX",
        "min": 2000000,
        "max": 100_000_000,
    },
]

SKILLS_LIST = [
    "Attack",
    "Hitpoints",
    "Mining",
    "Strength",
    "Agility",
    "Smithing",
    "Defence",
    "Herblore",
    "Fishing",
    "Ranged",
    "Thieving",
    "Cooking",
    "Prayer",
    "Crafting",
    "Firemaking",
    "Magic",
    "Fletching",
    "Woodcutting",
    "runecraft",
    "Slayer",
    "Farming",
    "Construction",
    "Hunter",
    "Total",
]


class playerStatsCommands(Cog):
    def __init__(self, bot: commands.Bot, deps: BotDependencies) -> None:
        self.bot = bot
        self.deps = deps

    @commands.hybrid_command()
    @commands.has_any_role(VERIFIED_PLAYER_ROLE)
    async def lookup(self, ctx: Context, *, player_name: str):
        logger.debug(f"{ctx.author.name=}, {ctx.author.id=}, looking up: {player_name}")
        await ctx.typing()

        assert self.deps.legacy_api is not None
        player = await self.deps.legacy_api.get_player(player_name=player_name)

        if not player:
            await ctx.reply("Something went terribly wrong. :(")
            return

        player_id = player.get("id")
        assert isinstance(player_id, int)
        player_hiscore_result = await self.deps.legacy_api.get_hiscore_latest(
            player_id=player_id
        )

        if not player_hiscore_result:
            await ctx.reply("Could not find the user in our database")
            return

        player_hiscore: dict[str, Any] = player_hiscore_result[0]  # type: ignore
        ts = player_hiscore.get("timestamp")

        embeds = []
        embed = discord.Embed(
            title=player_name, description="OSRS Hiscores Lookup", color=0x00FF00
        )
        embed.set_footer(text=f"Updated on: {ts}")
        for skill in SKILLS_LIST:
            xp = player_hiscore.get(skill.lower())
            if xp:
                embed.add_field(
                    name=f"{skill}", value=f"EXP - {int(xp):,d}", inline=True
                )
        embeds.append(embed)

        exclude = ["id", "timestamp", "ts_date", "Player_id"]
        skills_lower = [s.lower() for s in SKILLS_LIST]
        bosses = [k for k in player_hiscore.keys() if k not in skills_lower + exclude]
        embed = None

        for boss in bosses:
            if embed is None:
                embed = discord.Embed(
                    title=player_name,
                    description="OSRS Hiscores Lookup",
                    color=0x00FF00,
                )
                embed.set_footer(text=f"Updated on: {ts}")
            kc = player_hiscore.get(boss)

            if kc is None or kc <= 0:
                continue

            assert isinstance(embed, discord.Embed)
            embed.add_field(name=f"{boss}", value=f"KC - {int(kc):,d}", inline=True)

            if len(embed.fields) >= 21:
                embeds.append(embed)
                embed = None

            if len(embeds) >= 9:
                await ctx.reply(embeds=embeds)
                embeds = []

        if embed and len(embed.fields) > 0:
            embeds.append(embed)

        if embeds:
            await ctx.reply(embeds=embeds)

    @commands.hybrid_command()
    @commands.has_any_role(VERIFIED_PLAYER_ROLE)
    async def kc(self, ctx: Context):
        logger.debug(f"{ctx.author.name=}, {ctx.author.id=}, Requesting kc")
        await ctx.typing()

        assert self.deps.legacy_api is not None
        linked_accounts = await self.deps.legacy_api.get_discord_links(
            discord_id=str(ctx.author.id)
        )

        if not linked_accounts:
            embed = discord.Embed(
                description=cleandoc(
                    """
                    Please use the !link command to pair an OSRS account.
                    You can use !verify to check if you are verified.
                    """
                )
            )
            await ctx.reply(embed=embed)
            return

        linked_accounts = [
            {"name": acc.get("name"), "primary_rsn": acc.get("primary_rsn")}
            for acc in linked_accounts
            if acc.get("Verified_status") == 1
        ]

        assert self.deps.public_api is not None
        data = await self.deps.public_api.get_report_score(
            names=[n["name"] for n in linked_accounts]
        )

        if not data:
            await ctx.reply("No data found.")
            return

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
        logger.info(
            f"{manual_flags=}, {confirmed_manual_flags=}, {manual_confirmed_ban=}, {manual_confirmed_player=}"
        )

        primary_rsn = None
        for account in linked_accounts:
            if account.get("primary_rsn") == 1:
                primary_rsn = account.get("name")

        if not primary_rsn and linked_accounts:
            primary_rsn = linked_accounts[0].get("name")

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
            embed.add_field(
                name="Manual Flags:", value=f"{manual_flags:,}", inline=False
            )
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
        await ctx.reply(embed=embed)

    @commands.hybrid_command()
    @commands.has_any_role(VERIFIED_PLAYER_ROLE)
    async def rankup(self, ctx: Context):
        logger.debug(f"{ctx.author.name=}, {ctx.author.id=}, Requesting rankup")
        await ctx.typing()

        if ctx.guild is None:
            await ctx.reply("This command must be used in a guild.")
            return

        assert self.deps.legacy_api is not None
        linked_accounts = await self.deps.legacy_api.get_discord_links(
            discord_id=str(ctx.author.id)
        )

        if not linked_accounts:
            embed = discord.Embed(
                description=cleandoc(
                    """
                    Please use the !link command to pair an OSRS account.
                    You can use !verify to check if you are verified.
                """
                )
            )
            await ctx.reply(embed=embed)
            return

        linked_accounts = [
            {"name": acc.get("name")}
            for acc in linked_accounts
            if acc.get("Verified_status") == 1
        ]

        assert self.deps.public_api is not None
        data = await self.deps.public_api.get_report_score(
            names=[n["name"] for n in linked_accounts]
        )
        confirmed_bans = sum(d.count for d in data if d.confirmed_ban)
        logger.debug(confirmed_bans)

        role_dict = [
            r
            for r in BOT_HUNTER_ROLES
            if r.get("max", 0) > confirmed_bans >= r.get("min", 0)
        ]
        if not role_dict:
            embed = discord.Embed(
                description="You currently have no confirmed bans. Keep hunting those bots, and you'll be there in no time! :)",
                color=discord.Colour.dark_red(),
            )
            await ctx.reply(embed=embed)
            return

        role = role_dict[0]
        new_role = discord.utils.find(
            lambda r: r.id == role.get("role_id"), ctx.guild.roles
        )

        if ctx.author.get_role(int(role.get("role_id"))):  # type: ignore[union-attr]
            embed = discord.Embed(
                description=f"You are not yet eligible for a new role. Only **{role.get('max', 0) - confirmed_bans}** more confirmed bans and you'll be there! :D",
                color=new_role.color if new_role else discord.Color.default(),
            )
            await ctx.reply(embed=embed)
            return

        for r in ctx.author.roles:  # type: ignore[union-attr]
            if "Bot Hunter" in r.name:
                await ctx.author.remove_roles(r, reason="rankup")  # type: ignore[union-attr]

        if new_role:
            await ctx.author.add_roles(new_role)  # type: ignore[union-attr]
        embed = discord.Embed(
            description=f"{ctx.author.display_name}, you are now a {new_role}!",
            color=new_role.color if new_role else discord.Color.default(),
        )
        embed.set_thumbnail(
            url="https://user-images.githubusercontent.com/45152844/116952387-8ac1fa80-ac58-11eb-8a31-5fe0fc6f5f88.gif"
        )
        await ctx.reply(embed=embed)

    @commands.hybrid_command()
    async def predict(self, ctx: Context, *, player_name: str):
        logger.debug(
            f"{ctx.author.name=}, {ctx.author.id=}, Requesting predict: [{player_name}]"
        )
        await ctx.typing()

        assert self.deps.public_api is not None
        predictions = await self.deps.public_api.get_prediction(
            names=[player_name], breakdown=True
        )

        if not predictions:
            await ctx.reply(f"I couldn't get a prediction for **{player_name}**.")
            return

        prediction = predictions[0]
        name = prediction.player_name
        pred_label = prediction.prediction_label or "N/A"
        confidence = prediction.prediction_confidence or 0
        breakdown = prediction.predictions_breakdown or {}

        color = Color.green() if pred_label.lower() == "real_player" else Color.red()

        summary_text = (
            f"**Name:** {name}\n"
            f"**Prediction:** {pred_label}\n"
            f"**Confidence:** {confidence * 100:.2f}%\n"
            "============"
        )

        # Build breakdown section
        _breakdown = [
            f"- **{k}:** {v * 100:.2f}%" for k, v in breakdown.items() if v > 0
        ]
        _breakdown_txt = "No breakdown available."
        _breakdown_txt = "\n".join(_breakdown) if _breakdown else _breakdown_txt

        embed = Embed(color=color, timestamp=datetime.now(timezone.utc))
        embed.add_field(
            name="Player Prediction",
            value=summary_text,
            inline=False,
        )
        embed.add_field(
            name="Predictions Breakdown",
            value=_breakdown_txt,
            inline=False,
        )
        embed.set_footer(text=f"Requested by {ctx.author.name}")

        await ctx.reply(embed=embed)

    @commands.hybrid_command()
    @commands.has_any_role(VERIFIED_PLAYER_ROLE)
    async def pwned(self, ctx: Context, player_name: str):
        logger.debug(
            f"{ctx.author.name=}, {ctx.author.id=}, Requesting pwned: {player_name}"
        )
        assert self.deps.legacy_api is not None
        player = await self.deps.legacy_api.get_player(player_name=player_name)

        if not player:
            await ctx.reply(f"I couldn't get data for {player_name} :(")
            return

        if player.get("label_jagex") == 2:
            await ctx.reply(f"{player_name} has been banned")
        else:
            await ctx.reply(f"{player_name} has NOT been banned")

    @commands.hybrid_command()
    @commands.has_any_role(VERIFIED_PLAYER_ROLE)
    async def gear(self, ctx: Context, player_name: str):
        logger.debug(
            f"{ctx.author.name=}, {ctx.author.id=}, Requesting gear: {player_name}"
        )
        assert self.deps.legacy_api is not None
        sighting = await self.deps.legacy_api.get_latest_sighting(
            player_name=player_name
        )

        if not sighting:
            await ctx.reply(f"I was unable to grab {player_name}'s latest outfit.")
            return

        embed = discord.Embed(
            title=f"{player_name}'s Last Seen Equipment",
            color=discord.Colour.dark_gold(),
        )

        equipped_items = 0
        sighting_data = sighting[0] if isinstance(sighting, list) else sighting

        for k, v in sighting_data.items():
            parts = k.split("_")
            if len(parts) > 1:
                slot = parts[1].capitalize()
            else:
                slot = k.capitalize()

            if v:
                item = await self.bot.osrs_items.get_by_id(v)  # type: ignore
                item_name = item.name if item else f"Unknown item (ID: {v})"

                equipped_items += 1
                embed.add_field(name=slot, value=item_name, inline=False)

        if equipped_items == 0:
            embed.add_field(
                name="(O_O;)",
                value=f"It appears that {player_name} was last seen.. naked.",
                inline=False,
            )
            embed.set_thumbnail(url="https://i.imgur.com/rYz39o6.png")
        await ctx.reply(embed=embed)

    @commands.hybrid_command()
    @commands.has_any_role(VERIFIED_PLAYER_ROLE)
    async def xpgain(self, ctx: Context, player_name: str):
        logger.debug(
            f"{ctx.author.name=}, {ctx.author.id=}, Requesting xpgain: {player_name}"
        )

        assert self.deps.legacy_api is not None
        gains = await self.deps.legacy_api.get_xp_gains(player_name=player_name)

        if not gains:
            await ctx.reply(f"I couldn't locate {player_name}'s hiscores gains. Sorry!")
            return

        gains_data: dict[str, Any] = gains
        latest_data: dict[str, Any] = gains_data.get("latest", {})
        second_latest_data: dict[str, Any] = gains_data.get("second", {})

        embed = discord.Embed(
            title=f"{player_name}'s Latest Daily XP/KC Gains",
            color=discord.Colour.dark_gold(),
        )

        diffs = 0

        keys_to_remove = ["id", "Player_id", "ts_date"]
        for key in keys_to_remove:
            latest_data.pop(key, None)

        timestamp = latest_data.pop("timestamp", None)

        for k, v in latest_data.items():
            k = " ".join(k.split("_"))
            k = k.capitalize()

            if v is None:
                v = 0

            if v > 0:
                embed.add_field(name=k, value=f"{int(v):,d}", inline=True)
                diffs += 1

        if diffs == 0:
            await ctx.reply(
                f"It doesn't appear that {player_name} has trained anything recently. Slacker!"
            )
        else:
            if second_latest_data and timestamp:
                dt_format = "%Y-%m-%dT%H:%M:%S"
                try:
                    latest_ts = datetime.strptime(timestamp, dt_format)
                    second_ts_str = second_latest_data.get("timestamp")
                    if second_ts_str:
                        second_latest_ts = datetime.strptime(second_ts_str, dt_format)
                        timestamp_delta = latest_ts - second_latest_ts
                        embed.add_field(
                            name="Duration", value=f"{timestamp_delta}", inline=False
                        )
                except ValueError:
                    embed.add_field(
                        name="Duration", value="Unable to parse timestamp", inline=False
                    )
            else:
                embed.add_field(
                    name="Duration", value="Insufficient data", inline=False
                )

            embed.set_footer(text=f"Last Updated: {timestamp}")
            await ctx.reply(embed=embed)
