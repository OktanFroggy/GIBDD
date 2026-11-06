from pathlib import Path

import psycopg2

from services.fine_service import import_fines_from_json


def main() -> int:
    json_path = Path(__file__).with_name("test_fines.json")
    try:
        result = import_fines_from_json(str(json_path))
    except (OSError, ValueError) as error:
        print(f"Ошибка импорта: {error}")
        return 1
    except psycopg2.Error as error:
        print(f"Ошибка базы данных: {error}")
        return 1

    print(
        "Импорт завершён. "
        f"Всего: {result['total']}; "
        f"импортировано: {result['imported']}; "
        f"дубликатов: {result['duplicates']}; "
        f"ошибок: {len(result['errors'])}."
    )
    for item in result["errors"]:
        print(
            f"Запись {item['record']} "
            f"(fine_id={item['fine_id']}): {item['error']}"
        )

    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
