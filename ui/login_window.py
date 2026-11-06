from typing import Any

import psycopg2
from PyQt6.QtCore import QEvent, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services.auth_service import AuthService


class LoginWindow(QWidget):
    authenticated = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Авторизация")
        self.setMinimumWidth(360)
        self.auth_service = AuthService()

        title = QLabel("Вход в систему")
        title.setObjectName("title")

        self.login_input = QLineEdit()
        self.login_input.setPlaceholderText("Введите логин")
        self.login_input.setClearButtonEnabled(True)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Введите пароль")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.addRow("Логин:", self.login_input)
        form_layout.addRow("Пароль:", self.password_input)

        self.login_button = QPushButton("Войти")
        self.login_button.setDefault(True)
        self.login_button.clicked.connect(self._authenticate)
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.login_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(20)
        layout.addWidget(title)
        layout.addLayout(form_layout)
        layout.addLayout(button_layout)

        self.inactivity_timer = QTimer(self)
        self.inactivity_timer.setInterval(60_000)
        self.inactivity_timer.setSingleShot(True)
        self.inactivity_timer.timeout.connect(self._handle_inactivity)
        self.inactivity_timer.start()

        self._activity_filter_installed = False
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            self._activity_filter_installed = True

        self.setStyleSheet(
            """
            QWidget {
                background-color: #f5f7fa;
                color: #263445;
                font-size: 14px;
            }
            QLabel#title {
                color: #243b53;
                font-size: 22px;
                font-weight: 600;
            }
            QLineEdit {
                background-color: white;
                border: 1px solid #cbd2d9;
                border-radius: 5px;
                padding: 8px;
            }
            QLineEdit:focus {
                border: 1px solid #2680c2;
            }
            QPushButton {
                background-color: #2680c2;
                border: none;
                border-radius: 5px;
                color: white;
                min-width: 100px;
                padding: 9px 16px;
            }
            QPushButton:hover {
                background-color: #186faf;
            }
            QPushButton:pressed {
                background-color: #0f609b;
            }
            """
        )

    def _authenticate(self) -> None:
        login = self.login_input.text().strip()
        password = self.password_input.text()

        try:
            if self.auth_service.check_lockout(login):
                QMessageBox.warning(
                    self, "Вход заблокирован", "Попробуйте позже."
                )
                return

            inspector = self.auth_service.authenticate(login, password)
        except psycopg2.Error as error:
            QMessageBox.critical(
                self,
                "Ошибка базы данных",
                f"Не удалось выполнить вход: {error}",
            )
            return
        except ValueError as error:
            QMessageBox.critical(self, "Ошибка авторизации", str(error))
            return

        if inspector is not None:
            QMessageBox.information(self, "Авторизация", "Успешный вход")
            self.inactivity_timer.stop()
            self._remove_activity_filter()
            self.authenticated.emit()
            return

        try:
            is_locked = self.auth_service.check_lockout(login)
        except psycopg2.Error as error:
            QMessageBox.critical(
                self,
                "Ошибка базы данных",
                f"Не удалось проверить блокировку: {error}",
            )
            return

        if is_locked:
            QMessageBox.warning(self, "Вход заблокирован", "Попробуйте позже.")
        else:
            QMessageBox.warning(
                self, "Ошибка авторизации", "Неверный логин или пароль."
            )

    def _handle_inactivity(self) -> None:
        self.login_input.clear()
        self.password_input.clear()
        QMessageBox.information(self, "Сессия", "Сессия истекла")
        self.inactivity_timer.start()

    def prepare_for_login(self) -> None:
        self.login_input.clear()
        self.password_input.clear()
        self._install_activity_filter()
        self.inactivity_timer.start()
        self.show()

    def _install_activity_filter(self) -> None:
        if self._activity_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            self._activity_filter_installed = True

    def _remove_activity_filter(self) -> None:
        if not self._activity_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._activity_filter_installed = False

    def eventFilter(self, watched: Any, event: QEvent) -> bool:
        activity_events = {
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseMove,
            QEvent.Type.KeyPress,
            QEvent.Type.TouchBegin,
        }
        if event.type() in activity_events:
            self.inactivity_timer.start()
        return super().eventFilter(watched, event)
