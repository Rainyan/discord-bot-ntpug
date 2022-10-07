"""PUG queueing specific utilities."""

import asyncio
from datetime import datetime, timedelta, timezone
import random
import time
from typing import Union

import discord

from config import cfg
import bot_instance


# This is a variable because the text is used for detecting previous PUGs
# when restoring status during restart.
PUG_READY_TITLE = "**PUG is now ready!**"


class PugStatus():
    """Object for containing and operating on one Discord server's PUG
       information.
    """
    # pylint: disable=too-many-instance-attributes
    # This might need revisiting, but deal with it for now.
    def __init__(self, guild_channel,
                 players_required=cfg("NTBOT_PLAYERS_REQUIRED_TOTAL"),
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

    async def reset(self) -> None:
        """Stores the previous puggers, and then resets current pugger queue.
        """
        async with self.lock:
            self.prev_puggers = self.team1_players + self.team2_players
            self.team1_players.clear()
            self.team2_players.clear()

    async def player_join(self, player, team=None) -> tuple[bool, str]:
        """If there is enough room in this PUG queue, assigns this player
           to a random team to wait in, until the PUG is ready to be started.
           The specific team rosters can later be shuffled by a !scramble.
        """
        async with self.lock:
            if not cfg("NTBOT_DEBUG") and \
                    (player in self.team1_players or
                     player in self.team2_players):
                return False, (f"{player.mention} You are already queued! "
                               "If you wanted to un-PUG, please use `unpug` "
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

    async def reload_puggers(self) -> None:
        """Iterate PUG channel's recent message history to figure out who
           should be pugged. This is used both for restoring puggers after a
           bot restart, but also for dropping inactive players from the queue
           after inactivity of "NTBOT_IDLE_THRESHOLD_HOURS" period.
        """
        return  # FIXME: update to use database logic!!!

        limit_hrs = cfg("NTBOT_IDLE_THRESHOLD_HOURS")
        assert limit_hrs > 0
        after = datetime.now() - timedelta(hours=limit_hrs)

        def is_cmd(msg, cmd) -> bool:
            """Predicate for whether message equals a specific PUG command.
            """
            return msg.content == f"{bot_instance.BOT.command_prefix}{cmd}"

        def is_pug_reset(msg) -> bool:
            """Predicate for whether a message signals PUG reset.
            """
            return (msg.author.bot and
                    msg.content.endswith("has reset the PUG queue"))

        def is_pug_start(msg) -> bool:
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

    async def player_leave(self, player) -> tuple[bool, str]:
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
    def num_queued(self) -> int:
        """Returns the number of puggers currently in the PUG queue.
        """
        return len(self.team1_players) + len(self.team2_players)

    @property
    def num_expected(self) -> int:
        """Returns the number of puggers expected, total, to start a PUG.
        """
        return self.players_required_total

    @property
    def players_per_team(self) -> int:
        """Players required to start a PUG, per team."""
        res = self.num_expected / 2
        assert res % 1 == 0, "Must be whole number"
        return int(res)

    @property
    def num_more_needed(self) -> int:
        """Returns how many more puggers are needed to start a PUG.
        """
        return max(0, self.num_expected - self.num_queued)

    @property
    def is_full(self) -> bool:
        """Whether the PUG queue is currently full or not."""
        return self.num_queued >= self.num_expected

    async def start_pug(self) -> tuple[bool, str]:
        """Starts a PUG match.
        """
        async with self.lock:
            if len(self.team1_players) == 0 or len(self.team2_players) == 0:
                await self.reset()
                return False, "Error: team was empty"
            msg = f"{PUG_READY_TITLE}\n"
            msg += "\n_" + cfg("NTBOT_FIRST_TEAM_NAME") + " players:_\n"
            for player in self.team1_players:
                msg += f"{player.mention}, "
            msg = msg[:-2]  # trailing ", "
            msg += "\n_" + cfg("NTBOT_SECOND_TEAM_NAME") + " players:_\n"
            for player in self.team2_players:
                msg += f"{player.mention}, "
            msg = msg[:-2]  # trailing ", "
            # FIXME!!!
            # msg += ("\n\nTeams unbalanced? Use **"
            #         f"{bot_instance.BOT.command_prefix}scramble** to suggest "
            #         "new random teams.")
            return True, msg

    async def update_presence(self) -> None:
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

            await bot_instance.BOT.change_presence(
                activity=presence["activity"],
                status=presence["status"])
            self.last_presence = presence
            self.last_changed_presence = int(time.time())

    async def role_ping_deltatime(self) -> Union[timedelta, None]:
        """Returns a datetime.timedelta of latest role ping, or None if no such
           ping was found.
        """
        after = datetime.now() - timedelta(
            hours=cfg("NTBOT_PUGGER_ROLE_PING_MIN_INTERVAL_HOURS"))
        try:
            async for msg in self.guild_channel.history(limit=None,
                                                        after=after,
                                                        oldest_first=False).\
                    filter(lambda msg: cfg("NTBOT_PUGGER_ROLE")
                           in [role.name for role in msg.role_mentions]):
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

    async def ping_role(self) -> None:
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
                if role.name == cfg("NTBOT_PUGGER_ROLE"):
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
