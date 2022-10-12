# /usr/bin/env python3

import os
import sys

sys.path.append(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "..")
)

import pytest

from pug import bot


# TODO: get fixture for raw DB calls to verify DB status
# TODO: write our own async event loop instead of the Pycord abstraction
#       so that we can use it here


@pytest.mark.asyncio
async def test_pug_join(mocker) -> None:
    context = mocker.AsyncMock()
    context.guild.id = context.user.id = 1
    await bot.pug(context)


@pytest.mark.asyncio
async def test_pug_unjoin(mocker) -> None:
    context = mocker.AsyncMock()
    context.guild.id = context.user.id = 1
    await bot.unpug(context)
