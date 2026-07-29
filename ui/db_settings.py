# диалог настройки подключения к postgresql
# настройки читаются и сохраняются в файл config.ini

import configparser
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QPushButton, QLabel, QLineEdit, QSpinBox, QMessageBox,
    QDialogButtonBox,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

# путь к файлу конфигурации относительно этого файла
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.ini"

# стили оформления диалога в тёмной теме
_STYLE = """
QDialog { background: #1e1e2e; color: #cdd6f4; }
QGroupBox {
    border: 1px solid #2a2a3d; border-radius: 8px;
    margin-top: 16px; padding: 12px 8px 8px 8px;
    color: #89b4fa; font-weight: 600; font-size: 8.5pt;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 12px;
    padding: 0 6px; background: #1e1e2e;
}
QLabel { color: #cdd6f4; font-size: 9pt; }
QLineEdit, QSpinBox {
    background: #181825; border: 1px solid #2a2a3d;
    border-radius: 6px; color: #cdd6f4;
    padding: 4px 8px; font-size: 9pt;
}
QLineEdit:focus, QSpinBox:focus { border-color: #89b4fa; }
QSpinBox::up-button, QSpinBox::down-button { width: 0; }
QPushButton {
    background: #2a2a3d; color: #cdd6f4;
    border: 1px solid #3d3f5c; border-radius: 6px;
    padding: 5px 14px; font-size: 9pt;
}
QPushButton:hover { background: #35364f; }
QPushButton:pressed { background: #45475a; }
QPushButton#testBtn {
    background: #1a2f54; color: #89b4fa;
    border-color: #89b4fa;
}
QPushButton#testBtn:hover { background: #1e3a6a; }
QPushButton#okBtn {
    background: #172d20; color: #a6e3a1;
    border-color: #2d5040; font-weight: 700;
}
QPushButton#okBtn:hover { background: #1d3828; }
"""


# читает параметры подключения из config.ini и возвращает словарь
def _read_cfg() -> dict:
    cfg = configparser.ConfigParser()
    cfg.read(_CONFIG_PATH, encoding="utf-8")
    # если секции postgresql нет — возвращаем значения по умолчанию
    if not cfg.has_section("postgresql"):
        return {"host": "localhost", "port": 5432,
                "database": "postgres", "user": "postgres", "password": ""}
    s = cfg["postgresql"]
    return {
        "host":     s.get("host",     "localhost"),
        "port":     s.getint("port",  5432),
        "database": s.get("database", "postgres"),
        "user":     s.get("user",     "postgres"),
        "password": s.get("password", ""),
    }


# записывает параметры подключения в config.ini
def _write_cfg(params: dict):
    cfg = configparser.ConfigParser()
    # читаем существующий файл чтобы не затереть другие секции
    cfg.read(_CONFIG_PATH, encoding="utf-8")
    if not cfg.has_section("postgresql"):
        cfg.add_section("postgresql")
    cfg["postgresql"]["host"]     = params["host"]
    cfg["postgresql"]["port"]     = str(params["port"])
    cfg["postgresql"]["database"] = params["database"]
    cfg["postgresql"]["user"]     = params["user"]
    cfg["postgresql"]["password"] = params["password"]
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        cfg.write(f)


# класс диалога настройки подключения к базе данных
class DBSettingsDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки подключения к базе данных")
        self.setMinimumWidth(460)
        self.setModal(True)
        self.setStyleSheet(_STYLE)
        self._build()
        # загружаем текущие настройки из файла
        self._load()

    # строит интерфейс диалога
    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 16, 16, 16)

        # группа полей с параметрами сервера
        gb = QGroupBox("Параметры сервера PostgreSQL")
        form = QFormLayout(gb)
        form.setSpacing(10)
        form.setContentsMargins(12, 18, 12, 12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # поле для адреса хоста
        self._f_host = QLineEdit()
        self._f_host.setPlaceholderText("например: 192.168.1.100  или  localhost")
        form.addRow("Хост / IP:", self._f_host)

        # поле для порта с допустимым диапазоном 1-65535
        self._f_port = QSpinBox()
        self._f_port.setRange(1, 65535)
        self._f_port.setValue(5432)
        self._f_port.setFixedWidth(100)
        form.addRow("Порт:", self._f_port)

        # поля для имени базы данных, пользователя и пароля
        self._f_db = QLineEdit()
        self._f_db.setPlaceholderText("postgres")
        form.addRow("База данных:", self._f_db)

        self._f_user = QLineEdit()
        self._f_user.setPlaceholderText("postgres")
        form.addRow("Пользователь:", self._f_user)

        self._f_pass = QLineEdit()
        # скрываем пароль звёздочками
        self._f_pass.setEchoMode(QLineEdit.Password)
        self._f_pass.setPlaceholderText("пароль")
        form.addRow("Пароль:", self._f_pass)

        root.addWidget(gb)

        # метка для вывода результата проверки соединения
        self._lbl_status = QLabel("")
        self._lbl_status.setWordWrap(True)
        self._lbl_status.setStyleSheet("font-size: 8.5pt; padding: 4px 2px;")
        root.addWidget(self._lbl_status)

        # кнопка проверки соединения
        btn_test = QPushButton("⚡  Проверить соединение")
        btn_test.setObjectName("testBtn")
        btn_test.setFixedHeight(32)
        btn_test.clicked.connect(self._test)
        root.addWidget(btn_test)

        # подсказка для пользователя
        hint = QLabel(
            "Чтобы подключиться к сетевому серверу, введите его IP-адрес.\n"
            "Для работы на своём компьютере оставьте localhost."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #6c7086; font-size: 8pt; padding: 2px 0;")
        root.addWidget(hint)

        # кнопки отмена и сохранить
        row_btn = QHBoxLayout()
        row_btn.addStretch()

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setFixedWidth(90)
        btn_cancel.clicked.connect(self.reject)
        row_btn.addWidget(btn_cancel)

        btn_ok = QPushButton("Сохранить")
        btn_ok.setObjectName("okBtn")
        btn_ok.setFixedWidth(110)
        btn_ok.clicked.connect(self._save_and_accept)
        row_btn.addWidget(btn_ok)

        root.addLayout(row_btn)

    # заполняет поля формы значениями из config.ini
    def _load(self):
        p = _read_cfg()
        self._f_host.setText(p["host"])
        self._f_port.setValue(p["port"])
        self._f_db.setText(p["database"])
        self._f_user.setText(p["user"])
        self._f_pass.setText(p["password"])

    # собирает текущие значения из полей в словарь
    def _current_params(self) -> dict:
        return {
            "host":     self._f_host.text().strip() or "localhost",
            "port":     self._f_port.value(),
            "database": self._f_db.text().strip() or "postgres",
            "user":     self._f_user.text().strip() or "postgres",
            "password": self._f_pass.text(),
        }

    # пробует подключиться к серверу и показывает результат
    def _test(self):
        self._lbl_status.setText("Подключение…")
        self._lbl_status.setStyleSheet("color: #f9e2af; font-size: 8.5pt; padding: 4px 2px;")
        # обновляем интерфейс до попытки подключения
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()

        params = self._current_params()
        try:
            import psycopg2
            # пробуем соединиться с таймаутом 5 секунд
            conn = psycopg2.connect(
                host=params["host"], port=params["port"],
                dbname=params["database"],
                user=params["user"], password=params["password"],
                connect_timeout=5,
            )
            ver = conn.server_version
            conn.close()
            # вычисляем версию postgresql из числового кода
            major = ver // 10000
            minor = (ver % 10000) // 100
            self._lbl_status.setText(
                f"✓  Подключение успешно  —  PostgreSQL {major}.{minor}"
            )
            self._lbl_status.setStyleSheet(
                "color: #a6e3a1; font-size: 8.5pt; "
                "padding: 4px 6px; background: #172d20; border-radius: 5px;"
            )
        except ImportError:
            # psycopg2 не установлен
            self._lbl_status.setText("✗  psycopg2 не установлен: pip install psycopg2-binary")
            self._lbl_status.setStyleSheet(
                "color: #f38ba8; font-size: 8.5pt; padding: 4px 2px;"
            )
        except Exception as e:
            # любая другая ошибка подключения
            self._lbl_status.setText(f"✗  Ошибка: {e}")
            self._lbl_status.setStyleSheet(
                "color: #f38ba8; font-size: 8.5pt; padding: 4px 2px;"
            )

    # сохраняет настройки в файл и закрывает диалог
    def _save_and_accept(self):
        try:
            _write_cfg(self._current_params())
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сохранения", str(e))
            return
        self.accept()
