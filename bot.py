#!/usr/bin/env python3

import asyncio
import atexit
import os
import time
import random

import discord
from discord.ext import commands
from matplotlib import font_manager
from PIL import Image, ImageDraw, ImageFont
from strictyaml import load, Bool, Int, Map, Seq, Str, YAMLError
import requests
from io import BytesIO


SCRIPT_NAME = "NT Pug Bot"
SCRIPT_VERSION = "0.5.0"
SCRIPT_URL = "https://github.com/Rainyan/discord-bot-ntpug"

CFG_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                        "config.yml")
assert os.path.isfile(CFG_PATH)
with open(CFG_PATH, "r") as f:
    YAML_CFG_SCHEMA = Map({
        "bot_secret_token": Str(),
        "avatar_download_url": Str(),
        "command_prefix": Str(),
        "pug_channel_name": Str(),
        "num_players_required_total": Int(),
        "debug_allow_requeue": Bool(),
        "queue_polling_interval_secs": Int(),
        "discord_presence_update_interval_secs": Int(),
    })
    CFG = load(f.read(), YAML_CFG_SCHEMA)
assert CFG is not None

DEFAULT_AVATAR_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                   "static", "avatars", "default.png")
if not os.path.isfile(DEFAULT_AVATAR_PATH):
    r = requests.get(CFG["avatar_download_url"].value)
    r.raise_for_status()
    with Image.open(BytesIO(r.content)).convert("RGBA") as image:
        image.save(DEFAULT_AVATAR_PATH)
    assert os.path.isfile(DEFAULT_AVATAR_PATH)

bot = commands.Bot(command_prefix=CFG["command_prefix"].value)
NUM_PLAYERS_REQUIRED = CFG["num_players_required_total"].value
assert NUM_PLAYERS_REQUIRED % 2 == 0, "Need even number of players"
DEBUG_ALLOW_REQUEUE = CFG["debug_allow_requeue"].value
PUG_CHANNEL_NAME = CFG["pug_channel_name"].value
BOT_SECRET_TOKEN = os.environ.get("DISCORD_BOT_TOKEN") or \
    CFG["bot_secret_token"].value

print(f"Now running {SCRIPT_NAME} v.{SCRIPT_VERSION} -- {SCRIPT_URL}",
      flush=True)


class PugStatus():
    def __init__(self, players_required=NUM_PLAYERS_REQUIRED,
                 guild_emojis=[]):
        self.guild_emojis = guild_emojis
        self.jin_players = []
        self.nsf_players = []
        self.prev_puggers = []
        self.players_required_total = players_required
        self.players_per_team = int(self.players_required_total / 2)
        self.last_changed_presence = 0
        self.last_presence = None

    def reset(self):
        self.prev_puggers = self.jin_players + self.nsf_players
        self.jin_players = []
        self.nsf_players = []

    def player_join(self, player, team=None):
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
        num_before = self.num_queued()
        self.jin_players = [p for p in self.jin_players if p != player]
        self.nsf_players = [p for p in self.nsf_players if p != player]
        num_after = self.num_queued()

        left_queue = (num_after != num_before)
        if left_queue:
            return True, ""
        else:
            return False, (f"{player.mention} You are not currently in the "
                           "PUG queue")

    def num_queued(self):
        return len(self.jin_players) + len(self.nsf_players)

    def num_expected(self):
        return self.players_required_total

    def is_full(self):
        return self.num_queued() >= self.num_expected()

    def start_pug(self):
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

    # TODO: remove this
    async def update_avatar(self):
        with open(DEFAULT_AVATAR_PATH, "rb") as f:
            try:
                await bot.user.edit(avatar=f.read())
            except discord.errors.HTTPException as e:
                pass

    async def update_presence(self):
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
        return


pug_guilds = {}


@bot.command(brief="Test if bot is active")
async def ping(ctx):
    await ctx.send("pong")


@bot.command(brief="Join the PUG queue")
async def pug(ctx):
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
    if ctx.guild not in pug_guilds or not ctx.channel.name == PUG_CHANNEL_NAME:
        return
    pug_guilds[ctx.guild].reset()
    await ctx.send(f"{ctx.message.author.name} has reset the PUG queue")


@bot.command(brief="Get new random teams suggestion for the latest PUG")
async def scramble(ctx):
    msg = ""
    if len(pug_guilds[ctx.guild].prev_puggers) == 0:
        msg = (f"{ctx.message.author.mention} Sorry, no previous PUG found to "
               "scramble")
    else:
        random.shuffle(pug_guilds[ctx.guild].prev_puggers)
        msg = f"{ctx.message.author.name} suggests scrambled teams:\n"
        # Adding a random human readable phrase here to work as an identifier
        # for this shuffle, so specific shuffle results are easier to refer to
        # in voice chat, if there are many of them.
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
    while True:
        # Iterating and caching per-guild to support multiple Discord channels
        # simultaneously using the same bot instance with their own independent
        # player pools.
        for guild in bot.guilds:
            for channel in guild.channels:
                if channel.name != PUG_CHANNEL_NAME:
                    continue
                if guild not in pug_guilds:
                    pug_guilds[guild] = PugStatus(guild_emojis=guild.emojis)

                # Can't set avatar per-guild, so can only support number
                # avatars with single guild.
                if len(bot.guilds) == 1:
                    await pug_guilds[guild].update_avatar()
                    await pug_guilds[guild].update_presence()

                if pug_guilds[guild].is_full():
                    pug_start_success, msg = pug_guilds[guild].start_pug()
                    if pug_start_success:
                        # Before starting pug and resetting queue, manually
                        # update presence, so we're guaranteed to have the
                        # presence status fully up-to-date here.
                        if len(bot.guilds) == 1:
                            pug_guilds[guild].last_changed_presence = 0
                            await pug_guilds[guild].update_presence()
                        # Ping the puggers
                        await channel.send(msg)
                        # And finally reset the queue, so we're ready for the
                        # next PUGs.
                        pug_guilds[guild].reset()
        await asyncio.sleep(CFG["queue_polling_interval_secs"].value)


def random_human_readable_phrase():
    with open("nouns.txt", "r") as f:
        nouns = f.readlines()
    with open("adjectives.txt", "r") as f:
        adjectives = f.readlines()
    phrase = (f"{adjectives[random.randint(0, len(adjectives))]} "
              f"{nouns[random.randint(0, len(nouns))]}")
    return phrase.replace("\n", "").lower()


asyncio.Task(poll_if_pug_ready())
asyncio.Task(bot.run(BOT_SECRET_TOKEN))
while True:
    continue
