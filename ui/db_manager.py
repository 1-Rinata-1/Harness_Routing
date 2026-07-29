# диалог менеджера базы данных — просмотр и редактирование проектов
# открывается из тулбара кнопкой «база данных»

from pathlib import Path
import sys

# добавляем корневую папку в путь поиска модулей
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QWidget, QLineEdit, QTextEdit, QGroupBox,
    QMessageBox, QSplitter, QFrame,
)
from PyQt5.QtCore import Qt

from core import database as db


# вспомогательная функция — создаёт таблицу с базовыми настройками
def _tbl(cols: list[str]) -> QTableWidget:
    t = QTableWidget()
    t.setColumnCount(len(cols))
    t.setHorizontalHeaderLabels(cols)
    # запрещаем редактирование ячеек прямо в таблице
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setAlternatingRowColors(True)
    # скрываем номера строк слева
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setStretchLastSection(True)
    return t


# вспомогательная функция — создаёт горизонтальный разделитель
def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFrameShadow(QFrame.Sunken)
    return f


# вкладка со списком проектов и формой редактирования
class ProjectsTab(QWidget):
    def __init__(self):
        super().__init__()
        # id проекта, который сейчас редактируется
        self._editing_id: int | None = None
        self._build()
        # сразу загружаем список проектов из базы
        self.refresh()

    # строит интерфейс вкладки
    def _build(self):
        # делим окно на левую часть (таблица) и правую (форма)
        sp = QSplitter(Qt.Horizontal, self)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(sp)

        # левая часть: таблица со всеми проектами
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self._tbl = _tbl(["ID", "Название", "Описание", "Обновлён"])
        # настраиваем ширину столбцов
        self._tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self._tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._tbl.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        # при выборе строки заполняем форму справа
        self._tbl.selectionModel().selectionChanged.connect(self._on_select)
        lv.addWidget(self._tbl)
        sp.addWidget(left)

        # правая часть: форма для редактирования метаданных проекта
        right = QGroupBox("Проект")
        rv = QVBoxLayout(right)
        rv.setSpacing(8)
        rv.setContentsMargins(12, 16, 12, 12)

        rv.addWidget(QLabel("Название:"))
        self._f_name = QLineEdit()
        self._f_name.setPlaceholderText("Название проекта")
        rv.addWidget(self._f_name)

        rv.addWidget(QLabel("Описание:"))
        self._f_desc = QTextEdit()
        self._f_desc.setPlaceholderText("Описание…")
        self._f_desc.setFixedHeight(80)
        rv.addWidget(self._f_desc)

        rv.addWidget(_sep())

        # метка показывает id текущего редактируемого проекта
        self._lbl_status = QLabel("")
        self._lbl_status.setStyleSheet("color:#6c7086; font-size:8pt;")
        rv.addWidget(self._lbl_status)

        rv.addStretch()

        # кнопка создания нового проекта
        self._btn_add = QPushButton("Добавить")
        self._btn_add.setObjectName("runBtn")
        self._btn_add.setFixedHeight(32)
        self._btn_add.clicked.connect(self._add)
        rv.addWidget(self._btn_add)

        # кнопка сохранения изменений выбранного проекта
        self._btn_save = QPushButton("Сохранить изменения")
        self._btn_save.setEnabled(False)
        self._btn_save.setFixedHeight(32)
        self._btn_save.clicked.connect(self._save)
        rv.addWidget(self._btn_save)

        # кнопка удаления выбранного проекта
        self._btn_del = QPushButton("Удалить проект")
        self._btn_del.setObjectName("dangerBtn")
        self._btn_del.setEnabled(False)
        self._btn_del.setFixedHeight(32)
        self._btn_del.clicked.connect(self._delete)
        rv.addWidget(self._btn_del)

        right.setMinimumWidth(280)
        sp.addWidget(right)
        sp.setSizes([460, 340])

    # загружает список проектов из бд и обновляет таблицу
    def refresh(self):
        try:
            rows = db.list_projects()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка БД", str(e))
            return
        self._tbl.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self._tbl.setItem(i, 0, QTableWidgetItem(str(r["id"])))
            self._tbl.setItem(i, 1, QTableWidgetItem(r["name"]))
            self._tbl.setItem(i, 2, QTableWidgetItem(r.get("description") or ""))
            ts = r.get("updated_at")
            # форматируем дату в читаемый вид
            self._tbl.setItem(i, 3, QTableWidgetItem(
                ts.strftime("%d.%m.%Y %H:%M") if ts else ""))
            # сохраняем id и описание в скрытых данных ячейки
            self._tbl.item(i, 0).setData(Qt.UserRole, r["id"])
            self._tbl.item(i, 0).setData(Qt.UserRole + 1, r.get("description") or "")
        self._clear_form()

    # вызывается при выборе строки в таблице
    def _on_select(self):
        row = self._tbl.currentRow()
        if row < 0:
            self._clear_form()
            return
        # запоминаем id редактируемого проекта и заполняем форму
        self._editing_id = self._tbl.item(row, 0).data(Qt.UserRole)
        self._f_name.setText(self._tbl.item(row, 1).text())
        self._f_desc.setPlainText(self._tbl.item(row, 0).data(Qt.UserRole + 1))
        self._lbl_status.setText(f"Редактируется ID {self._editing_id}")
        self._btn_save.setEnabled(True)
        self._btn_del.setEnabled(True)

    # сбрасывает форму и снимает выделение в таблице
    def _clear_form(self):
        self._editing_id = None
        self._f_name.clear()
        self._f_desc.clear()
        self._lbl_status.setText("")
        self._btn_save.setEnabled(False)
        self._btn_del.setEnabled(False)
        self._tbl.clearSelection()

    # проверяет что название не пустое и возвращает его
    def _validate(self) -> str | None:
        name = self._f_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Нет названия", "Введите название проекта.")
            return None
        return name

    # создаёт новый проект в базе данных
    def _add(self):
        name = self._validate()
        if name is None:
            return
        try:
            db.create_project(name, self._f_desc.toPlainText().strip())
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
            return
        self.refresh()

    # сохраняет изменения названия и описания выбранного проекта
    def _save(self):
        if self._editing_id is None:
            return
        name = self._validate()
        if name is None:
            return
        try:
            db.update_project_meta(self._editing_id, name,
                                   self._f_desc.toPlainText().strip())
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
            return
        self.refresh()

    # удаляет выбранный проект после подтверждения
    def _delete(self):
        if self._editing_id is None:
            return
        # спрашиваем подтверждение перед удалением
        ans = QMessageBox.question(
            self, "Удалить проект",
            f"Удалить «{self._f_name.text().strip()}» (ID {self._editing_id})?\n"
            "Все данные проекта тоже будут удалены.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return
        try:
            db.delete_project(self._editing_id)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
            return
        self.refresh()


# главный диалог менеджера базы данных
class DBManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Менеджер базы данных")
        self.setMinimumSize(860, 500)
        self._build()

    # строит интерфейс диалога
    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(6)

        # вкладка с проектами занимает основное пространство
        self._tab_projects = ProjectsTab()
        v.addWidget(self._tab_projects)

        # кнопка закрытия внизу диалога
        h = QHBoxLayout()
        h.addStretch()
        btn_close = QPushButton("Закрыть")
        btn_close.clicked.connect(self.accept)
        h.addWidget(btn_close)
        v.addLayout(h)
