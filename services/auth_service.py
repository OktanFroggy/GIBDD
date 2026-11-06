from typing import Any, Dict, Optional

import bcrypt

from database.db_connection import (
    execute_query,
    fetch_one,
    get_inspector_by_login,
)


class AuthService:
    def authenticate(
        self, login: str, password: str
    ) -> Optional[Dict[str, Any]]:
        inspector = get_inspector_by_login(login)
        if inspector is None or self.check_lockout(login):
            return None

        stored_hash = inspector["password_hash"]
        hash_bytes = (
            stored_hash.encode("utf-8")
            if isinstance(stored_hash, str)
            else bytes(stored_hash)
        )
        try:
            password_matches = bcrypt.checkpw(
                password.encode("utf-8"), hash_bytes
            )
        except ValueError as error:
            raise ValueError("Некорректный хеш пароля в базе данных") from error

        if not password_matches:
            execute_query(
                """
                UPDATE inspectors
                SET failed_attempts = CASE
                        WHEN failed_attempts + 1 >= 3 THEN 0
                        ELSE failed_attempts + 1
                    END,
                    lockout_until = CASE
                        WHEN failed_attempts + 1 >= 3
                            THEN NOW() + INTERVAL '1 minute'
                        ELSE lockout_until
                    END
                WHERE id = %s
                """,
                (inspector["id"],),
            )
            return None

        execute_query(
            """
            UPDATE inspectors
            SET failed_attempts = 0, lockout_until = NULL
            WHERE id = %s
            """,
            (inspector["id"],),
        )
        return inspector

    def check_lockout(self, login: str) -> bool:
        result = fetch_one(
            """
            SELECT lockout_until > NOW() AS is_locked
            FROM inspectors
            WHERE login = %s
            """,
            (login,),
        )
        return bool(result and result["is_locked"])

    def change_password(self, login: str, new_password: str) -> bool:
        password_bytes = new_password.encode("utf-8")
        if not password_bytes:
            raise ValueError("Пароль не должен быть пустым")
        if len(password_bytes) > 72:
            raise ValueError("Пароль не должен превышать 72 байта в UTF-8")

        password_hash = bcrypt.hashpw(
            password_bytes, bcrypt.gensalt()
        ).decode("utf-8")
        updated_rows = execute_query(
            """
            UPDATE inspectors
            SET password_hash = %s,
                must_change_password = FALSE,
                failed_attempts = 0,
                lockout_until = NULL
            WHERE login = %s
            """,
            (password_hash, login),
        )
        return updated_rows == 1
