import os
import re
import shutil
import tempfile
import uuid
from typing import Any, Dict, Optional, Tuple

import psycopg2
from PIL import Image, UnidentifiedImageError
from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCompleter,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from database.db_connection import execute_query


CITY_NAMES = [
    "Москва",
    "Санкт-Петербург",
    "Новосибирск",
    "Екатеринбург",
    "Казань",
]
MAX_PHOTO_SIZE = 2 * 1024 * 1024
EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
)


def validate_photo(file_path: str) -> Tuple[bool, str]:
    """Validate a JPG/PNG image no larger than 2 MB with a portrait 3:4 ratio."""
    extension = os.path.splitext(file_path)[1].lower()
    if extension not in {".jpg", ".jpeg", ".png"}:
        return False, "Выберите файл JPG или PNG."

    try:
        if os.path.getsize(file_path) > MAX_PHOTO_SIZE:
            return False, "Размер фотографии не должен превышать 2 МБ."

        with Image.open(file_path) as image:
            expected_format = "PNG" if extension == ".png" else "JPEG"
            if image.format != expected_format:
                return False, "Формат файла не соответствует его расширению."

            width, height = image.size
            image.verify()
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
        return False, "Не удалось прочитать изображение. Проверьте файл."

    if height <= width:
        return False, "Изображение должно быть вертикальным."

    if abs(width / height - 0.75) > 0.02:
        return False, "Пропорции фотографии должны быть 3:4."

    return True, "OK"


class DriverForm(QDialog):
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        driver_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(parent)
        self.driver_data = driver_data
        self.driver_guid = (
            str(driver_data["guid"]) if driver_data is not None else None
        )
        self.is_editing = driver_data is not None
        self.setWindowTitle(
            "Редактирование водителя" if self.is_editing else "Добавление водителя"
        )
        self.resize(620, 760)
        self.photo_path: Optional[str] = None
        self.photo_changed = False
        self._validated_widgets: list[QWidget] = []

        self.last_name_input = QLineEdit()
        self.first_name_input = QLineEdit()
        self.middle_name_input = QLineEdit()
        self.birth_date_input = QDateEdit()
        self.birth_date_input.setCalendarPopup(True)
        self.birth_date_input.setDisplayFormat("dd.MM.yyyy")
        self.birth_date_input.setMinimumDate(QDate(1900, 1, 1))
        self.birth_date_input.setSpecialValueText("Выберите дату")
        self.birth_date_input.setDate(self.birth_date_input.minimumDate())
        self.license_number_input = QLineEdit()
        self.passport_input = QLineEdit()
        self.reg_city_input = self._create_city_input()
        self.reg_address_input = QLineEdit()
        self.living_city_input = self._create_city_input()
        self.living_address_input = QLineEdit()
        self.workplace_input = QLineEdit()
        self.position_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.email_input = QLineEdit()
        self.notes_input = QLineEdit()

        for field in (
            self.last_name_input,
            self.first_name_input,
            self.middle_name_input,
            self.birth_date_input,
            self.license_number_input,
            self.passport_input,
            self.reg_city_input,
            self.reg_address_input,
            self.living_city_input,
            self.living_address_input,
            self.phone_input,
            self.email_input,
        ):
            self._validated_widgets.append(field)

        self.photo_preview = QLabel("Фото не выбрано")
        self.photo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo_preview.setFixedSize(150, 200)
        self.photo_preview.setStyleSheet(
            "QLabel { border: 1px solid #cbd2d9; background: white; }"
        )
        self.choose_photo_button = QPushButton("Выбрать фото")
        self.choose_photo_button.clicked.connect(self._choose_photo)
        photo_layout = QHBoxLayout()
        photo_layout.addWidget(self.photo_preview)
        photo_layout.addWidget(
            self.choose_photo_button,
            alignment=Qt.AlignmentFlag.AlignTop,
        )
        photo_layout.addStretch()

        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        form_layout.addRow(
            self._required_label("Фамилия"), self.last_name_input
        )
        form_layout.addRow(self._required_label("Имя"), self.first_name_input)
        form_layout.addRow(
            self._required_label("Отчество"), self.middle_name_input
        )
        form_layout.addRow(
            self._required_label("Дата рождения"), self.birth_date_input
        )
        form_layout.addRow(
            self._required_label("Номер водительского удостоверения"),
            self.license_number_input,
        )
        form_layout.addRow(
            self._required_label("Паспорт"), self.passport_input
        )
        form_layout.addRow(
            self._required_label("Город регистрации"), self.reg_city_input
        )
        form_layout.addRow(
            self._required_label("Адрес регистрации (улица/дом)"),
            self.reg_address_input,
        )
        form_layout.addRow(
            self._required_label("Город проживания"), self.living_city_input
        )
        form_layout.addRow(
            self._required_label("Адрес проживания (улица/дом)"),
            self.living_address_input,
        )
        form_layout.addRow("Место работы", self.workplace_input)
        form_layout.addRow("Должность", self.position_input)
        form_layout.addRow(self._required_label("Телефон"), self.phone_input)
        form_layout.addRow(self._required_label("Email"), self.email_input)
        form_layout.addRow("Замечания", self.notes_input)
        form_layout.addRow(
            self._required_label("Фотография"), photo_layout
        )

        form_widget = QWidget()
        form_widget.setLayout(form_layout)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(form_widget)

        self.save_button = QPushButton("Сохранить")
        self.cancel_button = QPushButton("Отмена")
        self.save_button.clicked.connect(self._validate_and_report)
        self.cancel_button.clicked.connect(self.reject)

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.save_button)
        buttons_layout.addWidget(self.cancel_button)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll_area)
        layout.addLayout(buttons_layout)

        if driver_data is not None:
            self._populate_from_driver(driver_data)

    @staticmethod
    def _required_label(text: str) -> QLabel:
        return QLabel(f"{text} *")

    @staticmethod
    def _create_city_input() -> QLineEdit:
        city_input = QLineEdit()
        completer = QCompleter(CITY_NAMES, city_input)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        city_input.setCompleter(completer)
        return city_input

    def _choose_photo(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите фотографию водителя",
            "",
            "Изображения (*.jpg *.jpeg *.png)",
        )
        if not file_path:
            return

        is_valid, message = validate_photo(file_path)
        if not is_valid:
            self.photo_path = None
            self.photo_preview.setPixmap(QPixmap())
            self.photo_preview.setText("Фото не выбрано")
            self.choose_photo_button.setStyleSheet("")
            QMessageBox.warning(self, "Некорректное фото", message)
            return

        self.photo_path = file_path
        self.photo_changed = True
        preview = QPixmap(file_path)
        self.photo_preview.setText("")
        self.photo_preview.setPixmap(
            preview.scaled(
                self.photo_preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _validate_and_report(self) -> None:
        invalid_widgets = []
        for widget in self._validated_widgets:
            value = (
                widget.date().toString("yyyy-MM-dd")
                if isinstance(widget, QDateEdit)
                else widget.text().strip()
            )
            is_invalid = not value
            if isinstance(widget, QDateEdit):
                is_invalid = widget.date() == widget.minimumDate()
            if widget is self.email_input and value:
                is_invalid = EMAIL_PATTERN.match(value) is None

            widget.setStyleSheet(
                "border: 1px solid #d64545;" if is_invalid else ""
            )
            if is_invalid:
                invalid_widgets.append(widget)

        if self.photo_path is None:
            invalid_widgets.append(self.choose_photo_button)
            self.choose_photo_button.setStyleSheet("border: 1px solid #d64545;")
        else:
            is_valid, message = validate_photo(self.photo_path)
            if not is_valid:
                invalid_widgets.append(self.choose_photo_button)
                self.choose_photo_button.setStyleSheet(
                    "border: 1px solid #d64545;"
                )
                QMessageBox.warning(self, "Некорректное фото", message)
                return
            self.choose_photo_button.setStyleSheet("")

        if invalid_widgets:
            QMessageBox.warning(
                self,
                "Проверьте данные",
                "Заполните обязательные поля и укажите корректный email.",
            )
            invalid_widgets[0].setFocus()
            return

        self._save_driver()

    def _save_driver(self) -> None:
        driver_guid = self.driver_guid or str(uuid.uuid4())
        relative_photo_path = (
            self.driver_data["photo_path"]
            if self.driver_data is not None and not self.photo_changed
            else f"resources/photos/{driver_guid}.jpg"
        )
        project_root = os.path.dirname(os.path.dirname(__file__))
        photos_dir = os.path.join(project_root, "resources", "photos")
        absolute_photo_path = os.path.join(
            project_root, *relative_photo_path.split("/")
        )
        staged_photo_path: Optional[str] = None
        backup_photo_path: Optional[str] = None
        photo_installed = False

        if not self.is_editing or self.photo_changed:
            try:
                os.makedirs(photos_dir, exist_ok=True)
                descriptor, staged_photo_path = tempfile.mkstemp(
                    suffix=".jpg", dir=photos_dir
                )
                os.close(descriptor)
                self._save_photo_as_jpeg(
                    self.photo_path or "",
                    staged_photo_path,
                )

                if self.is_editing and os.path.exists(absolute_photo_path):
                    backup_descriptor, backup_photo_path = tempfile.mkstemp(
                        suffix=".bak", dir=photos_dir
                    )
                    os.close(backup_descriptor)
                    shutil.copy2(absolute_photo_path, backup_photo_path)

                os.replace(staged_photo_path, absolute_photo_path)
                staged_photo_path = None
                photo_installed = True
            except (
                OSError,
                UnidentifiedImageError,
                Image.DecompressionBombError,
            ) as error:
                self._cleanup_photo_files(
                    staged_photo_path,
                    backup_photo_path,
                    restore_path=(
                        absolute_photo_path
                        if self.is_editing and photo_installed
                        else None
                    ),
                )
                QMessageBox.critical(
                    self,
                    "Ошибка сохранения фото",
                    f"Не удалось сохранить фотографию: {error}",
                )
                return

        driver_values = (
            self.last_name_input.text().strip(),
            self.first_name_input.text().strip(),
            self.middle_name_input.text().strip(),
            self.birth_date_input.date().toPyDate(),
            self.license_number_input.text().strip(),
            self.passport_input.text().strip(),
            self.reg_city_input.text().strip(),
            self.reg_address_input.text().strip(),
            self.living_city_input.text().strip(),
            self.living_address_input.text().strip(),
            self.workplace_input.text().strip() or None,
            self.position_input.text().strip() or None,
            self.phone_input.text().strip(),
            self.email_input.text().strip(),
            relative_photo_path,
            self.notes_input.text().strip() or None,
        )
        try:
            if self.is_editing:
                updated_rows = execute_query(
                    """
                    UPDATE drivers
                    SET last_name = %s,
                        first_name = %s,
                        middle_name = %s,
                        birth_date = %s,
                        license_number = %s,
                        passport = %s,
                        reg_city = %s,
                        reg_address = %s,
                        living_city = %s,
                        living_address = %s,
                        workplace = %s,
                        position = %s,
                        phone = %s,
                        email = %s,
                        photo_path = %s,
                        notes = %s
                    WHERE guid = %s AND is_deleted = FALSE
                    """,
                    (*driver_values, driver_guid),
                )
                rows_affected = updated_rows
            else:
                inserted_rows = execute_query(
                    """
                    INSERT INTO drivers (
                        guid, last_name, first_name, middle_name, birth_date,
                        license_number, passport, reg_city, reg_address,
                        living_city, living_address, workplace, position,
                        phone, email, photo_path, notes
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (driver_guid, *driver_values),
                )
                rows_affected = inserted_rows
        except psycopg2.Error as error:
            self._cleanup_photo_files(
                staged_photo_path,
                backup_photo_path,
                restore_path=(
                    absolute_photo_path
                    if self.is_editing and photo_installed
                    else None
                ),
                remove_path=(
                    absolute_photo_path
                    if photo_installed
                    and (
                        not self.is_editing
                        or backup_photo_path is None
                    )
                    else None
                ),
            )
            QMessageBox.critical(
                self,
                "Ошибка базы данных",
                f"Не удалось сохранить данные водителя: {error}",
            )
            return

        if rows_affected != 1:
            self._cleanup_photo_files(
                staged_photo_path,
                backup_photo_path,
                restore_path=(
                    absolute_photo_path
                    if self.is_editing and photo_installed
                    else None
                ),
                remove_path=(
                    absolute_photo_path
                    if photo_installed
                    and (
                        not self.is_editing
                        or backup_photo_path is None
                    )
                    else None
                ),
            )
            QMessageBox.critical(
                self,
                "Ошибка сохранения",
                "Не удалось сохранить запись водителя.",
            )
            return

        if backup_photo_path is not None:
            self._remove_saved_photo(backup_photo_path)

        QMessageBox.information(
            self,
            "Успех",
            "Данные водителя успешно обновлены."
            if self.is_editing
            else "Водитель успешно сохранён.",
        )
        self.accept()

    def _populate_from_driver(self, driver_data: Dict[str, Any]) -> None:
        self.last_name_input.setText(driver_data["last_name"])
        self.first_name_input.setText(driver_data["first_name"])
        self.middle_name_input.setText(driver_data["middle_name"])
        birth_date = driver_data["birth_date"]
        self.birth_date_input.setDate(
            QDate(birth_date.year, birth_date.month, birth_date.day)
        )
        self.license_number_input.setText(driver_data["license_number"])
        self.passport_input.setText(driver_data["passport"])
        self.reg_city_input.setText(driver_data["reg_city"])
        self.reg_address_input.setText(driver_data["reg_address"])
        self.living_city_input.setText(driver_data["living_city"])
        self.living_address_input.setText(driver_data["living_address"])
        self.workplace_input.setText(driver_data.get("workplace") or "")
        self.position_input.setText(driver_data.get("position") or "")
        self.phone_input.setText(driver_data["phone"])
        self.email_input.setText(driver_data["email"])
        self.notes_input.setText(driver_data.get("notes") or "")

        project_root = os.path.dirname(os.path.dirname(__file__))
        self.photo_path = os.path.join(
            project_root, *driver_data["photo_path"].split("/")
        )
        if os.path.isfile(self.photo_path):
            preview = QPixmap(self.photo_path)
            if not preview.isNull():
                self.photo_preview.setText("")
                self.photo_preview.setPixmap(
                    preview.scaled(
                        self.photo_preview.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        else:
            self.photo_path = None
            self.photo_preview.setText("Фото не найдено")

    @staticmethod
    def _cleanup_photo_files(
        staged_path: Optional[str],
        backup_path: Optional[str],
        restore_path: Optional[str] = None,
        remove_path: Optional[str] = None,
    ) -> None:
        if staged_path is not None:
            DriverForm._remove_saved_photo(staged_path)

        if backup_path is not None:
            try:
                if restore_path is not None:
                    os.replace(backup_path, restore_path)
                else:
                    os.remove(backup_path)
            except OSError as error:
                QMessageBox.warning(
                    None,
                    "Ошибка восстановления фото",
                    f"Не удалось восстановить резервную копию "
                    f"{backup_path}: {error}",
                )

        if remove_path is not None:
            DriverForm._remove_saved_photo(remove_path)

    @staticmethod
    def _save_photo_as_jpeg(source_path: str, destination_path: str) -> None:
        with Image.open(source_path) as source_image:
            has_transparency = (
                "A" in source_image.getbands()
                or "transparency" in source_image.info
            )
            if has_transparency:
                rgba_image = source_image.convert("RGBA")
                jpeg_image = Image.new("RGB", rgba_image.size, "white")
                jpeg_image.paste(
                    rgba_image,
                    mask=rgba_image.getchannel("A"),
                )
            else:
                jpeg_image = source_image.convert("RGB")

            jpeg_image.save(destination_path, format="JPEG", quality=95)

    @staticmethod
    def _remove_saved_photo(photo_path: str) -> None:
        try:
            os.remove(photo_path)
        except FileNotFoundError:
            pass
        except OSError as error:
            QMessageBox.warning(
                None,
                "Очистка фото",
                f"Не удалось удалить несохранённый файл {photo_path}: {error}",
            )
