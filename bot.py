#!/usr/bin/env python3

"""Discord PUG (pick-up game) bot for Neotokyo.
   Discord chat commands: !pug / !unpug / !puggers / !scramble / !clearpuggers
   TODO/DOCS: Useful docstring goes here!
"""

import asyncio
import os
import time
import random

import discord
from discord.ext import commands
from strictyaml import load, Bool, EmptyList, Float, Int, Map, Seq, Str


SCRIPT_NAME = "NT Pug Bot"
SCRIPT_VERSION = "0.7.4"
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
        "pug_admin_role_name": Seq(Str()) | EmptyList(),
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
        self.last_role_ping = 0

    def reset(self):
        """Stores the previous puggers, and then resets current pugger queue.
        """
        self.prev_puggers = self.jin_players + self.nsf_players
        self.jin_players = []
        self.nsf_players = []

    def player_join(self, player, team=None):
        """If there is enough room in this PUG queue, assigns this player
           to a random team to wait in, until the PUG is ready to be started.
           The specific team rosters can later be shuffled by a !scramble.
        """
        if not DEBUG_ALLOW_REQUEUE and \
                (player in self.jin_players or player in self.nsf_players):
            return False, (f"{player.mention} You are already queued! "
                           "If you wanted to un-PUG, please use **"
                           f"{CFG['command_prefix'].value}unpug** instead.")
        if team is None:
            team = random.randint(0, 1)  # flip a coin between jin/nsf
        if team == 0:
            if len(self.jin_players) < self.players_per_team:
                self.jin_players.append(player)
                return True, ""
        else:
            if len(self.nsf_players) < self.players_per_team:
                self.nsf_players.append(player)
                return True, ""
        return False, f"{player.mention} Sorry, this PUG is currently full!"

    def player_leave(self, player):
        """Removes a player from the pugger queue if they were in it.
        """
        num_before = self.num_queued()
        self.jin_players = [p for p in self.jin_players if p != player]
        self.nsf_players = [p for p in self.nsf_players if p != player]
        num_after = self.num_queued()

        left_queue = (num_after != num_before)
        if left_queue:
            return True, ""
        return False, (f"{player.mention} You are not currently in the PUG "
                       "queue")

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

    def start_pug(self):
        """Starts a PUG match.
        """
        if len(self.jin_players) == 0 or len(self.nsf_players) == 0:
            self.reset()
            return False, "Error: team was empty"
        msg = "**PUG is now ready!**\n"
        msg += "_Jinrai players:_\n"
        for player in self.jin_players:
            msg += f"{player.mention}, "
        msg = msg[:-2]  # trailing ", "
        msg += "\n_NSF players:_\n"
        for player in self.nsf_players:
            msg += f"{player.mention}, "
        msg = msg[:-2]  # trailing ", "
        msg += (f"\n\nTeams unbalanced? Use **{CFG['command_prefix'].value}"
                "scramble** to suggest new random teams.")
        return True, msg

    async def update_presence(self):
        """Updates the bot's status message ("presence").
           This is used for displaying things like the PUG queue status.
        """
        delta_time = int(time.time()) - self.last_changed_presence
        if delta_time < CFG["discord_presence_update_interval_secs"].value + 2:
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

    async def ping_role(self):
        """Pings the puggers Discord server role, if it's currently allowed.
           Frequency of these pings is restricted to avoid being too spammy.
        """
        if self.num_more_needed() == 0:
            return
        ping_dt_secs = int(time.time()) - self.last_role_ping
        ping_dt_hours = ping_dt_secs / 60 / 60
        hours_threshold = CFG["pugger_role_min_ping_interval_hours"].value
        ping_ratio = CFG["pugger_role_ping_threshold"].value
        pugger_role = CFG["pugger_role_name"].value
        if ping_dt_hours >= hours_threshold:
            pugger_ratio = self.num_queued() / self.num_expected()
            if pugger_ratio >= ping_ratio:
                for role in self.guild_roles:
                    if role.name == pugger_role:
                        min_nag_hrs = f"{hours_threshold:.1f}"
                        min_nag_hrs = min_nag_hrs.rstrip("0").rstrip(".")
                        msg = (f"{role.mention} Need **"
                               f"{self.num_more_needed()} more puggers** for "
                               "a game!\n_(This is an automatic ping to all "
                               "puggers, because the PUG queue is "
                               f"{(ping_ratio * 100):.0f}% full.\nRest "
                               "assured, I will only ping you once per "
                               f"{min_nag_hrs} hours, at most.\n"
                               "If you don't want any of these notifications, "
                               "please consider temporarily muting this bot "
                               f'or leaving the {role.mention} server '
                               "role._)")
                        await self.guild_channel.send(msg)
                        self.last_role_ping = int(time.time())
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
    join_success, response = pug_guilds[ctx.guild].player_join(
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

    leave_success, msg = pug_guilds[ctx.guild].player_leave(ctx.message.author)
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
        pug_guilds[ctx.guild].reset()
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


async def poll_if_pug_ready():
    """The main event loop for the bot.
    """
    while True:
        # Iterating and caching per-guild to support multiple Discord channels
        # simultaneously using the same bot instance with their own independent
        # player pools.
        for guild in bot.guilds:
            for channel in guild.channels:
                if channel.name != PUG_CHANNEL_NAME:
                    continue
                if guild not in pug_guilds:
                    pug_guilds[guild] = PugStatus(guild_channel=channel,
                                                  guild_roles=guild.roles)
                if pug_guilds[guild].is_full():
                    pug_start_success, msg = pug_guilds[guild].start_pug()
                    if pug_start_success:
                        # Before starting pug and resetting queue, manually
                        # update presence, so we're guaranteed to have the
                        # presence status fully up-to-date here.
                        pug_guilds[guild].last_changed_presence = 0
                        await pug_guilds[guild].update_presence()
                        # Ping the puggers
                        await channel.send(msg)
                        # And finally reset the queue, so we're ready for the
                        # next PUGs.
                        pug_guilds[guild].reset()
                else:
                    await pug_guilds[guild].update_presence()
                    await pug_guilds[guild].ping_role()
        await asyncio.sleep(CFG["queue_polling_interval_secs"].value)


def random_human_readable_phrase():
    """Generates a random human readable phrase to work as an identifier.
       Can be used for the !scrambles, to make it easier for players to refer
       to specific scramble permutations via voice chat by using these phrases.
    """
    with open(file="nouns.txt", mode="r", encoding="utf-8") as f_nouns:
        nouns = f_nouns.readlines()
    with open(file="adjectives.txt", mode="r", encoding="utf-8") as f_adjs:
        adjectives = f_adjs.readlines()
    phrase = (f"{adjectives[random.randint(0, len(adjectives) - 1)]} "
              f"{nouns[random.randint(0, len(nouns) - 1)]}")
    return phrase.replace("\n", "").lower()


asyncio.Task(poll_if_pug_ready())
asyncio.Task(bot.run(BOT_SECRET_TOKEN))
while True:
    continue
