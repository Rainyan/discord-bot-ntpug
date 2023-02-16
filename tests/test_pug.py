# /usr/bin/env python3

import asyncio
import os
import sys

sys.path.append(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "..")
)

from hypothesis import given, strategies
from hypothesis.strategies import integers

import pytest
import pytest_asyncio

from pug import bot, database


@pytest.fixture(scope="session", autouse=True)
def event_loop():
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def guild_id():
    return 1


@pytest.fixture(scope="session")
def context(session_mocker):
    context = session_mocker.AsyncMock()
    return context


# FIXME: Discord IDs use Twitter's Snowflake spec, which theoretically allows for the entire uint64 range.
# We can't store unsigned ints as a type in Sqlite3 -- perhaps store as string data, or store the sign bit separately?
# Unlikely to become an issue with real world data any time soon, but should deal with this regardless.
# This test can fail with the correct max_value of 2**64-1.
@given(integers(min_value=1, max_value=2**63-1))
@pytest.mark.asyncio
async def test_pug_join(context, x):
    context.guild.id = 1
    context.user.id = x
     

    await bot.pug(context)


#@pytest.mark.asyncio
#async def test_pug_unjoin(event_loop, context) -> None:
#    await bot.unpug(context)

