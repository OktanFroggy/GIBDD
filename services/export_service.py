import csv
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Tuple

from database.db_connection import execute_query, fetch_all


def export_debts_to_fssp() -> Tuple[int, int]:
    """Export overdue unpaid fines, then mark the exported records as sent."""
    debts = fetch_all(
        """
        SELECT
            f.id,
            CONCAT_WS(
                ' ',
                d.last_name,
                d.first_name,
                NULLIF(d.middle_name, '')
            ) AS full_name,
            d.passport,
            f.amount,
            f.issue_date
        FROM fines AS f
        JOIN drivers AS d ON d.guid = f.driver_guid
        WHERE f.status = 'не оплачен'
          AND f.issue_date <= CURRENT_DATE - INTERVAL '6 months'
          AND f.is_deleted = FALSE
          AND d.is_deleted = FALSE
        ORDER BY f.issue_date, f.id
        """
    )
    if not debts:
        return 0, 0

    export_dir = Path(__file__).resolve().parent.parent / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"fssp_debts_{timestamp}_{uuid.uuid4().hex[:8]}.csv"
    destination_path = export_dir / filename
    temp_path: str | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            dir=export_dir,
            prefix=".fssp_",
            suffix=".tmp",
            delete=False,
        ) as csv_file:
            temp_path = csv_file.name
            writer = csv.writer(csv_file, delimiter=";")
            writer.writerow(
                ["ID_штрафа", "ФИО", "Паспорт", "Сумма", "Дата"]
            )
            for debt in debts:
                writer.writerow(
                    [
                        debt["id"],
                        debt["full_name"],
                        debt["passport"],
                        debt["amount"],
                        debt["issue_date"],
                    ]
                )

        os.replace(temp_path, destination_path)
        temp_path = None
    finally:
        if temp_path is not None:
            try:
                os.remove(temp_path)
            except FileNotFoundError:
                pass

    exported_ids = [debt["id"] for debt in debts]
    updated_rows = execute_query(
        """
        UPDATE fines
        SET status = 'передан в ФССП'
        WHERE id = ANY(%s)
          AND status = 'не оплачен'
          AND is_deleted = FALSE
        """,
        (exported_ids,),
    )
    if updated_rows != len(exported_ids):
        raise RuntimeError(
            "CSV сформирован, но статус обновлён не для всех штрафов "
            f"({updated_rows} из {len(exported_ids)}). Файл: {destination_path}"
        )

    return 1, len(exported_ids)
