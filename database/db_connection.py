from contextlib import closing
from typing import Any, Dict, List, Optional, Sequence

import psycopg2
from psycopg2.extras import RealDictCursor

from config import (
    DB_CONNECT_TIMEOUT,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
)


def get_connection() -> psycopg2.extensions.connection:
    """Open and return a PostgreSQL connection using config.py settings."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=DB_CONNECT_TIMEOUT,
    )


def execute_query(
    query: str, params: Optional[Sequence[Any]] = None
) -> int:
    """Execute a parameterized INSERT, UPDATE, or DELETE and return row count."""
    with closing(get_connection()) as connection:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.rowcount


def fetch_one(
    query: str, params: Optional[Sequence[Any]] = None
) -> Optional[Dict[str, Any]]:
    """Run a parameterized SELECT and return one row as a dictionary."""
    with closing(get_connection()) as connection:
        with connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
                return dict(row) if row is not None else None


def fetch_all(
    query: str, params: Optional[Sequence[Any]] = None
) -> List[Dict[str, Any]]:
    """Run a parameterized SELECT and return all rows as dictionaries."""
    with closing(get_connection()) as connection:
        with connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]


def get_inspector_by_login(login: str) -> Optional[Dict[str, Any]]:
    """Return an active inspector record for authentication."""
    return fetch_one(
        """
        SELECT id, login, password_hash, failed_attempts,
               lockout_until, must_change_password
        FROM inspectors
        WHERE login = %s
        """,
        (login,),
    )


def get_driver_by_guid(guid: str) -> Optional[Dict[str, Any]]:
    """Return a non-deleted driver by GUID."""
    return fetch_one(
        "SELECT * FROM drivers WHERE guid = %s AND is_deleted = FALSE",
        (guid,),
    )


def get_unmatched_fines() -> List[Dict[str, Any]]:
    """Return non-deleted fines that have not been matched to a driver."""
    return fetch_all(
        """
        SELECT id, source_fine_id, vehicle_number, amount, issue_date,
               status, photo_url
        FROM fines
        WHERE driver_guid IS NULL AND is_deleted = FALSE
        ORDER BY issue_date DESC, id
        """
    )
