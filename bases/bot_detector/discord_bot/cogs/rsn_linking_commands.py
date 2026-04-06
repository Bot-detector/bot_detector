import logging
from inspect import cleandoc

import discord
from bot_detector.discord_bot.dependencies import BotDependencies
from bot_detector.discord_bot.utils import checks, string_processing
from discord.ext import commands
from discord.ext.commands import Context

logger = logging.getLogger(__name__)


class rsnLinkingCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, deps: BotDependencies) -> None:
        self.bot = bot
        self.deps = deps

    def _batch(self, iterable, n=1):
        length = len(iterable)
        for ndx in range(0, length, n):
            yield iterable[ndx : min(ndx + n, length)]

    async def send_pm(self, ctx: Context, *args, **kwargs):
        try:
            await ctx.author.send(*args, **kwargs)
            await ctx.author.send(
                "https://media.discordapp.net/attachments/1008397996108566558/1011736267265937478/sentry_verify.gif?ex=69d4c293&is=69d37113&hm=cb23d156ad1b6cc7f2ae99a037af0c61ce93bd0936808b20cbbb0aef9b07e032"
            )
            await ctx.reply("Please check your PMs.")
        except discord.Forbidden:
            await ctx.reply(
                "This command requires that your PMs be enabled. Please enable your PMs, then try again."
            )

    async def verified_msg(self, name: str) -> discord.Embed:
        embed = discord.Embed(title=f"{name}'s Status:", color=0x00FF00)
        embed.add_field(name="Verified:", value=f"{name} is Verified.", inline=False)
        embed.set_thumbnail(
            url="https://user-images.githubusercontent.com/5789682/117238120-538b4f00-adfa-11eb-9c58-d5500af7d215.png"
        )
        return embed

    async def unverified_msg(self, name: str) -> discord.Embed:
        embed = discord.Embed(title=f"{name}'s Status:", color=0xFF0000)
        embed.add_field(
            name="Unverified:", value=f"{name} is Unverified.", inline=False
        )
        embed.add_field(
            name="Next Steps:", value=f"Please type '/link {name}'", inline=False
        )
        embed.set_thumbnail(
            url="https://user-images.githubusercontent.com/5789682/117239076-19bb4800-adfc-11eb-94c4-27ff7e1217cc.png"
        )
        return embed

    async def install_plugin_msg(self) -> discord.Embed:
        embed = discord.Embed(title="User Not Found:", color=0xFF0000)
        embed.add_field(
            name="Status:",
            value="No reports exist from specified player.",
            inline=False,
        )
        embed.add_field(
            name="Next Steps:",
            value="Please install the Bot-Detector Plugin on RuneLite if you have not done so.\n\nIf you have the plugin installed, you will need to disable Anonymous Reporting for us to be able to /link your account.",
            inline=False,
        )
        embed.set_thumbnail(
            url="https://user-images.githubusercontent.com/5789682/117361316-e1f9e200-ae87-11eb-8b42-9ef5e225930d.png"
        )
        return embed

    async def link_msg(self, name, code) -> discord.Embed:
        embed = discord.Embed(title=f"Linking '{name}':", color=0x0000FF)

        embed.add_field(
            name="STATUS",
            inline=False,
            value=cleandoc(
                f"""
                Request to link '{name}'.
                Access Code: {code}
            """
            ),
        )
        embed.add_field(
            name="SETUP",
            inline=False,
            value=cleandoc(
                f"""
                Please read through these instructions.
                1. Open Old School Runescape through RuneLite.
                2. Login as: '{name}'
                3. Join the clan channel: 'Bot Detector'.
                4. Verify that a Plugin Admin or Plugin Moderator is present in the channel.
                5. If a Plugin Admin or Plugin Moderator is not available, please leave a message in #detector-commands, or create a ticket in #support
                6. Type into the Clan Chat: '!Code {code}'.
                7. Type '/verify {name}' in #detector-commands channel to confirm that you have been Verified.
                8. Verification Process Complete.
            """
            ),
        )
        embed.add_field(
            name="INFO",
            inline=False,
            value=cleandoc(
                """
                You may link multiple Runescape accounts via this method.
                1. If you change the name of your account(s) you must repeat this process with your new RSN(s).
                2. In the event of a name change please allow some time for your data to be transferred over.
            """
            ),
        )
        embed.add_field(
            name="NOTICE",
            inline=False,
            value=cleandoc(
                """
                Do not delete this message.
                1. If this RSN was submitted in error, please type '/link <Your Correct RSN>'.
                2. This code will not expire, it is tied to your unique RSN:Discord Pair.
                3. If you are unable to become 'Verified' through this process, please contact an administrator for assistance.
            """
            ),
        )

        return embed

    @commands.hybrid_command(name="link")
    async def link(self, ctx: Context, *, name: str):
        logger.debug(f"{ctx.author.name=}, {ctx.author.id=}, Requesting link, {name=}")

        if not name:
            await ctx.reply(
                "Please specify the RSN of the account you'd wish to link. /link <RSN>"
            )
            return

        if not string_processing.is_valid_rsn(name):
            await ctx.reply(f"{name} isn't a valid Runescape user name.")
            return

        player = await self.deps.public_api.get_player(player_name=name)  # type: ignore
        if not player:
            embed = await self.install_plugin_msg()
            await ctx.reply(embed=embed)
            return

        linked_users = await self.deps.public_api.get_discord_player(player_name=name)  # type: ignore
        if not linked_users:
            linked_users = []

        linked_user = [
            user for user in linked_users if user.get("Discord_id") == ctx.author.id
        ]

        if linked_user:
            linked_user = linked_user[0]
            linked_status = linked_user.get("Verified_status") == 1
            if linked_status:
                embed = await self.verified_msg(name)
                await ctx.reply(embed=embed)
                return
            else:
                code = linked_user.get("Code")
                embed = await self.link_msg(name, code)
                await self.send_pm(ctx, embed=embed)
                return

        code = string_processing.get_random_id()

        await self.deps.public_api.post_discord_code(  # type: ignore
            discord_id=str(ctx.author.id),
            player_name=player.get("name"),
            code=code,
        )

        embed = await self.link_msg(name, code)
        await self.send_pm(ctx, embed=embed)

    @commands.hybrid_command(name="verify")
    async def verify(self, ctx: Context, name: str):
        logger.debug(
            f"{ctx.author.name=}, {ctx.author.id=}, Requesting verify, {name=}"
        )

        player = await self.deps.public_api.get_player(player_name=name)  # type: ignore
        if not player:
            embed = await self.install_plugin_msg()
            await ctx.reply(embed=embed)
            return

        linked_users = await self.deps.public_api.get_discord_player(player_name=name)  # type: ignore
        if not linked_users:
            linked_users = []

        if ctx.guild is None:
            await ctx.reply("This command must be used in a guild.")
            return

        is_privileged = any(ctx.author.get_role(r) for r in checks.PREVILEGED_ROLES)  # type: ignore[union-attr]

        if is_privileged:
            linked_user = linked_users[0] if linked_users else None
        else:
            matching_users = [
                user for user in linked_users if user.get("Discord_id") == ctx.author.id
            ]
            linked_user = matching_users[0] if matching_users else None

        if linked_user:
            linked_status = linked_user.get("Verified_status") == 1
            if linked_status:
                embed = await self.verified_msg(name)
                verified_role = discord.utils.find(
                    lambda r: r.id == checks.VERIFIED_PLAYER_ROLE,
                    ctx.guild.roles,  # type: ignore[union-attr]
                )
                if verified_role:
                    await ctx.author.add_roles(verified_role)  # type: ignore[union-attr]
                await ctx.reply(embed=embed)
                return
            else:
                code = linked_user.get("Code")
                embed = await self.link_msg(name, code)
                await self.send_pm(ctx, embed=embed)
                return
        else:
            embed = await self.unverified_msg(name)
            await ctx.reply(embed=embed)

    @commands.hybrid_command(name="linked")
    async def linked(self, ctx: Context):
        logger.debug(f"{ctx.author.name=}, {ctx.author.id=}, Requesting linked")

        links = await self.deps.public_api.get_discord_links(
            discord_id=str(ctx.author.id)
        )  # type: ignore

        if not links or len(links) == 0:
            await ctx.send(
                "You do not have any OSRS accounts linked to this Discord ID. Use the /link command in order to link an account."
            )
            return

        embeds = []
        for i, batch in enumerate(self._batch(links, n=21)):
            embed = discord.Embed(title="Linked Accounts", color=0x00FF00)
            for link in batch:
                if not link:
                    continue
                embed.add_field(name="Account:", value=link.get("name"), inline=True)
            embeds.append(embed)

            if i != 0 and i % 9 == 0:
                await ctx.reply(embeds=embeds)
                embeds = []

        if embeds:
            await ctx.reply(embeds=embeds)
