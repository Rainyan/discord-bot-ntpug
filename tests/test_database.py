# /usr/bin/env python3

import asyncio
import os
import sys
from typing import Union, Iterable, TypeVar

import pytest

sys.path.append(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "..")
)
from pug import database


DriverBase = TypeVar("DriverBase", bound="database.DbDriver")


def event_loop():
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


def test_dbdrivers_value(dbdrivers: str) -> None:
    if dbdrivers.casefold() != "all":
        supported_drivers = ("sqlite3", "postgres")
        assert all(
            [
                x in [y for y in supported_drivers]
                for x in dbdrivers.casefold().split(",")
            ]
        )


class TestPostgres:
    @pytest.mark.asyncio
    async def test_create_db(self, dbdrivers: str) -> None:
        if (
            dbdrivers.casefold() != "all"
            and "postgres" not in dbdrivers.casefold().split(",")
        ):
            pytest.skip(reason="Skipped by --dbdrivers")
        db = database.Postgres(
            dbname=os.getenv("PYTEST_DB_DBNAME"),
            user=os.getenv("PYTEST_DB_USER"),
            password=os.getenv("PYTEST_DB_PASSWORD"),
            host=os.getenv("PYTEST_DB_HOST"),
            port=int(os.getenv("PYTEST_DB_PORT")),
        )
        async with db(1) as driver:
            await db._drop_tables()
            res = await driver._execute(
                "SELECT * FROM INFORMATION_SCHEMA.TABLES;"
            )
            assert len(res) > 0


class TestSqlite3:
    @pytest.mark.asyncio
    async def test_create_db(self, dbdrivers: str) -> None:
        if (
            dbdrivers.casefold() != "all"
            and "sqlite3" not in dbdrivers.casefold().split(",")
        ):
            pytest.skip(reason="Skipped by --dbdrivers")

        db = database.Sqlite3(database=os.getenv("PYTEST_DB_DBNAME"))
        async with db(1) as driver:
            await db._drop_tables()
            res = await driver._execute(
                "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name;"
            )
            assert len(res) > 0
