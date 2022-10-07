"""
Discord bot for organizing PUGs (pick-up games).
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

:copyright: (c) 2021- https://github.com/Rainyan and collaborators
:license: MIT License; please see the LICENSE file for info.
"""

__title__ = "NT Pug Bot for Discord"
__author__ = "https://github.com/Rainyan and collaborators"
__license__ = "MIT"
__copyright__ = "Copyright (c) 2021- https://github.com/Rainyan and collaborators"
__version__ = "1.0.0"


import os, sys; sys.path.append(os.path.dirname(os.path.realpath(__file__)))
