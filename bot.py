#!/usr/bin/env python3

"""Discord PUG (pick-up game) bot for Neotokyo.
   Discord chat commands: !pug / !unpug / !puggers / !scramble / !clearpuggers
   TODO/DOCS: Useful docstring goes here!
"""

import asyncio
from datetime import datetime, timezone
import os
import time
import random

import discord
from discord.ext import commands, tasks
import pendulum
from strictyaml import load, Bool, EmptyList, Float, Int, Map, Seq, Str


# May encounter breaking changes otherwise
# NOTE: Discord API "decomissions" are scheduled for April 30, 2022:
# https://github.com/discord/discord-api-docs/discussions/4510
# Probably have to upgrade to pycord 2.X dev branch, or
# some original discord.py project equivalent whenever it releases.
assert discord.version_info.major == 1 and discord.version_info.minor == 7

SCRIPT_NAME = "NT Pug Bot"
SCRIPT_VERSION = "0.10.1"
SCRIPT_URL = "https://github.com/Rainyan/discord-bot-ntpug"

CFG_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                        "config.yml")
assert os.path.isfile(CFG_PATH)
with open(file=CFG_PATH, mode="r", encoding="utf-8") as f_config:
    YAML_CFG_SCHEMA = Map({
        "bot_secret_token": Str(),
        "command_prefix": Str(),
        "pug_channel_name": Str(),
        "num_players_required_total": Int(),
        "debug_allow_requeue": Bool(),
        "queue_polling_interval_secs": Int(),
        "discord_presence_update_interval_secs": Int(),
        "pugger_role_name": Str(),
        "pugger_role_ping_threshold": Float(),
        "pugger_role_min_ping_interval_hours": Float(),
        "pugger_role_ping_max_history": Int(),
        "pug_admin_role_name": Seq(Str()) | EmptyList(),
        "restore_puggers_limit_hours": Int(),
    })
    CFG = load(f_config.read(), YAML_CFG_SCHEMA)
assert CFG is not None

bot = commands.Bot(command_prefix=CFG["command_prefix"].value)
NUM_PLAYERS_REQUIRED = CFG["num_players_required_total"].value
assert NUM_PLAYERS_REQUIRED > 0, "Need positive number of players"
assert NUM_PLAYERS_REQUIRED % 2 == 0, "Need even number of players"
DEBUG_ALLOW_REQUEUE = CFG["debug_allow_requeue"].value
PUG_CHANNEL_NAME = CFG["pug_channel_name"].value
BOT_SECRET_TOKEN = os.environ.get("DISCORD_BOT_TOKEN") or \
    CFG["bot_secret_token"].value
assert CFG["pugger_role_ping_threshold"].value >= 0 and \
    CFG["pugger_role_ping_threshold"].value <= 1

# This is a variable because the text used for detecting previous PUGs when
# restoring status during restart.
PUG_READY_TITLE = "**PUG is now ready!**"

print(f"Now running {SCRIPT_NAME} v.{SCRIPT_VERSION} -- {SCRIPT_URL}",
      flush=True)


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
        self.jin_players = []
        self.nsf_players = []
        self.prev_puggers = []
        self.players_required_total = players_required
        self.players_per_team = int(self.players_required_total / 2)
        self.last_changed_presence = 0
        self.last_presence = None
        self.lock = asyncio.Lock()

    async def reset(self):
        """Stores the previous puggers, and then resets current pugger queue.
        """
        async with self.lock:
            self.prev_puggers = self.jin_players + self.nsf_players
            self.jin_players = []
            self.nsf_players = []

    async def player_join(self, player, team=None):
        """If there is enough room in this PUG queue, assigns this player
           to a random team to wait in, until the PUG is ready to be started.
           The specific team rosters can later be shuffled by a !scramble.
        """
        async with self.lock:
            if not DEBUG_ALLOW_REQUEUE and \
                    (player in self.jin_players or player in self.nsf_players):
                return False, (f"{player.mention} You are already queued! "
                               "If you wanted to un-PUG, please use **"
                               f"{CFG['command_prefix'].value}unpug** "
                               "instead.")
            if team is None:
                team = random.randint(0, 1)  # flip a coin between jin/nsf
            if team == 0:
                if len(self.jin_players) < self.players_per_team:
                    self.jin_players.append(player)
                    return True, ""
            if len(self.nsf_players) < self.players_per_team:
                self.nsf_players.append(player)
                return True, ""
            return False, (f"{player.mention} Sorry, this PUG is currently "
                           "full!")

    async def reload_puggers(self):
        """Iterate PUG channel's recent message history to figure out who
           should be pugged. This is used both for restoring puggers after a
           bot restart, but also for dropping inactive players from the queue
           after inactivity of "restore_puggers_limit_hours" period.
        """
        assert CFG["restore_puggers_limit_hours"].value > 0
        after = pendulum.now().subtract(
            hours=CFG["restore_puggers_limit_hours"].value)
        # Because Pycord 1.7.3 wants non timezone aware "after" date.
        after = datetime.fromisoformat(after.in_timezone("UTC").isoformat())
        after = after.replace(tzinfo=None)

        def is_pug_cmd(msg):
            """Predicate for PUG join chat commands.
            """
            return msg.content == f"{CFG['command_prefix'].value}pug"

        def is_unpug_cmd(msg):
            """Predicate for PUG un-join chat commands.
            """
            return msg.content == f"{CFG['command_prefix'].value}unpug"

        def is_pug_start(msg):
            """Predicate for PUG start.
            """
            return msg.author.bot and msg.content.startswith(PUG_READY_TITLE)

        def predicate(msg):
            """Combined predicate for filtering the message history for
               enumeration.
            """
            return is_pug_cmd(msg) or is_unpug_cmd(msg) or is_pug_start(msg)

        # First reset the PUG queue, and then replay the pug/unpug traffic
        # within the acceptable "restore_puggers_limit_hours" history range.
        await self.reset()
        async for msg in self.guild_channel.history(after=after,
                                                    oldest_first=True).\
                filter(predicate):
            if is_pug_start(msg):
                await self.reset()
            elif is_pug_cmd(msg):
                await self.player_join(msg.author)
            else:
                await self.player_leave(msg.author)

    async def player_leave(self, player):
        """Removes a player from the pugger queue if they were in it.
        """
        async with self.lock:
            num_before = self.num_queued()
            self.jin_players = [p for p in self.jin_players if p != player]
            self.nsf_players = [p for p in self.nsf_players if p != player]
            num_after = self.num_queued()

            left_queue = (num_after != num_before)
            if left_queue:
                return True, ""
            return False, (f"{player.mention} You are not currently in the "
                           "PUG queue")

    def num_queued(self):
        """Returns the number of puggers currently in the PUG queue.
        """
        return len(self.jin_players) + len(self.nsf_players)

    def num_expected(self):
        """Returns the number of puggers expected, total, to start a PUG.
        """
        return self.players_required_total

    def num_more_needed(self):
        """Returns how many more puggers are needed to start a PUG.
        """
        return max(0, self.num_expected() - self.num_queued())

    def is_full(self):
        """Whether the PUG queue is currently full or not."
        """
        return self.num_queued() >= self.num_expected()

    async def start_pug(self):
        """Starts a PUG match.
        """
        async with self.lock:
            if len(self.jin_players) == 0 or len(self.nsf_players) == 0:
                await self.reset()
                return False, "Error: team was empty"
            msg = f"{PUG_READY_TITLE}\n"
            msg += "_Jinrai players:_\n"
            for player in self.jin_players:
                msg += f"{player.mention}, "
            msg = msg[:-2]  # trailing ", "
            msg += "\n_NSF players:_\n"
            for player in self.nsf_players:
                msg += f"{player.mention}, "
            msg = msg[:-2]  # trailing ", "
            msg += ("\n\nTeams unbalanced? Use **"
                    f"{CFG['command_prefix'].value}scramble** to suggest new "
                    "random teams.")
            return True, msg

    async def update_presence(self):
        """Updates the bot's status message ("presence").
           This is used for displaying things like the PUG queue status.
        """
        async with self.lock:
            delta_time = int(time.time()) - self.last_changed_presence
            if delta_time < \
                    CFG["discord_presence_update_interval_secs"].value + 2:
                return

            presence = self.last_presence
            if presence is None:
                presence = {
                    "activity": discord.BaseActivity(),
                    "status": discord.Status.idle
                }

            puggers_needed = max(0, self.num_expected() - self.num_queued())

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
        history_limit = CFG["pugger_role_ping_max_history"].value
        assert history_limit >= 0
        after = pendulum.now().subtract(
            hours=CFG["pugger_role_min_ping_interval_hours"].value)
        # Because Pycord 1.7.3 wants non timezone aware "after" date.
        after = datetime.fromisoformat(after.in_timezone("UTC").isoformat())
        after = after.replace(tzinfo=None)
        async for msg in self.guild_channel.history(limit=history_limit,
                                                    after=after,
                                                    oldest_first=False):
            if CFG["pugger_role_name"].value in \
                    [role.name for role in msg.role_mentions]:
                # Because Pycord 1.7.3 returns non timezone aware UTC date,
                # and we need to subtract a timedelta using it.
                naive_utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
                return naive_utc_now - msg.created_at
        return None

    async def ping_role(self):
        """Pings the puggers Discord server role, if it's currently allowed.
           Frequency of these pings is restricted to avoid being too spammy.
        """
        async with self.lock:
            if self.num_more_needed() == 0:
                return

            last_ping_dt = await self.role_ping_deltatime()
            hours_limit = CFG["pugger_role_min_ping_interval_hours"].value
            if last_ping_dt is not None:
                last_ping_hours = last_ping_dt.total_seconds() / 60 / 60
                if last_ping_hours < hours_limit:
                    return

            pugger_ratio = self.num_queued() / self.num_expected()
            ping_ratio = CFG["pugger_role_ping_threshold"].value
            if pugger_ratio < ping_ratio:
                return

            pugger_role = CFG["pugger_role_name"].value
            for role in self.guild_roles:
                if role.name == pugger_role:
                    min_nag_hours = f"{hours_limit:.1f}"
                    min_nag_hours = min_nag_hours.rstrip("0").rstrip(".")
                    msg = (f"{role.mention} Need **"
                           f"{self.num_more_needed()} more puggers** "
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


@bot.command(brief="Test if bot is active")
async def ping(ctx):
    """Just a standard Discord bot ping test command for confirming whether
       the bot is online or not.
    """
    await ctx.send("pong")


@bot.command(brief="Join the PUG queue")
async def pug(ctx):
    """Player command for joining the PUG queue.
    """
    if ctx.guild not in pug_guilds or not ctx.channel.name == PUG_CHANNEL_NAME:
        return
    response = ""
    join_success, response = await pug_guilds[ctx.guild].player_join(
        ctx.message.author)
    if join_success:
        response = (f"{ctx.message.author.name} has joined the PUG queue "
                    f"({pug_guilds[ctx.guild].num_queued()} / "
                    f"{pug_guilds[ctx.guild].num_expected()})")
    await ctx.send(f"{response}")


@bot.command(brief="Leave the PUG queue")
async def unpug(ctx):
    """Player command for leaving the PUG queue.
    """
    if ctx.guild not in pug_guilds or not ctx.channel.name == PUG_CHANNEL_NAME:
        return

    leave_success, msg = await pug_guilds[ctx.guild].player_leave(
        ctx.message.author)
    if leave_success:
        msg = (f"{ctx.message.author.name} has left the PUG queue "
               f"({pug_guilds[ctx.guild].num_queued()} / "
               f"{pug_guilds[ctx.guild].num_expected()})")
    await ctx.send(msg)


@bot.command(brief="Empty the server's PUG queue")
async def clearpuggers(ctx):
    """Player command for clearing the PUG queue.
       This can be restricted to Discord guild specific admin roles.
    """
    if ctx.guild not in pug_guilds or not ctx.channel.name == PUG_CHANNEL_NAME:
        return

    # If zero pug admin roles are configured, assume anyone can !clearpuggers
    if len(CFG["pug_admin_role_name"]) == 0:
        is_allowed = True
    else:
        pug_admin_roles = [role.value for role in CFG["pug_admin_role_name"]]
        user_roles = [role.name for role in ctx.message.author.roles]
        is_allowed = any(role in pug_admin_roles for role in user_roles)

    if is_allowed:
        await pug_guilds[ctx.guild].reset()
        await ctx.send(f"{ctx.message.author.name} has reset the PUG queue")
    else:
        await ctx.send(f"{ctx.message.author.mention} The PUG queue can only "
                       f"be reset by users with role(s): _{pug_admin_roles}_")


@bot.command(brief="Get new random teams suggestion for the latest PUG")
async def scramble(ctx):
    """Player command for scrambling the latest full PUG queue.
       Can be called multiple times for generating new random teams.
    """
    msg = ""
    if len(pug_guilds[ctx.guild].prev_puggers) == 0:
        msg = (f"{ctx.message.author.mention} Sorry, no previous PUG found to "
               "scramble")
    else:
        random.shuffle(pug_guilds[ctx.guild].prev_puggers)
        msg = f"{ctx.message.author.name} suggests scrambled teams:\n"
        msg += f"_(random shuffle id: {random_human_readable_phrase()})_\n"
        msg += "_Jinrai players:_\n"
        for i in range(int(len(pug_guilds[ctx.guild].prev_puggers) / 2)):
            msg += f"{pug_guilds[ctx.guild].prev_puggers[i].name}, "
        msg = msg[:-2]  # trailing ", "
        msg += "\n_NSF players:_\n"
        for i in range(int(len(pug_guilds[ctx.guild].prev_puggers) / 2),
                       len(pug_guilds[ctx.guild].prev_puggers)):
            msg += f"{pug_guilds[ctx.guild].prev_puggers[i].name}, "
        msg = msg[:-2]  # trailing ", "
        msg += ("\n\nTeams still unbalanced? Use **"
                f"{CFG['command_prefix'].value}"
                "scramble** to suggest new random teams.")
    await ctx.send(msg)


@bot.command(brief="List players currently queueing for PUG")
async def puggers(ctx):
    """Player command for listing players currently in the PUG queue.
    """
    if ctx.guild not in pug_guilds or not ctx.channel.name == PUG_CHANNEL_NAME:
        return

    msg = (f"{pug_guilds[ctx.guild].num_queued()} / "
           f"{pug_guilds[ctx.guild].num_expected()} player(s) currently "
           "queued")

    if pug_guilds[ctx.guild].num_queued() > 0:
        all_players_queued = pug_guilds[ctx.guild].jin_players + \
            pug_guilds[ctx.guild].nsf_players
        msg += ": "
        for player in all_players_queued:
            msg += f"{player.name}, "
        msg = msg[:-2]  # trailing ", "
    await ctx.send(msg)


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

    @tasks.loop(seconds=CFG["queue_polling_interval_secs"].value)
    async def poll_queue(self):
        """Poll the PUG queue to see if we're ready to play,
           and to possibly update our status in various ways.

           Iterating and caching per-guild to support multiple Discord
           channels simultaneously using the same bot instance with their
           own independent player pools.
        """
        async with self.lock:
            for guild in bot.guilds:
                for channel in guild.channels:
                    if channel.name != PUG_CHANNEL_NAME:
                        continue
                    if guild not in pug_guilds:
                        pug_guilds[guild] = PugStatus(guild_channel=channel,
                                                      guild_roles=guild.roles)
                        await pug_guilds[guild].reload_puggers()
                    if pug_guilds[guild].is_full():
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

    @tasks.loop(hours=1)
    async def clear_inactive_puggers(self):
        """Periodically clear inactive puggers from the queue(s).
        """
        async with self.lock:
            for guild in bot.guilds:
                for channel in guild.channels:
                    if channel.name != PUG_CHANNEL_NAME:
                        continue
                    if guild not in pug_guilds:
                        continue
                    if pug_guilds[guild].is_full():
                        continue
                    await pug_guilds[guild].reload_puggers()


PugQueueCog(bot)
bot.run(BOT_SECRET_TOKEN)
