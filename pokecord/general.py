import asyncio
import json
import urllib

import discord
import tabulate
from redbot.core import commands
from redbot.core.utils.chat_formatting import *
from redbot.core.utils.menus import (
    DEFAULT_CONTROLS,
    close_menu,
    menu,
    next_page,
    prev_page,
)
from redbot.core.utils.predicates import MessagePredicate

from .abc import MixinMeta
from .functions import select_pokemon
from .statements import *

controls = {
    "⬅": prev_page,
    "❌": close_menu,
    "➡": next_page,
    "\N{WHITE HEAVY CHECK MARK}": select_pokemon,
}


class GeneralMixin(MixinMeta):
    """Pokecord General Commands"""

    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.command()
    async def list(self, ctx, user: discord.Member = None):
        """List a trainers or your own pokémon!"""
        user = user or ctx.author
        conf = await self.user_is_global(user)
        result = self.cursor.execute(SELECT_POKEMON, (user.id,)).fetchall()
        pokemons = []
        for data in result:
            pokemons.append(json.loads(data[0]))
        if not pokemons:
            return await ctx.send(
                "You don't have any pokémon, go get catching trainer!"
            )
        embeds = []
        for i, pokemon in enumerate(pokemons, 1):
            stats = pokemon["stats"]
            pokestats = tabulate.tabulate(
                [
                    ["HP", stats["HP"]],
                    ["Attack", stats["Attack"]],
                    ["Defence", stats["Defence"]],
                    ["Sp. Atk", stats["Sp. Atk"]],
                    ["Sp. Def", stats["Sp. Def"]],
                    ["Speed", stats["Speed"]],
                ],
                headers=["Ability", "Value"],
            )
            nick = pokemon.get("nickname")
            alias = f"**Nickname**: {nick}\n" if nick is not None else ""
            desc = f"{alias}**Level**: {pokemon['level']}\n**XP**: {pokemon['xp']}/{self.calc_xp(pokemon['level'])}\n{box(pokestats, lang='prolog')}"
            embed = discord.Embed(
                title=self.get_name(pokemon["name"], user), description=desc
            )
            if pokemon.get("id"):
                embed.set_thumbnail(
                    url=f"https://assets.pokemon.com/assets/cms2/img/pokedex/detail/{str(pokemon['id']).zfill(3)}.png"
                )
            embed.set_footer(text=f"Pokémon ID: {i}/{len(pokemons)}")
            embeds.append(embed)
        await menu(ctx, embeds, DEFAULT_CONTROLS if user != ctx.author else controls)

    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.command()
    async def nick(self, ctx, id: int, *, nickname: str):
        """Set a pokemons nickname."""
        if id <= 0:
            return await ctx.send("The ID must be greater than 0!")
        result = self.cursor.execute(SELECT_POKEMON, (ctx.author.id,),).fetchall()
        pokemons = [None]
        for data in result:
            pokemons.append([json.loads(data[0]), data[1]])
        if not pokemons:
            return await ctx.send("You don't have any pokémon, trainer!")
        if id > len(pokemons):
            return await ctx.send("You don't have a pokemon at that slot.")
        pokemon = pokemons[id]
        pokemon[0]["nickname"] = nickname
        self.cursor.execute(
            UPDATE_POKEMON, (ctx.author.id, pokemon[1], json.dumps(pokemon[0])),
        )
        await ctx.send(f"Your {pokemon[0]['name']} has been named `{nickname}`")

    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.command()
    async def free(self, ctx, id: int):
        """Free a pokemon."""
        if id <= 0:
            return await ctx.send("The ID must be greater than 0!")
        result = self.cursor.execute(SELECT_POKEMON, (ctx.author.id,),).fetchall()
        pokemons = [None]
        for data in result:
            pokemons.append([json.loads(data[0]), data[1]])
        if not pokemons:
            return await ctx.send("You don't have any pokémon, trainer!")
        if id >= len(pokemons):
            return await ctx.send("You don't have a pokemon at that slot.")
        pokemon = pokemons[id]
        name = self.get_name(pokemon[0]["name"], ctx.author)
        await ctx.send(
            f"You are about to free {name}, if you wish to continue type `yes`, otherwise type `no`."
        )
        try:
            pred = MessagePredicate.yes_or_no(ctx, user=ctx.author)
            await ctx.bot.wait_for("message", check=pred, timeout=20)
        except asyncio.TimeoutError:
            await ctx.send("Exiting operation.")
            return

        if pred.result:
            msg = ""
            userconf = await self.user_is_global(ctx.author)
            pokeid = await userconf.pokeid()
            if id < pokeid:
                msg += "\nYour default pokemon may have changed. I have tried to account for this change."
            elif id == pokeid:
                msg += "\nYou have released your selected pokemon. I have reset your selected pokemon to your first pokemon."
                await userconf.pokeid.set(1)
            self.cursor.execute(
                "DELETE FROM users where message_id = ?", (pokemon[1],),
            )
            await ctx.send(f"Your {name} has been freed.{msg}")
        else:
            await ctx.send("Operation cancelled.")

    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.command(usage="id_or_latest")
    @commands.guild_only()
    async def select(self, ctx, _id: Union[int, str]):
        """Select your default pokémon."""
        conf = await self.user_is_global(ctx.author)
        if not await conf.has_starter():
            return await ctx.send(
                f"You haven't chosen a starter pokemon yet, check out `{ctx.clean_prefix}starter` for more information."
            )
        result = self.cursor.execute(
            """SELECT pokemon, message_id from users where user_id = ?""",
            (ctx.author.id,),
        ).fetchall()
        pokemons = [None]
        for data in result:
            pokemons.append([json.loads(data[0]), data[1]])
        if not pokemons:
            return await ctx.send("You don't have any pokemon to select.")
        if isinstance(_id, str):
            if _id == "latest":
                _id = len(pokemons) - 1
            else:
                await ctx.send(
                    "Unidentified keyword, the only supported action is `latest` as of now."
                )
                return
        if _id < 1 or _id > len(pokemons) - 1:
            return await ctx.send("You've specified an invalid ID.")
        await ctx.send(
            f"You have selected {self.get_name(pokemons[_id][0]['name'], ctx.author)} as your default pokémon."
        )
        conf = await self.user_is_global(ctx.author)
        await conf.pokeid.set(_id)
        await self.update_user_cache()