from pathlib import Path
from typing import Any, Dict

import psycopg2
from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from database.db_connection import (
    execute_query,
    fetch_all,
    get_unmatched_fines,
)
from services.export_service import export_debts_to_fssp
from ui.driver_form import DriverForm


class DriverDetailsDialog(QDialog):
    def __init__(
        self, driver: Dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        full_name = " ".join(
            str(driver[field])
            for field in ("last_name", "first_name", "middle_name")
            if driver.get(field)
        )
        self.setWindowTitle(f"Водитель: {full_name}")
        self.resize(760, 560)

        self.photo_label = QLabel()
        self.photo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo_label.setFixedSize(180, 240)
        self.photo_label.setStyleSheet(
            "QLabel { border: 1px solid #cbd2d9; background: white; }"
        )
        photo_path = Path(__file__).resolve().parent.parent / driver["photo_path"]
        photo = QPixmap(str(photo_path))
        if photo.isNull():
            self.photo_label.setText("Фото недоступно")
        else:
            self.photo_label.setPixmap(
                photo.scaled(
                    self.photo_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        details_layout = QFormLayout()
        detail_fields = (
            ("Дата рождения", "birth_date"),
            ("Водительское удостоверение", "license_number"),
            ("Паспорт", "passport"),
            ("Телефон", "phone"),
            ("Email", "email"),
            ("Адрес регистрации", "reg_address"),
            ("Адрес проживания", "living_address"),
            ("Место работы", "workplace"),
            ("Должность", "position"),
            ("Замечания", "notes"),
        )
        for label, field in detail_fields:
            value = driver.get(field)
            details_layout.addRow(
                f"{label}:",
                QLabel("" if value is None else str(value)),
            )

        identity_layout = QVBoxLayout()
        identity_layout.addWidget(QLabel(f"<b>{full_name}</b>"))
        identity_layout.addWidget(
            QLabel(
                f"Регистрация: {driver.get('reg_city') or ''}"
            )
        )
        identity_layout.addWidget(
            QLabel(
                f"Проживание: {driver.get('living_city') or ''}"
            )
        )
        identity_layout.addLayout(details_layout)
        identity_layout.addStretch()

        identity_row = QHBoxLayout()
        identity_row.addWidget(self.photo_label, alignment=Qt.AlignmentFlag.AlignTop)
        identity_row.addLayout(identity_layout, 1)

        self.fines_table = QTableWidget(0, 5)
        self.fines_table.setHorizontalHeaderLabels(
            ["ID", "Номер ТС", "Сумма", "Дата", "Статус"]
        )
        self.fines_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.fines_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.fines_table.horizontalHeader().setStretchLastSection(True)
        self.fines_table.setAlternatingRowColors(True)

        layout = QVBoxLayout(self)
        layout.addLayout(identity_row)
        layout.addWidget(QLabel("Штрафы водителя"))
        layout.addWidget(self.fines_table)

        fines = fetch_all(
            """
            SELECT id, vehicle_number, amount, issue_date, status
            FROM fines
            WHERE driver_guid = %s AND is_deleted = FALSE
            ORDER BY issue_date DESC, id DESC
            """,
            (driver["guid"],),
        )
        self.fines_table.setRowCount(len(fines))
        for row_index, fine in enumerate(fines):
            for column_index, field in enumerate(
                ("id", "vehicle_number", "amount", "issue_date", "status")
            ):
                value = fine[field]
                item = QTableWidgetItem("" if value is None else str(value))
                self.fines_table.setItem(row_index, column_index, item)
        self.fines_table.resizeColumnsToContents()


class MainWindow(QMainWindow):
    session_expired = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("База водителей")
        self.resize(900, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        self.tabs = QTabWidget()
        self.drivers_tab = QWidget()
        self.problem_fines_tab = QWidget()
        self.tabs.addTab(self.drivers_tab, "Водители")
        self.tabs.addTab(self.problem_fines_tab, "Проблемные штрафы")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.add_button = QPushButton("Добавить водителя")
        self.edit_button = QPushButton("Редактировать")
        self.delete_button = QPushButton("Удалить")
        self.export_button = QPushButton("Экспорт в ФССП")

        self.add_button.clicked.connect(self._open_driver_form)
        self.export_button.clicked.connect(self._export_to_fssp)
        self.edit_button.clicked.connect(self._edit_selected_driver)
        self.delete_button.clicked.connect(self._delete_selected_driver)

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(self.add_button)
        buttons_layout.addWidget(self.edit_button)
        buttons_layout.addWidget(self.delete_button)
        buttons_layout.addWidget(self.export_button)
        buttons_layout.addStretch()

        self.drivers_table = QTableWidget(0, 4)
        self.drivers_table.setHorizontalHeaderLabels(
            ["Фамилия", "Имя", "Телефон", "Email"]
        )
        self._configure_table(self.drivers_table)
        self.drivers_table.cellDoubleClicked.connect(
            self._open_selected_driver
        )

        drivers_layout = QVBoxLayout(self.drivers_tab)
        drivers_layout.setContentsMargins(12, 12, 12, 12)
        drivers_layout.setSpacing(12)
        drivers_layout.addLayout(buttons_layout)
        drivers_layout.addWidget(self.drivers_table)

        self.problem_fines_table = QTableWidget(0, 5)
        self.problem_fines_table.setHorizontalHeaderLabels(
            ["ID", "Номер ТС", "Сумма", "Дата", "Статус"]
        )
        self._configure_table(self.problem_fines_table)

        fines_layout = QVBoxLayout(self.problem_fines_tab)
        fines_layout.setContentsMargins(12, 12, 12, 12)
        fines_layout.addWidget(self.problem_fines_table)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(self.tabs)

        self.inactivity_timer = QTimer(self)
        self.inactivity_timer.setInterval(60_000)
        self.inactivity_timer.setSingleShot(True)
        self.inactivity_timer.timeout.connect(self._expire_session)
        self.inactivity_timer.start()

        self._activity_filter_installed = False
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            self._activity_filter_installed = True

        self._load_drivers()

    @staticmethod
    def _configure_table(table: QTableWidget) -> None:
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.horizontalHeader().setStretchLastSection(True)
        table.setAlternatingRowColors(True)

    def _load_drivers(self) -> None:
        drivers = fetch_all(
            """
            SELECT guid, last_name, first_name, phone, email
            FROM drivers
            WHERE is_deleted = FALSE
            ORDER BY last_name, first_name
            """
        )

        self.drivers_table.setRowCount(len(drivers))
        for row_index, driver in enumerate(drivers):
            for column_index, field in enumerate(
                ("last_name", "first_name", "phone", "email")
            ):
                value = driver[field]
                item = QTableWidgetItem("" if value is None else str(value))
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, str(driver["guid"]))
                self.drivers_table.setItem(row_index, column_index, item)

        self.drivers_table.resizeColumnsToContents()

    def _load_problem_fines(self) -> None:
        fines = get_unmatched_fines()
        self.problem_fines_table.setRowCount(len(fines))
        for row_index, fine in enumerate(fines):
            for column_index, field in enumerate(
                ("id", "vehicle_number", "amount", "issue_date", "status")
            ):
                value = fine[field]
                item = QTableWidgetItem("" if value is None else str(value))
                self.problem_fines_table.setItem(row_index, column_index, item)
        self.problem_fines_table.resizeColumnsToContents()

    def _on_tab_changed(self, index: int) -> None:
        if self.tabs.widget(index) is not self.problem_fines_tab:
            return
        try:
            self._load_problem_fines()
        except psycopg2.Error as error:
            QMessageBox.critical(
                self,
                "Ошибка базы данных",
                f"Не удалось загрузить проблемные штрафы: {error}",
            )

    def _open_selected_driver(self, row: int, _column: int) -> None:
        first_cell = self.drivers_table.item(row, 0)
        if first_cell is None:
            return

        driver_guid = first_cell.data(Qt.ItemDataRole.UserRole)
        try:
            driver_rows = fetch_all(
                """
                SELECT *
                FROM drivers
                WHERE guid = %s AND is_deleted = FALSE
                """,
                (driver_guid,),
            )
            if not driver_rows:
                QMessageBox.warning(
                    self, "Водитель не найден", "Запись уже удалена."
                )
                self._load_drivers()
                return

            dialog = DriverDetailsDialog(driver_rows[0], self)
            dialog.exec()
        except psycopg2.Error as error:
            QMessageBox.critical(
                self,
                "Ошибка базы данных",
                f"Не удалось загрузить карточку водителя: {error}",
            )

    def _show_placeholder(self, action: str) -> None:
        QMessageBox.information(
            self, action, f"Функция «{action}» будет реализована позже."
        )

    def _open_driver_form(self) -> None:
        dialog = DriverForm(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._refresh_drivers()

    def _open_driver_form_for_selected(self) -> None:
        first_cell = self.drivers_table.item(
            self.drivers_table.currentRow(), 0
        )
        if first_cell is None:
            dialog = DriverForm(self)
        else:
            driver_guid = first_cell.data(Qt.ItemDataRole.UserRole)
            try:
                drivers = fetch_all(
                    """
                    SELECT *
                    FROM drivers
                    WHERE guid = %s AND is_deleted = FALSE
                    """,
                    (driver_guid,),
                )
            except psycopg2.Error as error:
                QMessageBox.critical(
                    self,
                    "Ошибка базы данных",
                    f"Не удалось загрузить данные водителя: {error}",
                )
                return

            if not drivers:
                QMessageBox.warning(
                    self, "Водитель не найден", "Запись уже удалена."
                )
                self._load_drivers()
                return

            dialog = DriverForm(self, driver_data=drivers[0])

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._refresh_drivers()

    def _refresh_drivers(self) -> None:
        try:
            self._load_drivers()
        except psycopg2.Error as error:
            QMessageBox.critical(
                self,
                "Ошибка базы данных",
                f"Данные сохранены, но список не удалось обновить: {error}",
            )

    def _edit_selected_driver(self) -> None:
        row = self.drivers_table.currentRow()
        first_cell = self.drivers_table.item(row, 0) if row >= 0 else None
        if first_cell is None:
            QMessageBox.warning(
                self,
                "Водитель не выбран",
                "Выберите водителя для редактирования.",
            )
            return
        self._open_driver_form_for_selected()

    def _delete_selected_driver(self) -> None:
        row = self.drivers_table.currentRow()
        first_cell = self.drivers_table.item(row, 0) if row >= 0 else None
        if first_cell is None:
            QMessageBox.warning(
                self,
                "Водитель не выбран",
                "Выберите водителя для удаления.",
            )
            return

        driver_guid = first_cell.data(Qt.ItemDataRole.UserRole)
        full_name = " ".join(
            item.text()
            for item in (
                self.drivers_table.item(row, 0),
                self.drivers_table.item(row, 1),
            )
            if item is not None and item.text()
        )
        answer = QMessageBox.question(
            self,
            "Подтверждение удаления",
            f"Удалить водителя {full_name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            deleted_rows = execute_query(
                """
                UPDATE drivers
                SET is_deleted = TRUE
                WHERE guid = %s AND is_deleted = FALSE
                """,
                (driver_guid,),
            )
            if deleted_rows == 0:
                QMessageBox.warning(
                    self, "Водитель не найден", "Запись уже удалена."
                )
            self._refresh_drivers()
        except psycopg2.Error as error:
            QMessageBox.critical(
                self,
                "Ошибка базы данных",
                f"Не удалось удалить водителя: {error}",
            )

    def _export_to_fssp(self) -> None:
        try:
            file_count, debt_count = export_debts_to_fssp()
        except (OSError, psycopg2.Error, RuntimeError) as error:
            QMessageBox.critical(
                self,
                "Ошибка экспорта",
                f"Не удалось выполнить экспорт в ФССП: {error}",
            )
            return

        QMessageBox.information(
            self,
            "Экспорт в ФССП",
            f"Сформировано файлов: {file_count}. "
            f"Отправлено штрафов: {debt_count}.",
        )

    def eventFilter(self, watched: Any, event: QEvent) -> bool:
        activity_events = {
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonDblClick,
            QEvent.Type.MouseMove,
            QEvent.Type.KeyPress,
            QEvent.Type.Wheel,
            QEvent.Type.TouchBegin,
        }
        if event.type() in activity_events and self.isVisible():
            self.inactivity_timer.start()
        return super().eventFilter(watched, event)

    def _expire_session(self) -> None:
        self.inactivity_timer.stop()
        self._remove_activity_filter()
        self.hide()
        self.session_expired.emit()
        self.close()

    def _remove_activity_filter(self) -> None:
        if not self._activity_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._activity_filter_installed = False

    def closeEvent(self, event: QCloseEvent) -> None:
        self.inactivity_timer.stop()
        self._remove_activity_filter()
        super().closeEvent(event)
