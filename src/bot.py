#!/usr/bin/env python3

"""Discord bot for organizing PUGs (pick-up games).
   Built for Neotokyo, but should work for any two-team game with even number
   of players total.

   Usage:
     Slash commands:
       - clearpuggers — Empty the PUG queue.
                        Command access can be restricted by role(s) with the
                        config value NTBOT_PUG_ADMIN_ROLES.

       - ping         — Bot will simply respond with "Pong". Use to test if
                        the bot is still online and responsive.

       - ping_puggers — Ping all the players currently in the PUG queue.
                        Can be used to manually organize games with smaller
                        than expected number of players. Expects a message
                        after the command, eg: "!ping_puggers Play 4v4?"

       - pug          — Join the PUG queue if there is room.

       - puggers      — List players currently in the PUG queue.

       - scramble     — Suggest randomly scrambled teams for the last full PUG
                        for balancing reasons. Can be repeated until a
                        satisfactory scramble is reached.

       - unpug        — Leave the PUG queue.

     Config values:
       The config values have been documented as comments in the config.yml
       file itself.

     For more information, please see the repository at:
       https://github.com/Rainyan/discord-bot-ntpug
"""

# MIT License
#
# Copyright (c) 2021- https://github.com/Rainyan and collaborators
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import asyncio
import random

import discord
from discord.ext import commands, tasks
import pendulum

from config import cfg
import database
import pugstatus
import bot_instance
from util import random_human_readable_phrase


assert discord.version_info.major == 2

SCRIPT_NAME = "NT Pug Bot for Discord"
SCRIPT_VERSION = "1.0.0"

assert bot_instance.BOT is None
INTENTS = discord.Intents.none()
INTENTS.guilds = True
INTENTS.guild_messages = True  # for legacy !commands
INTENTS.message_content = True  # for legacy !commands
bot_instance.BOT = commands.Bot(case_insensitive=True, intents=INTENTS)
assert bot_instance.BOT is not None


@bot_instance.BOT.event
async def on_message(msg):
    """Used to notify users of the ongoing migration to Discord slash commands
    """
    command_prefix = "!"
    # Testing if message starts with the command prefix explicitly,
    # because it allows us to quickly ignore most chat messages,
    # without having to execute the other code paths in this function at all.
    if msg.author.bot or not msg.content.startswith(command_prefix):
        return
    if msg.content == f"{command_prefix}ping":
        await msg.channel.send(f"{msg.author.mention} pong")
        return
    if msg.content == f"{command_prefix}help":
        await msg.channel.send(
            f"{msg.author.mention} If you need help for "
            "the PUG bot, please use `/pug help`, instead."
        )
        return
    if not any(
        (
            msg.content.startswith(command_prefix + x)
            for x in (
                "pug",
                "unpug",
                "puggers",
                "clearpuggers",
                "ping_puggers",
            )
        )
    ):
        return
    # TODO: add the help page
    # TODO: refactor into a command group, "/pug join", "/pug leave" etc.
    await msg.channel.send(
        f"{msg.author.mention} I am migrating to the new "
        "Discord slash command syntax; please use the "
        "new `/pug` command group, instead!\nFor more "
        "info, see the `/pug help` page."
    )


PUG_CHANNEL_NAME = cfg("NTBOT_PUG_CHANNEL")
BOT_SECRET_TOKEN = cfg("NTBOT_SECRET_TOKEN")
assert 0 <= cfg("NTBOT_PUGGER_ROLE_PING_THRESHOLD") <= 1
PUGGER_ROLE = cfg("NTBOT_PUGGER_ROLE")
assert len(PUGGER_ROLE) > 0

FIRST_TEAM_NAME = cfg("NTBOT_FIRST_TEAM_NAME")
SECOND_TEAM_NAME = cfg("NTBOT_SECOND_TEAM_NAME")

print(f"Now running {SCRIPT_NAME} v.{SCRIPT_VERSION}", flush=True)

pug_guilds: dict[discord.Guild, pugstatus.PugStatus] = {}


@bot_instance.BOT.slash_command(brief="Test if bot is active")
async def ping(ctx):
    """Just a standard Discord bot ping test command for confirming whether
    the bot is online or not.
    """
    await ctx.send_response("pong", ephemeral=True)


@bot_instance.BOT.slash_command(brief="Join the PUG queue")
async def pug(ctx):
    """Player command for joining the PUG queue."""

    print("Trying new db method:")
    async with database.DB(ctx.guild.id) as driver:
        res = await driver.get_discord_user(ctx.user.id)
        print(res)
    print("End of test")

    if not await is_pug_channel(ctx):
        return
    response = ""
    join_success, response = await pug_guilds[ctx.guild].player_join(ctx.user)
    if join_success:
        response = (
            f"{ctx.user.name} has joined the PUG queue "
            f"({pug_guilds[ctx.guild].num_queued} / "
            f"{pug_guilds[ctx.guild].num_expected})"
        )
    await ctx.send_response(
        content=response, ephemeral=cfg("NTBOT_EPHEMERAL_MESSAGES")
    )


@bot_instance.BOT.slash_command(brief="Leave the PUG queue")
async def unpug(ctx):
    """Player command for leaving the PUG queue."""
    if not await is_pug_channel(ctx):
        return

    leave_success, msg = await pug_guilds[ctx.guild].player_leave(ctx.user)
    if leave_success:
        msg = (
            f"{ctx.user.name} has left the PUG queue "
            f"({pug_guilds[ctx.guild].num_queued} / "
            f"{pug_guilds[ctx.guild].num_expected})"
        )
    await ctx.send_response(
        content=msg, ephemeral=cfg("NTBOT_EPHEMERAL_MESSAGES")
    )


@bot_instance.BOT.slash_command(brief="Empty the server's PUG queue")
async def clearpuggers(ctx):
    """Player command for clearing the PUG queue.
    This can be restricted to Discord guild specific admin roles.
    """
    if not await is_pug_channel(ctx):
        return

    # If zero pug admin roles are configured, assume anyone can !clearpuggers
    if len(cfg("NTBOT_PUG_ADMIN_ROLES")) == 0:
        is_allowed = True
    else:
        pug_admin_roles = [role.value for role in cfg("NTBOT_PUG_ADMIN_ROLES")]
        user_roles = [role.name for role in ctx.user.roles]
        is_allowed = any(role in pug_admin_roles for role in user_roles)

    if is_allowed:
        await pug_guilds[ctx.guild].reset()
        await ctx.respond(f"{ctx.user.name} has reset the PUG queue")
    else:
        await ctx.send_response(
            content=f"{ctx.user.mention} The PUG queue "
            "can only be reset by users with "
            f"role(s): _{pug_admin_roles}_",
            ephemeral=cfg("NTBOT_EPHEMERAL_MESSAGES"),
        )


@bot_instance.BOT.slash_command(
    brief="Get new random teams suggestion for " "the latest PUG"
)
async def scramble(ctx):
    """Player command for scrambling the latest full PUG queue.
    Can be called multiple times for generating new random teams.
    """
    if not await is_pug_channel(ctx):
        return
    msg = ""
    if len(pug_guilds[ctx.guild].prev_puggers) == 0:
        msg = f"{ctx.user.mention} Sorry, no previous PUG found to " "scramble"
    else:
        random.shuffle(pug_guilds[ctx.guild].prev_puggers)
        msg = f"{ctx.user.name} suggests scrambled teams:\n"
        msg += f"_(random shuffle id: {random_human_readable_phrase()})_\n"
        msg += "\n_" + FIRST_TEAM_NAME + " players:_\n"
        for i in range(int(len(pug_guilds[ctx.guild].prev_puggers) / 2)):
            msg += f"{pug_guilds[ctx.guild].prev_puggers[i].name}, "
        msg = msg[:-2]  # trailing ", "
        msg += "\n_" + SECOND_TEAM_NAME + " players:_\n"
        for i in range(
            int(len(pug_guilds[ctx.guild].prev_puggers) / 2),
            len(pug_guilds[ctx.guild].prev_puggers),
        ):
            msg += f"{pug_guilds[ctx.guild].prev_puggers[i].name}, "
        msg = msg[:-2]  # trailing ", "
        msg += (
            "\n\nTeams still unbalanced? Use "
            "`/scramble` to suggest new random teams."
        )
    await ctx.respond(msg)


@bot_instance.BOT.slash_command(
    brief="List players currently queueing for " "PUG"
)
async def puggers(ctx):
    """Player command for listing players currently in the PUG queue."""
    msg = (
        f"{pug_guilds[ctx.guild].num_queued} / "
        f"{pug_guilds[ctx.guild].num_expected} player(s) currently "
        "queued"
    )

    if pug_guilds[ctx.guild].num_queued > 0:
        all_players_queued = (
            pug_guilds[ctx.guild].team1_players
            + pug_guilds[ctx.guild].team2_players
        )
        msg += ": "
        for player in all_players_queued:
            msg += f"{player.name}, "
        msg = msg[:-2]  # trailing ", "
    # Respond ephemerally if we aren't in a PUG channel context.
    in_pug_channel = await is_pug_channel(ctx, respond=False)
    await ctx.send_response(
        content=msg,
        ephemeral=((not in_pug_channel) or cfg("NTBOT_EPHEMERAL_MESSAGES")),
    )


async def is_pug_channel(ctx, respond=True):
    """Returns whether the PUG bot should respond in this channel."""
    if ctx.guild not in pug_guilds or ctx.channel.name != PUG_CHANNEL_NAME:
        if respond:
            await ctx.send_response(
                content=f"Sorry, this command can only be "
                "used on the channel: "
                f"_{PUG_CHANNEL_NAME}_",
                ephemeral=True,
            )
        return False
    return True


@commands.cooldown(
    rate=1,
    per=cfg("NTBOT_PING_PUGGERS_COOLDOWN_SECS"),
    type=commands.BucketType.user,
)
@bot_instance.BOT.slash_command(
    brief="Ping all players currently queueing " "for PUG"
)
# pylint: disable=no-member
async def ping_puggers(
    ctx: discord.ext.commands.Context, message_to_other_players: str
):
    """Player command to ping all players currently inside the PUG queue."""
    if not await is_pug_channel(ctx):
        # Don't set cooldown for failed invocations
        ping_puggers.reset_cooldown(ctx)
        return

    pug_admin_roles = [role.value for role in cfg("NTBOT_PUG_ADMIN_ROLES")]
    user_roles = [role.name for role in ctx.author.roles]
    is_admin = any(role in pug_admin_roles for role in user_roles)

    # Only admins and players in the queue themselves are allowed to ping queue
    if not is_admin:
        if ctx.user not in (
            pug_guilds[ctx.guild].team1_players
            + pug_guilds[ctx.guild].team2_players
        ):
            if pug_guilds[ctx.guild].num_queued == 0:
                await ctx.respond(
                    f"{ctx.user.mention} PUG queue is currently " "empty."
                )
            else:
                await ctx.respond(
                    f"{ctx.user.mention} Sorry, to be able to "
                    "ping the PUG queue, you have to be queued "
                    "yourself, or have the role(s): "
                    f"_{pug_admin_roles}_"
                )
            ping_puggers.reset_cooldown(ctx)
            return

    async with pug_guilds[ctx.guild].lock:
        # Comparing <=1 instead of 0 because it makes no sense to ping others
        # if you're the only one currently in the queue.
        if pug_guilds[ctx.guild].num_queued <= 1:
            await ctx.respond(
                f"{ctx.user.mention} There are no other players "
                "in the queue to ping!"
            )
            ping_puggers.reset_cooldown(ctx)
            return

    msg = ""
    async with pug_guilds[ctx.guild].lock:
        for player in [
            p for p in pug_guilds[ctx.guild].team1_players if p != ctx.user
        ]:
            msg += f"{player.mention}, "
        for player in [
            p for p in pug_guilds[ctx.guild].team2_players if p != ctx.user
        ]:
            msg += f"{player.mention}, "
        msg = msg[:-2]  # trailing ", "
    message_to_other_players = message_to_other_players.replace("`", "")
    message_to_other_players = discord.utils.escape_markdown(
        message_to_other_players, ignore_links=False
    )
    msg += (
        f" User {ctx.user.mention} is pinging the PUG queue with "
        "message:\n"
        f"```{message_to_other_players}```"
    )
    # No cooldown for admin pings.
    if is_admin:
        ping_puggers.reset_cooldown(ctx)
    await ctx.respond(msg)


class ErrorHandlerCog(commands.Cog):
    """Helper class for error handling."""

    def __init__(self, parent_bot):
        self.bot = parent_bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx, err):
        """Error handler for bot commands."""
        # This could be a typo, or a command meant for another bot.
        if isinstance(err, discord.ext.commands.errors.CommandNotFound):
            print(f'Ignoring unknown command: "{ctx.message.content}"')
            return
        # This command is on cooldown from being used too often.
        if isinstance(err, discord.ext.commands.errors.CommandOnCooldown):
            # Returns a human readable "<so and so long> before" string.
            retry_after = pendulum.now().diff_for_humans(
                pendulum.now().add(seconds=err.retry_after)
            )
            await ctx.send(
                f"{ctx.message.author.mention} You're doing it too "
                f"much! Please wait {retry_after} trying again."
            )
            return
        # Something else happened! Just raise the error for the logs to catch.
        raise err


class PugQueueCog(commands.Cog):
    """PUG queue main event loop."""

    def __init__(self, parent_bot):
        """Acquire lock for asynchronous queue polling,
        and start the queue loop.
        """
        # pylint: disable=no-member
        self.bot = parent_bot
        self.lock = asyncio.Lock()
        self.poll_queue.start()
        self.clear_inactive_puggers.start()

    @tasks.loop(seconds=cfg("NTBOT_POLLING_INTERVAL_SECS"))
    async def poll_queue(self):
        """Poll the PUG queue to see if we're ready to play,
        and to possibly update our status in various ways.

        Iterating and caching per-guild to support multiple Discord
        channels simultaneously using the same bot instance with their
        own independent player pools.
        """
        async with self.lock:
            for guild in self.bot.guilds:
                for channel in guild.channels:
                    if channel.name != PUG_CHANNEL_NAME:
                        continue
                    if guild not in pug_guilds:
                        pug_guilds[guild] = pugstatus.PugStatus(
                            guild_channel=channel, guild_roles=guild.roles
                        )
                        await pug_guilds[guild].reload_puggers()
                    if pug_guilds[guild].is_full:
                        pug_start_success, msg = await pug_guilds[
                            guild
                        ].start_pug()
                        if pug_start_success:
                            # Before starting pug and resetting queue, manually
                            # update presence, so we're guaranteed to have the
                            # presence status fully up-to-date here.
                            pug_guilds[guild].last_changed_presence = 0
                            await pug_guilds[guild].update_presence()
                            # Ping the puggers
                            await channel.send(msg)
                            # And finally reset the queue, so we're ready for
                            # the next PUGs.
                            await pug_guilds[guild].reset()
                    else:
                        await pug_guilds[guild].update_presence()
                        await pug_guilds[guild].ping_role()

    @tasks.loop(hours=(cfg("NTBOT_IDLE_THRESHOLD_HOURS") / 2))
    async def clear_inactive_puggers(self):
        """Periodically clear inactive puggers from the queue(s)."""
        async with self.lock:
            for guild in self.bot.guilds:
                if guild not in pug_guilds:
                    continue
                if pug_guilds[guild].is_full:
                    continue
                for channel in guild.channels:
                    if channel.name != PUG_CHANNEL_NAME:
                        continue
                    await pug_guilds[guild].reload_puggers()
                    break


for cog in (ErrorHandlerCog, PugQueueCog):
    bot_instance.BOT.add_cog(cog(bot_instance.BOT))

if cfg("NTBOT_DEBUG"):
    print(f"Intents ({bot_instance.BOT.intents}):")
    for intent, enabled in iter(bot_instance.BOT.intents):
        if enabled:
            print(f"* {intent}")

bot_instance.BOT.run(BOT_SECRET_TOKEN)
