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
# Copyright (c) 2021- https://github.com/Rainyan
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

from ast import literal_eval
import asyncio
from datetime import datetime, timedelta, timezone
import inspect
import os
import time
import random

import discord
from discord.ext import commands, tasks
import pendulum
from strictyaml import (as_document, load, Bool, EmptyList, Float, Int, Map,
                        Seq, Str)

assert discord.version_info.major == 2

SCRIPT_NAME = "NT Pug Bot"
SCRIPT_VERSION = "1.0.0"


class PredicatedInt(Int):
    """StrictYAML Int validator, with optional predicates."""
    def __init__(self, predicates = None):
        self.predicates = predicates if predicates is not None else []

    def validate_scalar(self, chunk):
        val = super().validate_scalar(chunk)
        for pred in self.predicates:
            if not pred(val):
                chunk.expecting_but_found(str(inspect.getsourcelines(pred)[0]))
        return val


# The schema used for StrictYAML parsing.
YAML_CFG_SCHEMA = {
    "NTBOT_SECRET_TOKEN": Str(),
    "NTBOT_PUG_CHANNEL": Str(),
    "NTBOT_PLAYERS_REQUIRED_TOTAL": PredicatedInt([lambda x: x > 0,
                                                   lambda x: x % 2 == 0]),
    "NTBOT_DEBUG_ALLOW_REQUEUE": Bool(),
    "NTBOT_POLLING_INTERVAL_SECS": Int(),
    "NTBOT_PRESENCE_INTERVAL_SECS": Int(),
    "NTBOT_PUGGER_ROLE": Str(),
    "NTBOT_PUGGER_ROLE_PING_THRESHOLD": Float(),
    "NTBOT_PUGGER_ROLE_PING_MIN_INTERVAL_HOURS": Float(),
    "NTBOT_PUG_ADMIN_ROLES": Seq(Str()) | EmptyList(),
    "NTBOT_IDLE_THRESHOLD_HOURS": Float(),
    "NTBOT_PING_PUGGERS_COOLDOWN_SECS": Float(),
    "NTBOT_FIRST_TEAM_NAME": Str(),
    "NTBOT_SECOND_TEAM_NAME": Str(),
    "NTBOT_EPHEMERAL_MESSAGES": Bool(),
}

CFG_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                        "config.yml")
assert os.path.isfile(CFG_PATH)
with open(file=CFG_PATH, mode="r", encoding="utf-8") as f_config:
    CFG = load(f_config.read(), Map(YAML_CFG_SCHEMA))
assert CFG is not None


def cfg(key):
    """Returns a bot config value from environment variable or config file,
       in that order. If using an env var, its format has to match the type
       determined by the config values' StrictYAML schema.
    """
    assert isinstance(key, str)
    if os.environ.get(key):
        expected_ret_type = YAML_CFG_SCHEMA[key]
        # Small placeholder schema used for validating just this type.
        # We don't want to use the main schema because then we'd need
        # to populate it entirely, even though we're only interested
        # in returning this particular var.
        mini_schema = {key: expected_ret_type}
        # Generate StrictYAML in-place, with the mini-schema to enforce
        # strict typing, and then return the queried key's value.
        return as_document({key: literal_eval(os.environ.get(key))},
                           Map(mini_schema))[key].value
    return CFG[key].value


bot = commands.Bot(case_insensitive=True)
NUM_PLAYERS_REQUIRED = cfg("NTBOT_PLAYERS_REQUIRED_TOTAL")
DEBUG_ALLOW_REQUEUE = cfg("NTBOT_DEBUG_ALLOW_REQUEUE")
PUG_CHANNEL_NAME = cfg("NTBOT_PUG_CHANNEL")
BOT_SECRET_TOKEN = cfg("NTBOT_SECRET_TOKEN")
assert 0 <= cfg("NTBOT_PUGGER_ROLE_PING_THRESHOLD") <= 1
PUGGER_ROLE = cfg("NTBOT_PUGGER_ROLE")
assert len(PUGGER_ROLE) > 0

FIRST_TEAM_NAME = cfg("NTBOT_FIRST_TEAM_NAME")
SECOND_TEAM_NAME = cfg("NTBOT_SECOND_TEAM_NAME")

# This is a variable because the text is used for detecting previous PUGs
# when restoring status during restart.
PUG_READY_TITLE = "**PUG is now ready!**"

print(f"Now running {SCRIPT_NAME} v.{SCRIPT_VERSION}", flush=True)


class PugStatus():
    """Object for containing and operating on one Discord server's PUG
       information.
    """
    # pylint: disable=too-many-instance-attributes
    # This might need revisiting, but deal with it for now.
    def __init__(self, guild_channel, players_required=NUM_PLAYERS_REQUIRED,
                 guild_roles=None):
        self.guild_roles = [] if guild_roles is None else guild_roles
        self.guild_channel = guild_channel
        self.team1_players = []
        self.team2_players = []
        self.prev_puggers = []
        self.players_required_total = players_required
        assert self.players_required_total >= 2
        assert self.players_required_total % 2 == 0
        self.last_changed_presence = 0
        self.last_presence = None
        self.lock = asyncio.Lock()

    async def reset(self):
        """Stores the previous puggers, and then resets current pugger queue.
        """
        async with self.lock:
            self.prev_puggers = self.team1_players + self.team2_players
            self.team1_players.clear()
            self.team2_players.clear()

    async def player_join(self, player, team=None):
        """If there is enough room in this PUG queue, assigns this player
           to a random team to wait in, until the PUG is ready to be started.
           The specific team rosters can later be shuffled by a !scramble.
        """
        async with self.lock:
            if not DEBUG_ALLOW_REQUEUE and \
                    (player in self.team1_players or
                     player in self.team2_players):
                return False, (f"{player.mention} You are already queued! "
                               "If you wanted to un-PUG, please use **"
                               f"{bot.command_prefix}unpug** "
                               "instead.")
            if team is None:
                team = random.randint(0, 1)  # flip a coin between team1/team2
            if team == 0:
                if len(self.team1_players) < self.players_per_team:
                    self.team1_players.append(player)
                    return True, ""
            if len(self.team2_players) < self.players_per_team:
                self.team2_players.append(player)
                return True, ""
            return False, (f"{player.mention} Sorry, this PUG is currently "
                           "full!")

    async def reload_puggers(self):
        """Iterate PUG channel's recent message history to figure out who
           should be pugged. This is used both for restoring puggers after a
           bot restart, but also for dropping inactive players from the queue
           after inactivity of "NTBOT_IDLE_THRESHOLD_HOURS" period.
        """
        limit_hrs = cfg("NTBOT_IDLE_THRESHOLD_HOURS")
        assert limit_hrs > 0
        after = datetime.now() - timedelta(hours=limit_hrs)

        def is_cmd(msg, cmd):
            """Predicate for whether message equals a specific PUG command.
            """
            return msg.content == f"{bot.command_prefix}{cmd}"

        def is_pug_reset(msg):
            """Predicate for whether a message signals PUG reset.
            """
            return (msg.author.bot and
                    msg.content.endswith("has reset the PUG queue"))

        def is_pug_start(msg):
            """Predicate for whether a message signals PUG start.
            """
            return msg.author.bot and msg.content.startswith(PUG_READY_TITLE)

        backup_team2 = self.team2_players.copy()
        backup_team1 = self.team1_players.copy()
        backup_prev = self.prev_puggers.copy()
        try:
            # First reset the PUG queue, and then replay the pug/unpug traffic
            # within the acceptable "restore_puggers_limit_hours" history range
            await self.reset()
            # We remove the default max retrieved messages history limit
            # because we need to always retrieve the full order of events here.
            # This can be a slow operation if the channel is heavily congested
            # within the "now-after" search range, but it's acceptable here
            # because this code only runs on bot init, and then once per
            # clear_inactive_puggers() task loop period, which is at most once
            # per hour.
            async for msg in self.guild_channel.history(limit=None,
                                                        after=after,
                                                        oldest_first=True).\
                    filter(lambda msg: any((is_cmd(msg, "pug"),
                                            is_cmd(msg, "unpug"),
                                            is_pug_reset(msg),
                                            is_pug_start(msg)))):
                if is_pug_reset(msg) or is_pug_start(msg):
                    await self.reset()
                elif is_cmd(msg, "pug"):
                    await self.player_join(msg.author)
                else:
                    await self.player_leave(msg.author)
        # Discord frequently HTTP 500's, so need to have pug queue backups.
        # We can also hit a HTTP 429 here, which might be a pycord bug(?)
        # as I don't think we're being unreasonable with the history range.
        except discord.errors.HTTPException as err:
            self.team2_players = backup_team2.copy()
            self.team1_players = backup_team1.copy()
            self.prev_puggers = backup_prev.copy()
            raise err

    async def player_leave(self, player):
        """Removes a player from the pugger queue if they were in it.
        """
        async with self.lock:
            num_before = self.num_queued
            self.team1_players = [p for p in self.team1_players if p != player]
            self.team2_players = [p for p in self.team2_players if p != player]
            num_after = self.num_queued

            left_queue = (num_after != num_before)
            if left_queue:
                return True, ""
            return False, (f"{player.mention} You are not currently in the "
                           "PUG queue")

    @property
    def num_queued(self):
        """Returns the number of puggers currently in the PUG queue.
        """
        return len(self.team1_players) + len(self.team2_players)

    @property
    def num_expected(self):
        """Returns the number of puggers expected, total, to start a PUG.
        """
        return self.players_required_total

    @property
    def players_per_team(self):
        """Players required to start a PUG, per team."""
        res = self.num_expected / 2
        assert res % 1 == 0, "Must be whole number"
        return int(res)

    @property
    def num_more_needed(self):
        """Returns how many more puggers are needed to start a PUG.
        """
        return max(0, self.num_expected - self.num_queued)

    @property
    def is_full(self):
        """Whether the PUG queue is currently full or not."""
        return self.num_queued >= self.num_expected

    async def start_pug(self):
        """Starts a PUG match.
        """
        async with self.lock:
            if len(self.team1_players) == 0 or len(self.team2_players) == 0:
                await self.reset()
                return False, "Error: team was empty"
            msg = f"{PUG_READY_TITLE}\n"
            msg += "\n_" + FIRST_TEAM_NAME + " players:_\n"
            for player in self.team1_players:
                msg += f"{player.mention}, "
            msg = msg[:-2]  # trailing ", "
            msg += "\n_" + SECOND_TEAM_NAME + " players:_\n"
            for player in self.team2_players:
                msg += f"{player.mention}, "
            msg = msg[:-2]  # trailing ", "
            msg += ("\n\nTeams unbalanced? Use **"
                    f"{bot.command_prefix}scramble** to suggest new "
                    "random teams.")
            return True, msg

    async def update_presence(self):
        """Updates the bot's status message ("presence").
           This is used for displaying things like the PUG queue status.
        """
        async with self.lock:
            delta_time = int(time.time()) - self.last_changed_presence

            if delta_time < cfg("NTBOT_PRESENCE_INTERVAL_SECS") + 2:
                return

            presence = self.last_presence
            if presence is None:
                presence = {
                    "activity": discord.BaseActivity(),
                    "status": discord.Status.idle
                }

            puggers_needed = self.num_more_needed

            # Need to keep flipping status because activity update in itself
            # doesn't seem to propagate that well.
            status = discord.Status.idle
            if presence["status"] == status:
                status = discord.Status.online
            if puggers_needed > 0:
                text = f"for {puggers_needed} more pugger"
                if puggers_needed > 1:
                    text += "s"  # plural
                else:
                    text += "!"  # need one more!
                activity = discord.Activity(type=discord.ActivityType.watching,
                                            name=text)
            else:
                text = "a PUG! 🐩"
                activity = discord.Activity(type=discord.ActivityType.playing,
                                            name=text)

            presence["activity"] = activity
            presence["status"] = status

            await bot.change_presence(activity=presence["activity"],
                                      status=presence["status"])
            self.last_presence = presence
            self.last_changed_presence = int(time.time())

    async def role_ping_deltatime(self):
        """Returns a datetime.timedelta of latest role ping, or None if no such
           ping was found.
        """
        after = datetime.now() - timedelta(
            hours=cfg("NTBOT_PUGGER_ROLE_PING_MIN_INTERVAL_HOURS"))
        try:
            async for msg in self.guild_channel.history(limit=None,
                                                        after=after,
                                                        oldest_first=False).\
                    filter(lambda msg: PUGGER_ROLE in [role.name for role in
                                                       msg.role_mentions]):
                return datetime.now(timezone.utc) - msg.created_at
        except discord.errors.HTTPException as err:
            # If it's not a library error, and we got a HTTP 5xx response,
            # err on the side of caution and treat it as if we found a recent
            # ping by returning a zeroed timedelta, so that the bot will try
            # again later. The Discord API throws server side HTTP 5xx errors
            # pretty much daily, so silently ignoring them here keeps the bot
            # side error logs cleaner since the Discord bugs aren't really
            # actionable for us as the API user.
            if err.code == 0 and str(err.status)[:1] == "5":
                return timedelta()
            raise err
        return None

    async def ping_role(self):
        """Pings the puggers Discord server role, if it's currently allowed.
           Frequency of these pings is restricted to avoid being too spammy.
        """
        async with self.lock:
            if self.num_more_needed == 0:
                return

            pugger_ratio = self.num_queued / self.num_expected
            ping_ratio = cfg("NTBOT_PUGGER_ROLE_PING_THRESHOLD")
            if pugger_ratio < ping_ratio:
                return

            last_ping_dt = await self.role_ping_deltatime()
            hours_limit = cfg("NTBOT_PUGGER_ROLE_PING_MIN_INTERVAL_HOURS")
            if last_ping_dt is not None:
                last_ping_hours = last_ping_dt.total_seconds() / 60 / 60
                if last_ping_hours < hours_limit:
                    return

            for role in self.guild_roles:
                if role.name == PUGGER_ROLE:
                    min_nag_hours = f"{hours_limit:.1f}"
                    min_nag_hours = min_nag_hours.rstrip("0").rstrip(".")
                    msg = (f"{role.mention} Need **"
                           f"{self.num_more_needed} more puggers** "
                           "for a game!\n_(This is an automatic ping "
                           "to all puggers, because the PUG queue is "
                           f"{(ping_ratio * 100):.0f}% full.\nRest "
                           "assured, I will only ping you once per "
                           f"{min_nag_hours} hours, at most.\n"
                           "If you don't want any of these "
                           "notifications, please consider "
                           "temporarily muting this bot or leaving "
                           f"the {role.mention} server role._)")
                    await self.guild_channel.send(msg)
                    break


pug_guilds = {}


@bot.slash_command(brief="Test if bot is active")
async def ping(ctx):
    """Just a standard Discord bot ping test command for confirming whether
       the bot is online or not.
    """
    await ctx.send_response("pong", ephemeral=True)


@bot.slash_command(brief="Join the PUG queue")
async def pug(ctx):
    """Player command for joining the PUG queue."""
    if not await is_pug_channel(ctx):
        return
    response = ""
    join_success, response = await pug_guilds[ctx.guild].player_join(
        ctx.user)
    if join_success:
        response = (f"{ctx.user.name} has joined the PUG queue "
                    f"({pug_guilds[ctx.guild].num_queued} / "
                    f"{pug_guilds[ctx.guild].num_expected})")
    await ctx.send_response(content=response,
                            ephemeral=cfg("NTBOT_EPHEMERAL_MESSAGES"))


@bot.slash_command(brief="Leave the PUG queue")
async def unpug(ctx):
    """Player command for leaving the PUG queue.
    """
    if not await is_pug_channel(ctx):
        return

    leave_success, msg = await pug_guilds[ctx.guild].player_leave(
        ctx.user)
    if leave_success:
        msg = (f"{ctx.user.name} has left the PUG queue "
               f"({pug_guilds[ctx.guild].num_queued} / "
               f"{pug_guilds[ctx.guild].num_expected})")
    await ctx.send_response(content=msg,
                            ephemeral=cfg("NTBOT_EPHEMERAL_MESSAGES"))


@bot.slash_command(brief="Empty the server's PUG queue")
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
        await ctx.send_response(content=f"{ctx.user.mention} The PUG queue "
                                        "can only be reset by users with "
                                        f"role(s): _{pug_admin_roles}_",
                                ephemeral=cfg("NTBOT_EPHEMERAL_MESSAGES"))


@bot.slash_command(brief="Get new random teams suggestion for the latest PUG")
async def scramble(ctx):
    """Player command for scrambling the latest full PUG queue.
       Can be called multiple times for generating new random teams.
    """
    if not await is_pug_channel(ctx):
        return
    msg = ""
    if len(pug_guilds[ctx.guild].prev_puggers) == 0:
        msg = (f"{ctx.user.mention} Sorry, no previous PUG found to "
               "scramble")
    else:
        random.shuffle(pug_guilds[ctx.guild].prev_puggers)
        msg = f"{ctx.user.name} suggests scrambled teams:\n"
        msg += f"_(random shuffle id: {random_human_readable_phrase()})_\n"
        msg += "\n_" + FIRST_TEAM_NAME + " players:_\n"
        for i in range(int(len(pug_guilds[ctx.guild].prev_puggers) / 2)):
            msg += f"{pug_guilds[ctx.guild].prev_puggers[i].name}, "
        msg = msg[:-2]  # trailing ", "
        msg += "\n_" + SECOND_TEAM_NAME + " players:_\n"
        for i in range(int(len(pug_guilds[ctx.guild].prev_puggers) / 2),
                       len(pug_guilds[ctx.guild].prev_puggers)):
            msg += f"{pug_guilds[ctx.guild].prev_puggers[i].name}, "
        msg = msg[:-2]  # trailing ", "
        msg += ("\n\nTeams still unbalanced? Use **"
                f"{bot.command_prefix}scramble** to suggest new random teams.")
    await ctx.respond(msg)


@bot.slash_command(brief="List players currently queueing for PUG")
async def puggers(ctx):
    """Player command for listing players currently in the PUG queue.
    """
    msg = (f"{pug_guilds[ctx.guild].num_queued} / "
           f"{pug_guilds[ctx.guild].num_expected} player(s) currently "
           "queued")

    if pug_guilds[ctx.guild].num_queued > 0:
        all_players_queued = pug_guilds[ctx.guild].team1_players + \
            pug_guilds[ctx.guild].team2_players
        msg += ": "
        for player in all_players_queued:
            msg += f"{player.name}, "
        msg = msg[:-2]  # trailing ", "
    # Respond ephemerally" if we aren't in a PUG channel context.
    in_pug_channel = await is_pug_channel(ctx, respond=False)
    await ctx.send_response(content=msg,
                            ephemeral=((not in_pug_channel) or
                                       cfg("NTBOT_EPHEMERAL_MESSAGES")))


async def is_pug_channel(ctx, respond=True):
    """Returns whether the PUG bot should respond in this channel."""
    if ctx.guild not in pug_guilds or ctx.channel.name != PUG_CHANNEL_NAME:
        if respond:
            await ctx.send_response(content=f"Sorry, this command can only be "
                                            "used on the channel: "
                                            f"_{PUG_CHANNEL_NAME}_",
                                    ephemeral=True)
        return False
    return True


@commands.cooldown(rate=1, per=cfg("NTBOT_PING_PUGGERS_COOLDOWN_SECS"),
                   type=commands.BucketType.user)
@bot.slash_command(brief="Ping all players currently queueing for PUG")
# pylint: disable=no-member
async def ping_puggers(ctx, message_to_other_players: discord.Option(str)):
    """Player command to ping all players currently inside the PUG queue.
    """
    if not await is_pug_channel(ctx):
        # Don't set cooldown for failed invocations
        ping_puggers.reset_cooldown(ctx)
        return

    pug_admin_roles = [role.value for role in cfg("NTBOT_PUG_ADMIN_ROLES")]
    user_roles = [role.name for role in ctx.author.roles]
    is_admin = any(role in pug_admin_roles for role in user_roles)

    # Only admins and players in the queue themselves are allowed to ping queue
    if not is_admin:
        if ctx.user not in (pug_guilds[ctx.guild].team1_players +
                            pug_guilds[ctx.guild].team2_players):
            if pug_guilds[ctx.guild].num_queued == 0:
                await ctx.respond(f"{ctx.user.mention} PUG queue is currently "
                                  "empty.")
            else:
                await ctx.respond(f"{ctx.user.mention} Sorry, to be able to "
                                  "ping the PUG queue, you have to be queued "
                                  "yourself, or have the role(s): "
                                  f"_{pug_admin_roles}_")
            ping_puggers.reset_cooldown(ctx)
            return

    async with pug_guilds[ctx.guild].lock:
        # Comparing <=1 instead of 0 because it makes no sense to ping others
        # if you're the only one currently in the queue.
        if pug_guilds[ctx.guild].num_queued <= 1:
            await ctx.respond(f"{ctx.user.mention} There are no other players "
                              "in the queue to ping!")
            ping_puggers.reset_cooldown(ctx)
            return

    msg = ""
    async with pug_guilds[ctx.guild].lock:
        for player in [p for p in pug_guilds[ctx.guild].team1_players
                       if p != ctx.user]:
            msg += f"{player.mention}, "
        for player in [p for p in pug_guilds[ctx.guild].team2_players
                       if p != ctx.user]:
            msg += f"{player.mention}, "
        msg = msg[:-2]  # trailing ", "
    message_to_other_players = message_to_other_players.replace("`", "")
    message_to_other_players = discord.utils.escape_markdown(
            message_to_other_players,
            ignore_links=False)
    msg += (f" User {ctx.user.mention} is pinging the PUG queue with "
            "message:\n"
            f"```{message_to_other_players}```")
    # No cooldown for admin pings.
    if is_admin:
        ping_puggers.reset_cooldown(ctx)
    await ctx.respond(msg)


def random_human_readable_phrase():
    """Generates a random human readable phrase to work as an identifier.
       Can be used for the !scrambles, to make it easier for players to refer
       to specific scramble permutations via voice chat by using these phrases.
    """
    base_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                             "static", "phrase_gen")
    with open(file=os.path.join(base_path, "nouns.txt"), mode="r",
              encoding="utf-8") as f_nouns:
        nouns = f_nouns.readlines()
    with open(file=os.path.join(base_path, "adjectives.txt"), mode="r",
              encoding="utf-8") as f_adjs:
        adjectives = f_adjs.readlines()
    phrase = (f"{adjectives[random.randint(0, len(adjectives) - 1)]} "
              f"{nouns[random.randint(0, len(nouns) - 1)]}")
    return phrase.replace("\n", "").lower()


class ErrorHandlerCog(commands.Cog):
    """Helper class for error handling.
    """
    def __init__(self, parent_bot):
        self.bot = parent_bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx, err):
        """Error handler for bot commands.
        """
        # This could be a typo, or a command meant for another bot.
        if isinstance(err, discord.ext.commands.errors.CommandNotFound):
            print(f"Ignoring unknown command: \"{ctx.message.content}\"")
            return
        # This command is on cooldown from being used too often.
        if isinstance(err, discord.ext.commands.errors.CommandOnCooldown):
            # Returns a human readable "<so and so long> before" string.
            retry_after = pendulum.now().diff_for_humans(pendulum.now().add(
                            seconds=err.retry_after))
            await ctx.send(f"{ctx.message.author.mention} You're doing it too "
                           f"much! Please wait {retry_after} trying again.")
            return
        # Something else happened! Just raise the error for the logs to catch.
        raise err


class PugQueueCog(commands.Cog):
    """PUG queue main event loop.
    """
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
                        pug_guilds[guild] = PugStatus(guild_channel=channel,
                                                      guild_roles=guild.roles)
                        await pug_guilds[guild].reload_puggers()
                    if pug_guilds[guild].is_full:
                        pug_start_success, msg = \
                            await pug_guilds[guild].start_pug()
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
        """Periodically clear inactive puggers from the queue(s).
        """
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


bot.add_cog(ErrorHandlerCog(bot))
bot.add_cog(PugQueueCog(bot))
bot.run(BOT_SECRET_TOKEN)
