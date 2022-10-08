"""This module holds just the bot instance, to avoid circular imports.
"""

from typing import Optional

from discord.ext import commands


BOT: Optional[commands.Bot] = None
