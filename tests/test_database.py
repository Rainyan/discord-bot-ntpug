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


class TestPostgres:
    @pytest.mark.asyncio
    async def test_create_db(self, dbdrivers: str) -> None:
        print(f"Hello from {self.__class__.__name__}: {dbdrivers}")
        db = database.Postgres(
            dbname=os.getenv("PYTEST_DB_DBNAME"),
            user=os.getenv("PYTEST_DB_USER"),
            password=os.getenv("PYTEST_DB_PASSWORD"),
            host=os.getenv("PYTEST_DB_HOST"),
            port=int(os.getenv("PYTEST_DB_PORT"))
        )
        async with db(1) as driver:
            # Drop all tables
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
            res = await driver._execute(
                "SELECT * FROM INFORMATION_SCHEMA.TABLES;"
            )
            assert len(res) > 0


class TestSqlite3:
    @pytest.mark.asyncio
    async def test_create_db(self, dbdrivers: str) -> None:
        print(f"Hello from {self.__class__.__name__}: {dbdrivers}")

        db = database.Sqlite3(database=os.getenv("PYTEST_DB_DBNAME"))
        async with db(1) as driver:
            await driver._execute(
                """SELECT 'DROP TABLE ' || name || ';' from sqlite_master
    WHERE type = 'table';"""
            )
            res = await driver._execute(
                "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name;"
            )
            assert len(res) > 0
