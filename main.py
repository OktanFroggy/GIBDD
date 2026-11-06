import sys

import psycopg2
from PyQt6.QtWidgets import QApplication, QMessageBox

from ui.login_window import LoginWindow
from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)

    login_window = LoginWindow()
    main_window: MainWindow | None = None

    def open_main_window() -> None:
        nonlocal main_window
        try:
            main_window = MainWindow()
        except psycopg2.Error as error:
            QMessageBox.critical(
                login_window,
                "Ошибка базы данных",
                f"Не удалось загрузить список водителей: {error}",
            )
            login_window.prepare_for_login()
            return

        main_window.session_expired.connect(return_to_login)
        main_window.show()
        login_window.close()

    def return_to_login() -> None:
        login_window.prepare_for_login()
        QMessageBox.information(
            login_window,
            "Сессия завершена",
            "Сессия истекла из-за неактивности",
        )

    login_window.authenticated.connect(open_main_window)
    login_window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
