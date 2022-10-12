"""This module abstracts the database driver logic for accessing the PUG data.
"""

from abc import ABC, abstractmethod
import asyncio
import sqlite3
from types import TracebackType
from typing import Any, Union, Optional, Iterable, Type, TypeVar

import psycopg2  # todo: make optional (setup.py)

from config import cfg


T = TypeVar("T", bound="DbDriver")


class DbDriver(ABC):
    """Abstract DB driver base. All DB drivers should inherit from this."""

    def __init__(self, *_args: Any, **_kwargs: Any):
        self.lock = asyncio.Lock()
        self.connection: Union[
            None, sqlite3.Connection, psycopg2.connection
        ] = None
        self.guild_id: Optional[int] = None
        self.cursor: Union[None, sqlite3.Cursor, psycopg2.cursor] = None
        self.table: Optional[str] = None

    def __del__(self) -> None:
        if self.connection is not None:
            self.connection.close()

    def __call__(self: T, guild_id: int) -> T:
        assert self.guild_id is None
        assert guild_id > 0
        self.guild_id = guild_id

        assert self.table is None
        self.table = f"{cfg('NTBOT_DB_TABLE')}_{guild_id}"

        assert self.cursor is None
        assert self.connection is not None
        self.cursor = self.connection.cursor()

        return self

    async def __aenter__(self: T) -> T:
        async with self.lock:
            assert self.guild_id is not None
            assert self.connection is not None
            assert self.cursor is not None
            self.cursor.execute(
                f"""CREATE TABLE IF NOT EXISTS {self.table} (
                                id serial PRIMARY KEY,
                                user_id numeric,
                                is_queued boolean DEFAULT false,
                                unique(user_id));"""
            )
            self.connection.commit()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> bool:
        async with self.lock:
            assert self.table is not None
            self.table = None
            assert self.cursor is not None
            self.cursor.close()
            self.cursor = None
            self.guild_id = None
        return False

    async def get_discord_users(
        self, discord_ids: Optional[Iterable[int]] = None
    ) -> list[dict[str, Union[int, bool]]]:
        """Get the DB data of a specific user by their Discord ID integer.

        If discord_id is None, gets all users.
        Returns a list of 0 or more rows of data.
        """
        query = f"SELECT * FROM {self.table}"
        my_vars = None
        if discord_ids is not None:
            query += f" WHERE user_id IN ({', '.join([self.bind_placeholder for _ in discord_ids])})"
            my_vars = tuple(discord_ids)
        query += ";"
        res = await self._execute(query, my_vars)
        return [
            # TODO: refactor to return row names in a single row (instead of duplicating the key names),
            # so the value of the k-v pair is easier to consume by callers of this.
            # Could return a tuple of (keys, list[tuple(values)]), etc.
            dict(zip(("db_row_id", "discord_id", "queued"), x))
            for x in res
        ]

    async def set_discord_user(self, discord_id: int, is_queued: bool) -> None:
        """Set the DB queued state of a specific user by their Discord ID."""
        await self._execute(
            f"""INSERT INTO {self.table} (user_id) VALUES
                            ({self.bind_placeholder})
                            ON CONFLICT (user_id) DO UPDATE SET is_queued =
                            {self.bind_placeholder};""",
            (discord_id, is_queued),
        )

    @abstractmethod
    async def _execute(
        self, query: str, my_vars: Optional[tuple[Any]] = None
    ) -> list[dict[str, Union[int, bool]]]:
        """Returns a list of all fetched results of the query.

        If there were no results, returns an empty list.
        """

    @abstractmethod
    async def _drop_tables(self):
        """Drops all of the tables in this DB's schema."""

    @property
    @abstractmethod
    def bind_placeholder(self) -> str:
        """Returns the placeholder used for binding values in SQL queries."""


class Sqlite3(DbDriver):
    """DB driver for SQLite 3."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.connection = sqlite3.connect(
            database=kwargs["database"].removesuffix(".sqlite3") + ".sqlite3"
        )

    async def _execute(self, query, my_vars=None):
        async with self.lock:
            self.cursor.execute(query, my_vars if my_vars is not None else ())
            res = self.cursor.fetchall()
            self.connection.commit()
        return res

    async def _drop_tables(self):
        print("Drop tables: sqlite3")
        async with self.lock:
            self.cursor.execute("""
SELECT 'DROP TABLE ' || name || ';' from sqlite_master
WHERE type = 'table';""")

    @property
    def bind_placeholder(self):
        return "?"


class Postgres(DbDriver):
    """DB driver for Postgres."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        print(f"DBNAME IS: {kwargs['dbname']}")
        self.connection = psycopg2.connect(
            dbname=kwargs["dbname"],
            user=kwargs["user"],
            password=kwargs["password"],
            host=kwargs["host"],
            port=kwargs["port"],
        )

    async def _execute(self, query, my_vars=None):
        async with self.lock:
            self.cursor.execute(query, my_vars)
            try:
                res = self.cursor.fetchall()
            except psycopg2.ProgrammingError as err:
                # TODO: confirm this works
                if str(err) == "no results to fetch":
                    res = []
                else:
                    raise err
            self.connection.commit()
        return res

    async def _drop_tables(self):
        print("Drop tables: sqlite3")
        async with self.lock:
            self.cursor.execute("""
DO $$ DECLARE
    tabname RECORD;
BEGIN
    FOR tabname IN (SELECT tablename
                    FROM pg_tables
                    WHERE schemaname = current_schema())
LOOP
    EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(tabname.tablename) || ' CASCADE';
END LOOP;
END $$;""")

    @property
    def bind_placeholder(self):
        return "%s"


DB: Union[None, DbDriver] = None
driver = cfg("NTBOT_DB_DRIVER")
if driver == "postgres":
    DB = Postgres(
        dbname=cfg("NTBOT_DB_NAME"),
        user=cfg("NTBOT_DB_USER"),
        password=cfg("NTBOT_DB_SECRET"),
        host=cfg("NTBOT_DB_HOST"),
        port=cfg("NTBOT_DB_PORT"),
    )
elif driver == "sqlite3":
    DB = Sqlite3(database=cfg("NTBOT_DB_NAME"))
assert DB is not None
