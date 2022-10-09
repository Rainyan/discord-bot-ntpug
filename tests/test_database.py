# /usr/bin/env python3

import os
import sys
from typing import Union, Iterable, TypeVar

import pytest

sys.path.append(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "..")
)
from pug import database


DriverBase = TypeVar("DriverBase", bound="database.DbDriver")


def test_dbdrivers_value(dbdrivers: str) -> None:
    if dbdrivers.casefold() != "all":
        drivers = ("sqlite3", "postgres")
        assert all(
            [
                x in [y for y in drivers]
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
        print(f"Hello from {self.__class__.__name__}: {dbdrivers}")
        db = database.Postgres(
            dbname=os.getenv("PYTEST_DB_DBNAME"),
            user=os.getenv("PYTEST_DB_USER"),
            password=os.getenv("PYTEST_DB_PASSWORD"),
            host=os.getenv("PYTEST_DB_HOST"),
            port=int(os.getenv("PYTEST_DB_PORT")),
        )
        # First, drop any existing tables so that we have a clean slate
        async with db(1) as driver:
            await driver._execute(
                """
DO $$ DECLARE
    tabname RECORD;
BEGIN
    FOR tabname IN (SELECT tablename
                    FROM pg_tables
                    WHERE schemaname = current_schema())
LOOP
    EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(tabname.tablename) || ' CASCADE';
END LOOP;
END $$;"""
            )
        async with db(1) as driver:
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
        print(f"Hello from {self.__class__.__name__}: {dbdrivers}")

        db = database.Sqlite3(database=os.getenv("PYTEST_DB_DBNAME"))
        # First, drop any existing tables so that we have a clean slate
        async with db(1) as driver:
            await driver._execute(
                """SELECT 'DROP TABLE ' || name || ';' from sqlite_master
    WHERE type = 'table';"""
            )
        async with db(1) as driver:
            res = await driver._execute(
                "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name;"
            )
            assert len(res) > 0
