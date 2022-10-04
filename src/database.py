"""This module abstracts the database driver logic for accessing the PUG data.
"""

from abc import ABC, abstractmethod
import asyncio
import sqlite3

import psycopg2

from config import cfg


class DbDriver(ABC):
    """Abstract DB driver base. All DB drivers should inherit from this."""
    def __init__(self):
        self.lock = asyncio.Lock()
        self.conn = None
        self.open_database()

    def __del__(self):
        self.close_database()

    def open_database(self):
        """Open the DB connection, and create the DB if it doesn't exist yet.
        """
        self.table = cfg("NTBOT_DB_TABLE")
        cur = self.conn.cursor()
        # NOTE: Purges all DB data for debug.
        if cfg("NTBOT_DEBUG"):
            cur.execute(f"DROP TABLE IF EXISTS {self.table};")
        cur.execute(f"""CREATE TABLE IF NOT EXISTS {self.table} (
                           id serial PRIMARY KEY,
                           user_id numeric,
                           is_queued boolean DEFAULT false,
                           unique(user_id));""")
        self.conn.commit()
        cur.close()

    def close_database(self):
        """Close the DB if it was opened."""
        if hasattr(self, "conn"):
            self.conn.close()

    async def get_discord_user(self, discord_id=None):
        """Get the DB data of a specific user by their Discord ID integer.

           If discord_id is None, gets all users.
           Returns a list of 0 or more rows of data.
        """
        query = f"SELECT * FROM {self.table}"
        my_vars = None
        if discord_id is not None:
            query += " WHERE user_id = %s"
            my_vars = (discord_id,)
        res = await self._execute(query, my_vars)
        return [dict(zip(("db_row_id", "discord_id", "queued"), x)) for x in res]

    async def set_discord_user(self, discord_id: int, is_queued: bool):
        """Set the DB queued state of a specific user by their Discord ID.
        """
        await self._execute(f"""INSERT INTO {self.table} (user_id) VALUES (%s)
                            ON CONFLICT (user_id) DO UPDATE SET is_queued = %s;""",
                            (discord_id, is_queued))

    @abstractmethod
    async def _execute(self, query, my_vars=None):
        pass


class Sqlite3(DbDriver):
    """DB driver for SQLite 3."""
    def __init__(self):
        assert cfg("NTBOT_DB_DRIVER") == "sqlite3"
        super().__init__()

    def open_database(self):
        self.conn = sqlite3.connect(database=cfg("NTBOT_DB_NAME"))
        super().open_database()

    async def _execute(self, query, my_vars=None):
        async with self.lock:
            cur = self.conn.cursor()
            cur.execute(query, my_vars)
            res = cur.fetchall()
            self.conn.commit()
            cur.close()
        return res


class Postgres(DbDriver):
    """DB driver for Postgres."""
    def __init__(self):
        assert cfg("NTBOT_DB_DRIVER") == "postgres"
        super().__init__()

    def open_database(self):
        self.conn = psycopg2.connect(dbname=cfg("NTBOT_DB_NAME"),
                                     user=cfg("NTBOT_DB_USER"),
                                     password=cfg("NTBOT_DB_SECRET"),
                                     host=cfg("NTBOT_DB_HOST"),
                                     port=cfg("NTBOT_DB_PORT"))
        super().open_database()

    async def _execute(self, query, my_vars=None):
        async with self.lock:
            cur = self.conn.cursor()
            cur.execute(query, my_vars)
            try:
                res = cur.fetchall()
            except psycopg2.ProgrammingError as err:
                if str(err) == "no results to fetch":  # TODO: confirm this works
                    res = []
                else:
                    raise err
            self.conn.commit()
            cur.close()
        return res
