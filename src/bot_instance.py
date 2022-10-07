"""This module holds just the bot instance, to avoid circular imports.
"""

from typing import Union

from discord.ext import commands

BOT: Union[None, commands.Bot] = None
