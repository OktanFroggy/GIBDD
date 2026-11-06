import sys

import psycopg2

from database.db_connection import fetch_all


def main() -> int:
    try:
        inspectors = fetch_all("SELECT login FROM inspectors;")
    except psycopg2.OperationalError as error:
        print(f"Не удалось подключиться к базе данных: {error}", file=sys.stderr)
        return 1

    if not inspectors:
        print("Подключение успешно. В таблице inspectors нет записей.")
        return 0

    print("Логины инспекторов:")
    for inspector in inspectors:
        print(inspector["login"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
