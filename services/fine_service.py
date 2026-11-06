import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List

import psycopg2

from database.db_connection import execute_query, fetch_one


def import_fines_from_json(json_file_path: str) -> Dict[str, Any]:
    """Import fines from a JSON array, returning counts and per-record errors."""
    path = Path(json_file_path)
    try:
        with path.open("r", encoding="utf-8") as json_file:
            data = json.load(json_file)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError(
            f"Не удалось прочитать JSON-файл {path}: {error}"
        ) from error

    if not isinstance(data, list):
        raise ValueError("JSON должен содержать список штрафов.")

    result: Dict[str, Any] = {
        "total": len(data),
        "imported": 0,
        "duplicates": 0,
        "errors": [],
    }

    for index, record in enumerate(data, start=1):
        try:
            if not isinstance(record, dict):
                raise ValueError("Запись должна быть JSON-объектом.")

            fine_id = str(record.get("fine_id", "")).strip()
            if not fine_id:
                raise ValueError("Не задан обязательный fine_id.")

            amount = Decimal(str(record["amount"]))
            issue_date = date.fromisoformat(str(record["issue_date"]))
            license_number = str(record.get("license_number") or "").strip()
            vehicle_number = str(record.get("vehicle_number") or "").strip()
            photo_url = record.get("photo_url")

            driver_guid = None
            if license_number:
                driver = fetch_one(
                    """
                    SELECT guid
                    FROM drivers
                    WHERE license_number = %s AND is_deleted = FALSE
                    """,
                    (license_number,),
                )
                if driver is not None:
                    driver_guid = driver["guid"]

            inserted_rows = execute_query(
                """
                INSERT INTO fines (
                    source_fine_id, driver_guid, vehicle_number,
                    amount, issue_date, photo_url
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_fine_id) DO NOTHING
                """,
                (
                    fine_id,
                    driver_guid,
                    vehicle_number or None,
                    amount,
                    issue_date,
                    photo_url or None,
                ),
            )
            if inserted_rows:
                result["imported"] += 1
            else:
                result["duplicates"] += 1
        except (
            KeyError,
            TypeError,
            ValueError,
            InvalidOperation,
            psycopg2.Error,
        ) as error:
            fine_id = record.get("fine_id") if isinstance(record, dict) else None
            result["errors"].append(
                {
                    "record": index,
                    "fine_id": fine_id,
                    "error": str(error),
                }
            )

    return result
