import fnmatch
import logging
import math
import os
import urllib.request
from datetime import date
from inspect import cleandoc

import discord
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import PIL
import seaborn as sns
from bot_detector.discord_bot.dependencies import BotDependencies
from bot_detector.discord_bot.utils import OWNER_ROLE, PATREON_ROLE
from discord.ext import commands
from discord.ext.commands import Cog, Context

logger = logging.getLogger(__name__)


class mapCommands(Cog):
    def __init__(self, bot: commands.Bot, deps: BotDependencies) -> None:
        self.bot = bot
        self.deps = deps

    async def _web_request(self, url: str) -> dict | None:
        async with self.deps.session.get(url) as response:
            if response.status != 200:
                logger.error({"status": response.status, "url": url})
                return None
            return await response.json()

    @commands.hybrid_command()
    async def region(self, ctx: Context, *, region_name: str):
        debug = {
            "author": ctx.author.name,
            "author_id": ctx.author.id,
            "msg": f"Requested region {region_name}",
        }
        logger.debug(debug)

        data_region = await self.deps.public_api.get_heatmap_region(
            region_name=region_name
        )  # type: ignore
        if not data_region:
            embed = discord.Embed(
                color=discord.Colour.dark_red(),
                description=cleandoc(
                    f"""
                    {region_name} does not correspond with any of our labeled regions.
                    It is possible that we just need to add it. Please let us know if so!
                """
                ),
            )
            return await ctx.send(embed=embed)

        df_data_region = pd.DataFrame(data_region)
        df_region = self._display_duplicates(df_data_region)

        if len(df_region) == 0:
            embed = discord.Embed(
                color=discord.Colour.dark_red(),
                description=cleandoc(
                    f"""
                    {region_name} does not correspond with any of our labeled regions.
                    It is possible that we just need to add it. Please let us know if so!
                """
                ),
            )
            return await ctx.send(embed=embed)

        if len(df_region) < 30:
            region_true_name, region_id = self._autofill(df_region, region_name)

            msg = cleandoc(
                f"""```diff
                Input: {region_name}
                Selection From: {", ".join(str(elem) for elem in df_region["region_name"].values)}
                Selected: {region_true_name}
            ```"""
            )
        else:
            msg = "```diff\n- More than 30 Regions selected. Please refine your search.```"

        await ctx.send(msg)

    @commands.hybrid_command(aliases=["hm"])
    @commands.has_any_role(PATREON_ROLE, OWNER_ROLE)
    async def heatmap(self, ctx: Context, *, region: str):
        debug = {
            "author": ctx.author.name,
            "author_id": ctx.author.id,
            "msg": f"Requested heatmap {region}",
        }
        logger.debug(debug)

        if not region:
            return await ctx.send("Please enter a region name or region ID.")

        await ctx.typing()

        if region.isdigit():
            region_true_name = f"Region ID: {region}"
            map_file_path = await self._run_analysis(region_true_name, region)

            if not map_file_path:
                await self.map(ctx, region=region)
                await ctx.reply("We have no data on this region yet.")
            else:
                try:
                    await ctx.reply(file=discord.File(map_file_path))
                except Exception as e:
                    logger.error(f"Failed to send heatmap: {e}")
                    await ctx.reply(
                        "Uhhh... I should have a heatmap to give you, but I don't. Please accept this image of a cat fixing our bot instead."
                    )
                    await ctx.reply("https://i.redd.it/lel3o4e2hhp11.jpg")
        else:
            assert self.deps.public_api is not None
            data_region = await self.deps.public_api.get_heatmap_region(
                region_name=region
            )  # type: ignore
            if not data_region:
                embed = discord.Embed(
                    description=cleandoc(
                        f"""
                        "{region}" does not correspond with any of our labeled regions.
                        It is possible that we just need to add it. Please let us know if so!
                    """
                    ),
                    color=discord.Colour.dark_red(),
                )
                return await ctx.reply(embed=embed)

            df_data_region = pd.DataFrame(data_region)
            df_region = self._display_duplicates(df_data_region)

            if len(df_region) == 0:
                embed = discord.Embed(
                    description=cleandoc(
                        f"""
                        "{region}" does not correspond with any of our labeled regions.
                        It is possible that we just need to add it. Please let us know if so!
                    """
                    ),
                    color=discord.Colour.dark_red(),
                )
                return await ctx.reply(embed=embed)

            if len(df_region) < 30:
                region_true_name, region_id = self._autofill(df_region, region)
                map_file_path = await self._run_analysis(
                    region_true_name, str(region_id)
                )

                if not map_file_path:
                    await self.map(ctx, region=region)
                    await ctx.reply("We have no data on this region yet.")
                else:
                    try:
                        await ctx.reply(file=discord.File(map_file_path))
                    except Exception as e:
                        logger.error(f"Failed to send heatmap: {e}")
                        await ctx.reply(
                            "Uhhh... I should have a heatmap to give you, but I don't. Please accept this image of a cat fixing our bot instead."
                        )
                        await ctx.reply("https://i.redd.it/lel3o4e2hhp11.jpg")
            else:
                msg = ">30 Regions selected. Please refine your search."
                await ctx.reply(msg)

    @commands.hybrid_command("map")
    async def map(self, ctx: Context, *, region: str | None = None):
        debug = {
            "author": ctx.author.name,
            "author_id": ctx.author.id,
            "msg": f"Requested map {region}",
        }
        logger.debug(debug)

        if not region:
            return await ctx.send("Please enter a region name or region ID.")

        if region.isdigit():
            msg = f"https://raw.githubusercontent.com/Ferrariic/OSRS-Visible-Region-Images/main/Region_Maps/{region}.png"
        else:
            assert self.deps.public_api is not None
            data_region = await self.deps.public_api.get_heatmap_region(
                region_name=region
            )  # type: ignore
            if not data_region:
                embed = discord.Embed(
                    description=cleandoc(
                        f"""
                        "{region}" does not correspond with any of our labeled regions.
                        It is possible that we just need to add it. Please let us know if so!
                    """
                    ),
                    color=discord.Colour.dark_red(),
                )
                return await ctx.send(embed=embed)

            df_data_region = pd.DataFrame(data_region)
            df_region = self._display_duplicates(df_data_region)

            if len(df_region) == 0:
                embed = discord.Embed(
                    description=cleandoc(
                        f"""
                        "{region}" does not correspond with any of our labeled regions.
                        It is possible that we just need to add it. Please let us know if so!
                    """
                    ),
                    color=discord.Colour.dark_red(),
                )
                return await ctx.send(embed=embed)

            if len(df_region) < 30:
                region_true_name, region_id = self._autofill(df_region, region)
                msg = f"https://raw.githubusercontent.com/Ferrariic/OSRS-Visible-Region-Images/main/Region_Maps/{region_id}.png"
            else:
                msg = "```diff\n- More than 30 Regions selected. Please refine your search.```"

        await ctx.send(msg)

    async def _run_analysis(self, region_true_name: str, region_id: str):
        filename = self._get_filename(region_id=region_id)

        if self._heatmap_exists(filename=filename):
            return filename
        else:
            self._clean_old_heatmaps(region_id=region_id)

        region_id_int = int(region_id)

        data = await self.deps.public_api.get_heatmap_data(region_id=region_id_int)  # type: ignore
        if not data:
            return False

        df = pd.DataFrame(data)

        if df.empty:
            return False

        if "confirmed_ban" in df.columns:
            try:
                self._plot_heatmap(
                    df_local_ban=df, regionid=region_id_int, filename=filename
                )
            except ValueError:
                self._plot_pixel_heatmap(
                    df_local_ban=df, regionid=region_id_int, filename=filename
                )
            except Exception as e:
                logger.error(f"Failed to plot heatmap: {e}")
                return False

        return filename

    def _region_to_world_point(
        self, region_id: int, region_x: int, region_y: int, plane: int
    ):
        return (
            ((region_id >> 8) << 6) + region_x,
            ((region_id & 0xFF) << 6) + region_y,
            plane,
        )

    def _plot_heatmap(self, df_local_ban: pd.DataFrame, regionid: int, filename: str):
        origin_wp = self._region_to_world_point(regionid, 0, 0, 0)
        bounds_x = (origin_wp[0] - 0.5, origin_wp[0] + 63.5)
        bounds_y = (origin_wp[1] - 0.5, origin_wp[1] + 63.5)

        df_local_ban["confirmed_ban"] = df_local_ban["confirmed_ban"].apply(
            lambda x: math.log(x + 1)
        )

        map_img = PIL.Image.open(
            urllib.request.urlopen(
                f"https://raw.githubusercontent.com/Bot-detector/OSRS-Visible-Region-Images/main/Region_Maps/{regionid}.png"
            )
        )

        plt.style.use("seaborn-white")
        px = 1 / plt.rcParams["figure.dpi"]
        plt.subplots(figsize=(512 * px, 512 * px))
        plt.subplots_adjust(top=1, bottom=0, right=1, left=0, hspace=0, wspace=0)
        plt.margins(0, 0)
        plt.xlim(bounds_x)
        plt.ylim(bounds_y)
        plt.imshow(map_img, zorder=0, extent=[*bounds_x, *bounds_y])
        plt.axis("off")

        hmap = sns.kdeplot(
            data=df_local_ban,
            x="x_coord",
            y="y_coord",
            weights="confirmed_ban",
            gridsize=256,
            alpha=0.625,
            levels=256,
            antialiased=True,
            cmap="gnuplot_r",
            fill=True,
            bw_method=0.05,
        )
        hmap.legend(
            [f"Bot Detector Plugin: {date.today()}"],
            labelcolor="white",
            loc="lower right",
        )

        plt.savefig(filename, bbox_inches="tight", pad_inches=0)
        plt.figure().clear()
        plt.close("all")

    def _plot_pixel_heatmap(
        self, df_local_ban: pd.DataFrame, regionid: int, filename: str
    ):
        origin_wp = self._region_to_world_point(regionid, 0, 0, 0)
        df_local_ban["confirmed_ban"] = df_local_ban["confirmed_ban"].apply(
            lambda x: math.log(x + 1)
        )

        np_arr = np.empty((64, 64))
        np_arr[:] = np.nan
        for i, row in df_local_ban.iterrows():
            x_ind = int(row["x_coord"]) - origin_wp[0]
            y_ind = int(row["y_coord"]) - origin_wp[1]
            if 0 <= x_ind <= 63 and 0 <= y_ind <= 63:
                np_arr[y_ind, x_ind] = row["confirmed_ban"]

        map_img = PIL.Image.open(
            urllib.request.urlopen(
                f"https://raw.githubusercontent.com/Bot-detector/OSRS-Visible-Region-Images/main/Region_Maps/{regionid}.png"
            )
        )

        plt.style.use("seaborn-white")
        px = 1 / plt.rcParams["figure.dpi"]
        plt.subplots(figsize=(512 * px, 512 * px))
        plt.subplots_adjust(top=1, bottom=0, right=1, left=0, hspace=0, wspace=0)
        plt.margins(0, 0)
        plt.axis("off")

        hmap = sns.heatmap(
            data=np_arr, cmap="gnuplot_r", cbar=False, square=True, alpha=0.5
        )
        hmap.invert_yaxis()
        hmap.set_xlim([0, 64])
        hmap.set_ylim([0, 64])
        hmap.imshow(map_img, aspect=hmap.get_aspect(), extent=[0, 64, 0, 64], zorder=0)

        hmap.legend(
            [f"Bot Detector Plugin: {date.today()}"],
            labelcolor="white",
            loc="lower right",
        )

        plt.savefig(filename, bbox_inches="tight", pad_inches=0)
        plt.figure().clear()
        plt.close("all")

    def _display_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.drop_duplicates(subset=["region_name"], keep="first")

    def _clean_old_heatmaps(self, region_id: str):
        for file in os.listdir("."):
            if fnmatch.fnmatch(file, f"{region_id}*.png"):
                os.remove(file)

    def _heatmap_exists(self, filename: str) -> bool:
        return os.path.exists(filename)

    def _get_filename(self, region_id: str) -> str:
        date_str = date.today().strftime("%d-%m-%Y")
        return f"{region_id}_{date_str}.png"

    def _autofill(self, df_region: pd.DataFrame, region_name: str) -> tuple[str, int]:
        region_short = []
        name_index = df_region["region_name"].values
        location_index = df_region["region_ID"].values
        for i in name_index:
            region_short.append(len(i) - len(region_name))
        index = region_short.index(np.min(region_short))
        region_true_name = name_index[index]
        region_id = location_index[index]
        return region_true_name, region_id
