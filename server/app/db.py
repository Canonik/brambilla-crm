import contextlib
import os
import threading

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import config

_pool: ConnectionPool | None = None
_lock = threading.Lock()


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                _pool = ConnectionPool(
                    config.DATABASE_URL,
                    min_size=config.POOL_MIN,
                    max_size=config.POOL_MAX,
                    kwargs={"row_factory": dict_row, "autocommit": False},
                    open=True,
                    timeout=30,
                )
    return _pool


@contextlib.contextmanager
def connection():
    with pool().connection() as conn:
        yield conn


def init_schema() -> None:
    here = os.path.dirname(__file__)
    with open(os.path.join(here, "schema.sql"), encoding="utf-8") as fh:
        ddl = fh.read()
    with connection() as conn:
        conn.execute(ddl)
        conn.commit()
    from .defaults import ensure_defaults
    ensure_defaults()


def close() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
