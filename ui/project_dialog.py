# диалог для сохранения и загрузки проектов из базы данных
# открывается из меню "база данных"

from pathlib import Path
import sys

# добавляем корневую папку в путь импорта
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QGroupBox, QLineEdit, QTextEdit, QMessageBox, QSplitter,
)
from PyQt5.QtCore import Qt

from core import database as db


# диалог работает в двух режимах: сохранение ("save") и загрузка ("load")
class ProjectDialog(QDialog):

    def __init__(self, mode: str = "load", parent=None):
        super().__init__(parent)
        # проверяем что режим задан правильно
        assert mode in ("save", "load")
        self._mode = mode
        # id выбранного в таблице проекта
        self._selected_id: int | None = None
        # результат — словарь с действием и данными, возвращается вызывающему коду
        self._result: dict | None = None

        # заголовок окна зависит от режима
        title = "Сохранить проект в БД" if mode == "save" else "Загрузить проект из БД"
        self.setWindowTitle(title)
        self.setMinimumSize(700, 420)
        self._build_ui()
        # сразу загружаем список проектов из базы
        self._load_list()

    # строит весь интерфейс диалога
    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setSpacing(8)
        v.setContentsMargins(12, 12, 12, 12)

        # делим окно на левую (таблица) и правую (форма) части
        splitter = QSplitter(Qt.Horizontal)

        # левая часть: таблица со списком проектов из бд
        left = QGroupBox("Проекты в БД")
        lv = QVBoxLayout(left)

        self._tbl = QTableWidget()
        self._tbl.setColumnCount(3)
        self._tbl.setHorizontalHeaderLabels(["ID", "Название", "Обновлён"])
        # настраиваем ширину столбцов
        self._tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        # запрещаем редактирование ячеек
        self._tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        self._tbl.setAlternatingRowColors(True)
        # при выборе строки обновляем форму справа
        self._tbl.selectionModel().selectionChanged.connect(self._on_select)
        lv.addWidget(self._tbl)
        splitter.addWidget(left)

        # правая часть: поля для названия и описания проекта
        right = QGroupBox("Метаданные")
        rv = QVBoxLayout(right)

        rv.addWidget(QLabel("Название:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Название проекта…")
        rv.addWidget(self._name_edit)

        rv.addWidget(QLabel("Описание:"))
        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("Краткое описание (необязательно)…")
        self._desc_edit.setMaximumHeight(100)
        rv.addWidget(self._desc_edit)

        rv.addStretch()
        splitter.addWidget(right)
        splitter.setSizes([420, 280])
        v.addWidget(splitter)

        # кнопки внизу диалога
        h = QHBoxLayout()
        h.addStretch()

        # набор кнопок зависит от режима
        if self._mode == "save":
            # в режиме сохранения: создать новый или перезаписать выбранный
            self._btn_new = QPushButton("Создать новый")
            self._btn_new.setObjectName("runBtn")
            self._btn_new.clicked.connect(self._save_new)
            h.addWidget(self._btn_new)

            self._btn_overwrite = QPushButton("Обновить выбранный")
            self._btn_overwrite.setEnabled(False)  # активна только если выбран проект
            self._btn_overwrite.clicked.connect(self._save_overwrite)
            h.addWidget(self._btn_overwrite)
        else:
            # в режиме загрузки: кнопка загрузить
            self._btn_load = QPushButton("Загрузить")
            self._btn_load.setObjectName("runBtn")
            self._btn_load.setEnabled(False)  # активна только если выбран проект
            self._btn_load.clicked.connect(self._do_load)
            h.addWidget(self._btn_load)

        # кнопка удаления доступна в обоих режимах
        btn_del = QPushButton("Удалить")
        btn_del.setObjectName("dangerBtn")
        btn_del.clicked.connect(self._delete)
        h.addWidget(btn_del)

        btn_cancel = QPushButton("Закрыть")
        btn_cancel.clicked.connect(self.reject)
        h.addWidget(btn_cancel)

        v.addLayout(h)

    # загружает список проектов из бд и заполняет таблицу
    def _load_list(self):
        try:
            rows = db.list_projects()
        except Exception as e:
            QMessageBox.critical(self, "БД недоступна", str(e))
            return
        self._tbl.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self._tbl.setItem(i, 0, QTableWidgetItem(str(r["id"])))
            self._tbl.setItem(i, 1, QTableWidgetItem(r["name"]))
            ts = r["updated_at"]
            # форматируем дату в читаемый вид
            self._tbl.setItem(i, 2, QTableWidgetItem(
                ts.strftime("%d.%m.%Y %H:%M") if ts else ""))
            # сохраняем id и описание в скрытых данных ячейки
            self._tbl.item(i, 0).setData(Qt.UserRole, r["id"])
            self._tbl.item(i, 0).setData(Qt.UserRole + 1, r.get("description", ""))

    # вызывается при выборе строки в таблице
    def _on_select(self):
        rows = self._tbl.selectedItems()
        if not rows:
            # если ничего не выбрано — снимаем выделение и блокируем кнопки
            self._selected_id = None
            if self._mode == "save":
                self._btn_overwrite.setEnabled(False)
            else:
                self._btn_load.setEnabled(False)
            return
        row = self._tbl.currentRow()
        # запоминаем id выбранного проекта
        self._selected_id = self._tbl.item(row, 0).data(Qt.UserRole)
        desc = self._tbl.item(row, 0).data(Qt.UserRole + 1)
        # заполняем поля формы данными выбранного проекта
        self._name_edit.setText(self._tbl.item(row, 1).text())
        self._desc_edit.setPlainText(desc or "")
        if self._mode == "save":
            self._btn_overwrite.setEnabled(True)
        else:
            self._btn_load.setEnabled(True)

    # читает название и описание из формы, проверяет что название не пустое
    def _get_meta(self) -> tuple[str, str] | None:
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Нет названия", "Введите название проекта.")
            return None
        return name, self._desc_edit.toPlainText().strip()

    # создаёт новый проект (не перезаписывает существующий)
    def _save_new(self):
        meta = self._get_meta()
        if meta is None:
            return
        # записываем результат и закрываем диалог с принятием
        self._result = {"action": "save_new", "name": meta[0], "description": meta[1]}
        self.accept()

    # перезаписывает выбранный проект новыми данными
    def _save_overwrite(self):
        meta = self._get_meta()
        if meta is None:
            return
        self._result = {
            "action": "save_overwrite",
            "project_id": self._selected_id,
            "name": meta[0],
            "description": meta[1],
        }
        self.accept()

    # подтверждает загрузку выбранного проекта
    def _do_load(self):
        if self._selected_id is None:
            return
        self._result = {"action": "load", "project_id": self._selected_id}
        self.accept()

    # удаляет выбранный проект из базы данных после подтверждения
    def _delete(self):
        if self._selected_id is None:
            QMessageBox.warning(self, "Нет выбора", "Выберите проект для удаления.")
            return
        row = self._tbl.currentRow()
        name = self._tbl.item(row, 1).text()
        # спрашиваем подтверждение перед удалением
        ans = QMessageBox.question(
            self, "Удалить проект",
            f"Удалить «{name}» (ID {self._selected_id})?\nДействие необратимо.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return
        try:
            db.delete_project(self._selected_id)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
            return
        self._selected_id = None
        # обновляем список после удаления
        self._load_list()

    # возвращает результат диалога (None если пользователь закрыл без действия)
    def result_data(self) -> dict | None:
        return self._result
