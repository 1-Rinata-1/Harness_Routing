# главное окно приложения трассировки жгутовых соединений
# интерфейс построен на pyqt5 + pyvista (3d-рендер)
# режимы работы: навигация, добавление узла/ребра/пары, трассировка

import sys
import json
import math
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import networkx as nx
import pyvista as pv
from pyvistaqt import QtInteractor

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QDockWidget, QWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QListWidget, QListWidgetItem,
    QGroupBox, QLabel, QDoubleSpinBox, QSpinBox, QFormLayout,
    QToolBar, QFileDialog, QMessageBox, QTabWidget, QFrame,
    QButtonGroup, QSizePolicy, QAction,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QSlider, QScrollArea, QCheckBox, QDialog, QDialogButtonBox, QTextEdit,
    QSplitter, QStackedWidget, QToolTip,
)
from PyQt5.QtCore import Qt, QSize, QObject, QEvent, QRect, QPoint, QThread, pyqtSignal, QSettings, QTimer
from PyQt5.QtGui import QColor, QFont, QKeySequence, QCursor
from PyQt5.QtWidgets import QShortcut
from PyQt5.QtWidgets import QProgressBar

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.graph import CableChannelGraph
from core.aco import ACOParams, CableClass, WireType, emc_compatibility
from core.tracer import Tracer, ConnectionPair, Route, ROUTE_COLORS
from core.export_dxf import export_routes_dxf
from ui.project_dialog import ProjectDialog
from ui.db_manager import DBManagerDialog
from ui.db_settings import DBSettingsDialog
from core import database as db


# константы режимов — определяют текущее поведение при кликах в 3d-виде
MODE_NAVIGATE     = "navigate"
MODE_ADD_NODE     = "add_node"
MODE_ADD_EDGE     = "add_edge"
MODE_ADD_PAIR     = "add_pair"
MODE_GRID_EDIT    = "grid_edit"
MODE_MANUAL_ROUTE = "manual_route"
MODE_DRAW_CHANNEL = "draw_channel"

# подсказки для строки состояния в каждом режиме
_HINTS = {
    MODE_NAVIGATE:     "ПКМ — вращение  │  Колесо — масштаб  │  СКМ — перемещение",
    MODE_ADD_NODE:     "Кликни по поверхности модели, чтобы добавить узел",
    MODE_ADD_EDGE:     "Кликни по двум узлам, чтобы соединить их",
    MODE_ADD_PAIR:     "Выбери первый узел соединения",
    MODE_GRID_EDIT:    "ЛКМ — переключить ребро  │  Тяни — выделить рамкой  │  ПКМ/колесо — камера",
    MODE_MANUAL_ROUTE: "Кликни по соседнему узлу (зелёная сфера), чтобы продолжить маршрут  │  ПКМ/колесо — камера",
    MODE_DRAW_CHANNEL: "ЛКМ — добавить точку трассы  │  Двойной клик / Enter — зафиксировать  │  ПКМ/колесо — камера",
}

# функция возвращает строку css-стилей для тёмной темы приложения
def _make_style() -> str:
    return _STYLE

_STYLE = """
* { font-family: "Segoe UI", Arial, sans-serif; }

QMainWindow, QDialog, QWidget {
    background: #1e1e2e;
    color: #cdd6f4;
    font-size: 9pt;
}

/* ── Toolbar ── */
QToolBar {
    background: #181825;
    border: none;
    border-bottom: 1px solid #2a2a3d;
    spacing: 0;
    padding: 0 10px;
}
QToolBar::separator {
    background: #2a2a3d;
    width: 1px;
    margin: 6px 8px;
}

/* ── Кнопки ── */
QPushButton {
    background: #2a2a3d;
    color: #cdd6f4;
    border: 1px solid #3d3f5c;
    border-radius: 6px;
    padding: 4px 10px;
    min-width: 0;
}
QPushButton:hover   { background: #35364f; border-color: #585b70; }
QPushButton:pressed { background: #45475a; }
QPushButton:disabled { color: #3d3f5c; background: #1e1e2e; border-color: #252535; }
QPushButton:checked {
    background: #1a2f54;
    color: #89b4fa;
    border: 1.5px solid #89b4fa;
}

QPushButton#runBtn {
    background: #172d20;
    color: #a6e3a1;
    border: 1px solid #2d5040;
    font-size: 9.5pt;
    min-width: 210px;
    padding: 4px 14px;
    letter-spacing: 0.5px;
}
QPushButton#runBtn:hover   { background: #1d3828; border-color: #3d7055; }
QPushButton#runBtn:pressed { background: #10201a; }
QPushButton#runBtn:disabled { background: #181825; color: #3d3f5c; border-color: #252535; }

QPushButton#dangerBtn {
    background: #2a1520;
    color: #f38ba8;
    border-color: #52243a;
    min-width: 0;
    padding: 4px 12px;
}
QPushButton#dangerBtn:hover { background: #38182c; border-color: #7a3554; }

QPushButton#viewToggleBtn {
    background: #2a2a3d;
    color: #cdd6f4;
    border: 1px solid #3d3f5c;
    min-width: 0;
    padding: 3px 10px;
}
QPushButton#viewToggleBtn:hover { background: #35364f; border-color: #585b70; }
QPushButton#viewToggleBtn:checked {
    background: #1a2f54;
    color: #89b4fa;
    border: 1.5px solid #89b4fa;
    font-weight: 600;
}
QPushButton#viewToggleBtn:!checked {
    background: #252535;
    color: #45475a;
    border: 1px solid #313244;
}

QPushButton#delBtn {
    background: transparent;
    color: #6c7086;
    border: 1px solid #313244;
    min-width: 0;
    padding: 3px 10px;
    font-size: 8.5pt;
    border-radius: 5px;
}
QPushButton#delBtn:hover { color: #f38ba8; border-color: #585b70; background: #2a1a22; }

/* Сегментированные кнопки режимов */
QPushButton#modeFirst {
    border-radius: 0;
    border-top-left-radius: 5px;
    border-bottom-left-radius: 5px;
    border-right: none;
    min-width: 0;
    padding: 3px 10px;
}
QPushButton#modeMid {
    border-radius: 0;
    border-right: none;
    min-width: 0;
    padding: 3px 10px;
}
QPushButton#modeLast {
    border-radius: 0;
    border-top-right-radius: 5px;
    border-bottom-right-radius: 5px;
    min-width: 0;
    padding: 3px 10px;
}

/* ── GroupBox ── */
QGroupBox {
    border: 1px solid #2a2a3d;
    border-radius: 8px;
    margin-top: 16px;
    padding: 12px 8px 8px 8px;
    color: #89b4fa;
    font-weight: 600;
    font-size: 8.5pt;
    letter-spacing: 0.3px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    background: #1e1e2e;
}

/* ── Списки ── */
QListWidget {
    background: #181825;
    border: 1px solid #2a2a3d;
    border-radius: 6px;
    outline: none;
}
QListWidget::item          { padding: 5px 8px; border-radius: 4px; margin: 1px 4px; }
QListWidget::item:hover    { background: #252538; }
QListWidget::item:selected { background: #1e3358; color: #89b4fa; }

/* ── SpinBox ── */
QSpinBox, QDoubleSpinBox {
    background: #181825;
    border: 1px solid #2a2a3d;
    border-radius: 6px;
    color: #cdd6f4;
    padding: 3px 6px;
    min-width: 72px;
}
QSpinBox:focus, QDoubleSpinBox:focus { border-color: #89b4fa; }
QSpinBox::up-button, QDoubleSpinBox::up-button {
    background: #2a2a3d;
    border: none;
    border-left: 1px solid #3d3f5c;
    border-bottom: 1px solid #3d3f5c;
    width: 20px;
    subcontrol-origin: border;
    subcontrol-position: top right;
    border-top-right-radius: 5px;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    background: #2a2a3d;
    border: none;
    border-left: 1px solid #3d3f5c;
    width: 20px;
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    border-bottom-right-radius: 5px;
}
QSpinBox::up-button:hover,   QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background: #3d3f5c;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    width: 8px;
    height: 5px;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    width: 8px;
    height: 5px;
}

/* ── ComboBox ── */
QComboBox {
    background: #181825;
    border: 1px solid #2a2a3d;
    border-radius: 6px;
    color: #cdd6f4;
    padding: 3px 8px;
}
QComboBox:focus { border-color: #89b4fa; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background: #252535;
    border: 1px solid #45475a;
    selection-background-color: #1e3358;
    selection-color: #89b4fa;
    color: #cdd6f4;
    outline: none;
    padding: 2px;
}

/* ── Вкладки ── */
QTabWidget::pane {
    border: 1px solid #2a2a3d;
    border-top: none;
    background: #1e1e2e;
    border-bottom-left-radius: 6px;
    border-bottom-right-radius: 6px;
}
QTabBar {
    background: #181825;
}
QTabBar::tab {
    background: transparent;
    color: #585b70;
    padding: 7px 9px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 8.5pt;
}
QTabBar::tab:selected {
    color: #89b4fa;
    border-bottom: 2px solid #89b4fa;
    font-weight: 600;
}
QTabBar::tab:hover { color: #cdd6f4; background: rgba(255,255,255,0.03); }
QTabBar QToolButton {
    background: #181825;
    border: none;
    color: #6c7086;
    padding: 2px 4px;
    min-width: 18px;
    min-height: 18px;
}
QTabBar QToolButton:hover { background: #2a2a3d; color: #cdd6f4; }
QTabBar QToolButton:disabled { color: #313244; }

/* ── Scroll Area ── */
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }

/* ── Полосы прокрутки ── */
QScrollBar:vertical   { background: transparent; width: 6px; margin: 2px 0; }
QScrollBar:horizontal { background: transparent; height: 6px; margin: 0 2px; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #3d3f5c; border-radius: 3px; min-height: 24px; min-width: 24px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: #585b70; }
QScrollBar::add-line:vertical,  QScrollBar::sub-line:vertical,
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; height: 0; }

/* ── Таблица ── */
QTableWidget {
    background: #181825;
    border: 1px solid #2a2a3d;
    border-radius: 6px;
    gridline-color: #252535;
    color: #cdd6f4;
    outline: none;
}
QTableWidget::item          { padding: 4px 8px; }
QTableWidget::item:selected { background: #1e3358; color: #89b4fa; }
QHeaderView::section {
    background: #252535;
    color: #6c7086;
    border: none;
    border-right: 1px solid #2a2a3d;
    border-bottom: 1px solid #2a2a3d;
    padding: 5px 8px;
    font-weight: 600;
    font-size: 8pt;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* ── Слайдер ── */
QSlider::groove:horizontal {
    background: #2a2a3d; height: 3px; border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #89b4fa;
    border: 2px solid #1e1e2e;
    width: 12px; height: 12px;
    border-radius: 6px; margin: -5px 0;
}
QSlider::sub-page:horizontal { background: #4a7adb; border-radius: 2px; }

/* ── Dock ── */
QDockWidget::title {
    background: #181825;
    padding: 9px 14px;
    font-weight: 700;
    font-size: 8pt;
    color: #6c7086;
    border-bottom: 1px solid #2a2a3d;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}

/* ── Progress bar ── */
QProgressBar { background: #252535; border: none; border-radius: 3px; color: transparent; }
QProgressBar::chunk { background: #4a7adb; border-radius: 3px; }

/* ── Tooltip ── */
QToolTip {
    background: #252535;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 5px;
    padding: 5px 10px;
    font-size: 8.5pt;
}

/* ── Меню ── */
QMenuBar {
    background: #11111b;
    color: #cdd6f4;
    border-bottom: 1px solid #2a2a3d;
    padding: 2px;
    font-size: 9pt;
}
QMenuBar::item { padding: 4px 10px; border-radius: 4px; }
QMenuBar::item:selected { background: #2a2a3d; }
QMenu {
    background: #252535;
    color: #cdd6f4;
    border: 1px solid #3d3f5c;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item { padding: 5px 28px 5px 12px; border-radius: 4px; }
QMenu::item:selected { background: #1e3358; color: #89b4fa; }
QMenu::separator { background: #2a2a3d; height: 1px; margin: 4px 0; }

/* ── Кнопка-информация ⓘ ── */
QPushButton#infoBtn {
    background: transparent;
    color: #585b70;
    border: none;
    font-size: 11pt;
    padding: 0 2px;
    min-width: 0;
}
QPushButton#infoBtn:hover { color: #89b4fa; }

QLabel#accentLabel { color: #89b4fa; font-weight: 600; font-size: 8.5pt; padding: 2px 0; }
"""

# светлая тема
_STYLE_LIGHT = """
* { font-family: "Segoe UI", Arial, sans-serif; }

QMainWindow, QDialog, QWidget { background: #f8f9fa; color: #212529; font-size: 9pt; }

QToolBar {
    background: #e9ecef; border: none;
    border-bottom: 1px solid #ced4da; spacing: 0; padding: 0 10px;
}
QToolBar::separator { background: #ced4da; width: 1px; margin: 6px 8px; }

QPushButton {
    background: #e9ecef; color: #212529;
    border: 1px solid #ced4da; border-radius: 6px; padding: 4px 10px; min-width: 0;
}
QPushButton:hover   { background: #dee2e6; border-color: #adb5bd; }
QPushButton:pressed { background: #ced4da; }
QPushButton:disabled { color: #adb5bd; background: #f8f9fa; border-color: #e9ecef; }
QPushButton:checked { background: #dbeafe; color: #1d4ed8; border: 1.5px solid #2563eb; }

QPushButton#runBtn {
    background: #dcfce7; color: #166534; border: 1px solid #86efac;
    font-size: 9.5pt; min-width: 210px; padding: 4px 14px; letter-spacing: 0.5px;
}
QPushButton#runBtn:hover   { background: #bbf7d0; border-color: #4ade80; }
QPushButton#runBtn:pressed { background: #86efac; }
QPushButton#runBtn:disabled { background: #f0fdf4; color: #adb5bd; border-color: #e9ecef; }

QPushButton#dangerBtn {
    background: #fee2e2; color: #dc2626; border-color: #fca5a5; min-width: 0; padding: 4px 12px;
}
QPushButton#dangerBtn:hover { background: #fecaca; border-color: #f87171; }

QPushButton#viewToggleBtn {
    background: #e9ecef; color: #212529; border: 1px solid #ced4da; min-width: 0; padding: 3px 10px;
}
QPushButton#viewToggleBtn:hover { background: #dee2e6; border-color: #adb5bd; }
QPushButton#viewToggleBtn:checked {
    background: #dbeafe; color: #1d4ed8; border: 1.5px solid #2563eb; font-weight: 600;
}
QPushButton#viewToggleBtn:!checked { background: #f1f3f5; color: #adb5bd; border: 1px solid #dee2e6; }

QPushButton#delBtn {
    background: transparent; color: #6c757d; border: 1px solid #dee2e6;
    min-width: 0; padding: 3px 10px; font-size: 8.5pt; border-radius: 5px;
}
QPushButton#delBtn:hover { color: #dc2626; border-color: #adb5bd; background: #fee2e2; }

QPushButton#modeFirst {
    border-radius: 0; border-top-left-radius: 5px; border-bottom-left-radius: 5px;
    border-right: none; min-width: 0; padding: 3px 10px;
}
QPushButton#modeMid  { border-radius: 0; border-right: none; min-width: 0; padding: 3px 10px; }
QPushButton#modeLast {
    border-radius: 0; border-top-right-radius: 5px; border-bottom-right-radius: 5px;
    min-width: 0; padding: 3px 10px;
}

QPushButton#infoBtn {
    background: transparent; color: #adb5bd; border: none;
    font-size: 11pt; padding: 0 2px; min-width: 0;
}
QPushButton#infoBtn:hover { color: #2563eb; }

QLabel#accentLabel { color: #1d4ed8; font-weight: 600; font-size: 8.5pt; padding: 2px 0; }

QGroupBox {
    border: 1px solid #dee2e6; border-radius: 8px; margin-top: 16px;
    padding: 12px 8px 8px 8px; color: #1d4ed8; font-weight: 600;
    font-size: 8.5pt; letter-spacing: 0.3px;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; background: #f8f9fa; }

QListWidget {
    background: #ffffff; border: 1px solid #dee2e6; border-radius: 6px; outline: none;
}
QListWidget::item          { padding: 5px 8px; border-radius: 4px; margin: 1px 4px; }
QListWidget::item:hover    { background: #f1f3f5; }
QListWidget::item:selected { background: #dbeafe; color: #1d4ed8; }

QSpinBox, QDoubleSpinBox {
    background: #ffffff; border: 1px solid #ced4da; border-radius: 6px;
    color: #212529; padding: 3px 6px; min-width: 72px;
}
QSpinBox:focus, QDoubleSpinBox:focus { border-color: #2563eb; }
QSpinBox::up-button, QDoubleSpinBox::up-button {
    background: #e9ecef; border: none; border-left: 1px solid #ced4da;
    border-bottom: 1px solid #ced4da; width: 20px;
    subcontrol-origin: border; subcontrol-position: top right; border-top-right-radius: 5px;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    background: #e9ecef; border: none; border-left: 1px solid #ced4da; width: 20px;
    subcontrol-origin: border; subcontrol-position: bottom right; border-bottom-right-radius: 5px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background: #dee2e6; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow     { width: 8px; height: 5px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { width: 8px; height: 5px; }

QComboBox {
    background: #ffffff; border: 1px solid #ced4da; border-radius: 6px;
    color: #212529; padding: 3px 8px;
}
QComboBox:focus { border-color: #2563eb; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background: #ffffff; border: 1px solid #ced4da;
    selection-background-color: #dbeafe; selection-color: #1d4ed8;
    color: #212529; outline: none; padding: 2px;
}

QTabWidget::pane {
    border: 1px solid #dee2e6; border-top: none; background: #f8f9fa;
    border-bottom-left-radius: 6px; border-bottom-right-radius: 6px;
}
QTabBar { background: #e9ecef; }
QTabBar::tab {
    background: transparent; color: #6c757d; padding: 7px 9px;
    border: none; border-bottom: 2px solid transparent; font-size: 8.5pt;
}
QTabBar::tab:selected { color: #1d4ed8; border-bottom: 2px solid #2563eb; font-weight: 600; }
QTabBar::tab:hover { color: #212529; background: rgba(0,0,0,0.03); }
QTabBar QToolButton {
    background: #e9ecef; border: none; color: #6c757d;
    padding: 2px 4px; min-width: 18px; min-height: 18px;
}
QTabBar QToolButton:hover    { background: #dee2e6; color: #212529; }
QTabBar QToolButton:disabled { color: #ced4da; }

QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }

QScrollBar:vertical   { background: transparent; width: 6px; margin: 2px 0; }
QScrollBar:horizontal { background: transparent; height: 6px; margin: 0 2px; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #ced4da; border-radius: 3px; min-height: 24px; min-width: 24px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: #adb5bd; }
QScrollBar::add-line:vertical,  QScrollBar::sub-line:vertical,
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; height: 0; }

QTableWidget {
    background: #ffffff; border: 1px solid #dee2e6; border-radius: 6px;
    gridline-color: #e9ecef; color: #212529; outline: none;
}
QTableWidget::item          { padding: 4px 8px; }
QTableWidget::item:selected { background: #dbeafe; color: #1d4ed8; }
QHeaderView::section {
    background: #f1f3f5; color: #6c757d; border: none;
    border-right: 1px solid #dee2e6; border-bottom: 1px solid #dee2e6;
    padding: 5px 8px; font-weight: 600; font-size: 8pt;
    text-transform: uppercase; letter-spacing: 0.5px;
}

QSlider::groove:horizontal { background: #dee2e6; height: 3px; border-radius: 2px; }
QSlider::handle:horizontal {
    background: #2563eb; border: 2px solid #f8f9fa;
    width: 12px; height: 12px; border-radius: 6px; margin: -5px 0;
}
QSlider::sub-page:horizontal { background: #93c5fd; border-radius: 2px; }

QDockWidget::title {
    background: #e9ecef; padding: 9px 14px; font-weight: 700; font-size: 8pt;
    color: #6c757d; border-bottom: 1px solid #ced4da;
    letter-spacing: 1.5px; text-transform: uppercase;
}

QProgressBar { background: #e9ecef; border: none; border-radius: 3px; color: transparent; }
QProgressBar::chunk { background: #2563eb; border-radius: 3px; }

QToolTip {
    background: #212529; color: #f8f9fa; border: 1px solid #495057;
    border-radius: 5px; padding: 5px 10px; font-size: 8.5pt;
}

QMenuBar {
    background: #f1f3f5; color: #212529;
    border-bottom: 1px solid #dee2e6; padding: 2px; font-size: 9pt;
}
QMenuBar::item { padding: 4px 10px; border-radius: 4px; }
QMenuBar::item:selected { background: #dee2e6; }
QMenu {
    background: #ffffff; color: #212529;
    border: 1px solid #ced4da; border-radius: 8px; padding: 4px;
}
QMenu::item { padding: 5px 28px 5px 12px; border-radius: 4px; }
QMenu::item:selected { background: #dbeafe; color: #1d4ed8; }
QMenu::separator { background: #dee2e6; height: 1px; margin: 4px 0; }

QStatusBar {
    background: #e9ecef; color: #6c757d;
    border-top: 1px solid #ced4da; padding: 0 8px; font-size: 8.5pt;
}
QStatusBar::item { border: none; }
"""


# фильтр событий для определения кликов в 3d-сцене
# отличает клик от перетаскивания камеры по смещению курсора
# при клике вызывает callback с vtk-координатами, при движении — hover_cb
class _PartClickFilter(QObject):
    # порог в пикселях: если мышь сдвинулась больше — считается перетаскивание
    DRAG_THRESHOLD = 5

    def __init__(self, viewport_widget, callback, hover_cb=None):
        super().__init__(viewport_widget)
        self._widget    = viewport_widget
        self._callback  = callback
        self._hover_cb  = hover_cb
        self._press     = None
        self._dragging  = False

    def eventFilter(self, obj, event):
        t = event.type()
        if t == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self._press    = event.pos()
            self._dragging = False
        elif t == QEvent.MouseMove:
            if self._hover_cb is not None:
                vtk_x = event.x()
                vtk_y = self._widget.height() - event.y() - 1
                self._hover_cb(vtk_x, vtk_y)
            if self._press is not None:
                dp = event.pos() - self._press
                if dp.manhattanLength() > self.DRAG_THRESHOLD:
                    self._dragging = True
        elif t == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if self._press is not None and not self._dragging:
                # VTK: Y=0 снизу, Qt: Y=0 сверху
                vtk_x = event.x()
                vtk_y = self._widget.height() - event.y() - 1
                self._callback(vtk_x, vtk_y)
            self._press    = None
            self._dragging = False
        return False   # событие не поглощаем — камера работает как обычно


# фильтр для правого клика — перехватывает пкм в 3d-виде и вызывает callback
# нужно чтобы показать контекстное меню вместо стандартного меню vtk
class _ContextMenuFilter(QObject):
    DRAG_THRESHOLD = 5

    def __init__(self, viewport_widget, callback):
        super().__init__(viewport_widget)
        self._widget = viewport_widget
        self._callback = callback
        self._press = None

    def eventFilter(self, obj, event):
        t = event.type()
        if t == QEvent.MouseButtonPress and event.button() == Qt.RightButton:
            self._press = event.pos()
        elif t == QEvent.MouseButtonRelease and event.button() == Qt.RightButton:
            if self._press is not None:
                dp = event.pos() - self._press
                self._press = None
                if dp.manhattanLength() <= self.DRAG_THRESHOLD:
                    vtk_x = event.x()
                    vtk_y = self._widget.height() - event.y() - 1
                    self._callback(event.globalPos(), vtk_x, vtk_y)
                    return True   # поглощаем — не открываем системное меню VTK
        return False


# фильтр событий для режима рисования трассы полилинией
# одиночный клик добавляет точку, двойной клик завершает трассу
# двойной клик поглощается чтобы не добавить лишнюю точку
class _PolylineEventFilter(QObject):
    DRAG_THRESHOLD = 5

    def __init__(self, viewport_widget, click_cb, hover_cb, dblclick_cb):
        super().__init__(viewport_widget)
        self._widget      = viewport_widget
        self._click_cb    = click_cb
        self._hover_cb    = hover_cb
        self._dblclick_cb = dblclick_cb
        self._press       = None
        self._dragging    = False
        self._skip_release = False

    def eventFilter(self, obj, event):
        t = event.type()
        if t == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self._press    = event.pos()
            self._dragging = False
        elif t == QEvent.MouseMove:
            vtk_x = event.x()
            vtk_y = self._widget.height() - event.y() - 1
            self._hover_cb(vtk_x, vtk_y)
            if self._press is not None:
                if (event.pos() - self._press).manhattanLength() > self.DRAG_THRESHOLD:
                    self._dragging = True
        elif t == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
            # Поглощаем второй клик двойного нажатия, чтобы не добавить лишнюю точку
            self._skip_release = True
            self._press = None
            self._dblclick_cb()
            return True
        elif t == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if self._skip_release:
                self._skip_release = False
                self._press = None
                self._dragging = False
            elif self._press is not None and not self._dragging:
                vtk_x = event.x()
                vtk_y = self._widget.height() - event.y() - 1
                self._click_cb(vtk_x, vtk_y)
            self._press    = None
            self._dragging = False
        return False



# базовый класс команды для паттерна undo/redo
# каждое действие над графом (добавить/удалить узел/ребро) оборачивается в команду
class _Cmd:
    def execute(self): raise NotImplementedError
    def undo(self):    raise NotImplementedError
    def description(self) -> str: return ""


# команда добавления узла — при первом execute создаёт новый id, при повторе использует тот же
class _AddNodeCmd(_Cmd):
    def __init__(self, w, pos):
        self._w   = w
        self._pos = tuple(float(c) for c in pos)
        self._nid = None

    def execute(self):
        if self._nid is None:
            self._nid = self._w._graph.add_node(self._pos)
        else:
            self._w._graph._g.add_node(self._nid, pos=self._pos)
        actor = self._w.plotter.add_mesh(
            pv.Sphere(radius=self._w._sphere_r, center=self._pos),
            color="#00cc66", smooth_shading=True, pickable=True,
            reset_camera=False,
        )
        self._w._node_actors[self._nid] = actor
        self._w._refresh_nodes_list()
        self._w._set_status(
            f"Узел {self._nid} добавлен: "
            f"({self._pos[0]:.1f}, {self._pos[1]:.1f}, {self._pos[2]:.1f})"
        )

    def undo(self):
        self._w.plotter.remove_actor(self._w._node_actors.pop(self._nid))
        self._w._graph.remove_node(self._nid)
        self._w._refresh_nodes_list()
        self._w._set_status(f"Отмена: узел {self._nid} удалён.")

    def description(self) -> str:
        return f"Добавить узел {self._nid}"


# команда удаления узла — сохраняет позицию и список смежных рёбер для отмены
class _RemoveNodeCmd(_Cmd):
    def __init__(self, w, nid):
        self._w   = w
        self._nid = nid
        self._pos = tuple(w._graph.nodes[nid]["pos"])
        g = w._graph.networkx_graph()
        self._edges = [(u, v) for u, v in list(g.edges(nid))]

    def execute(self):
        for u, v in self._edges:
            key = (min(u, v), max(u, v))
            if key in self._w._edge_actors:
                self._w.plotter.remove_actor(self._w._edge_actors.pop(key))
        self._w._pairs = [
            p for p in self._w._pairs
            if p.source != self._nid and p.target != self._nid
        ]
        self._w._graph.remove_node(self._nid)
        if self._nid in self._w._node_actors:
            self._w.plotter.remove_actor(self._w._node_actors.pop(self._nid))
        self._w._refresh_all_lists()
        self._w._set_status(
            f"Узел {self._nid} и {len(self._edges)} рёбер удалены."
        )

    def undo(self):
        self._w._graph._g.add_node(self._nid, pos=self._pos)
        actor = self._w.plotter.add_mesh(
            pv.Sphere(radius=self._w._sphere_r, center=self._pos),
            color="#00cc66", smooth_shading=True, pickable=True,
            reset_camera=False,
        )
        self._w._node_actors[self._nid] = actor
        for u, v in self._edges:
            self._w._graph.add_edge(u, v)
            self._w._draw_edge_actor(u, v)
        self._w._refresh_all_lists()
        self._w._set_status(f"Отмена: узел {self._nid} и рёбра восстановлены.")

    def description(self) -> str:
        return f"Удалить узел {self._nid}"


# команда добавления ребра между двумя узлами
class _AddEdgeCmd(_Cmd):
    def __init__(self, w, u, v):
        self._w = w
        self._u = u
        self._v = v

    def execute(self):
        self._w._graph.add_edge(self._u, self._v)
        self._w._draw_edge_actor(self._u, self._v)
        self._w._refresh_edges_list()
        self._w._set_status(f"Ребро {self._u}—{self._v} добавлено.")

    def undo(self):
        key = (min(self._u, self._v), max(self._u, self._v))
        if key in self._w._edge_actors:
            self._w.plotter.remove_actor(self._w._edge_actors.pop(key))
        self._w._graph.remove_edge(self._u, self._v)
        self._w._refresh_edges_list()
        self._w._set_status(f"Отмена: ребро {self._u}—{self._v} удалено.")

    def description(self) -> str:
        return f"Добавить ребро {self._u}—{self._v}"


# команда удаления ребра — также убирает его из списка коллизий
class _RemoveEdgeCmd(_Cmd):
    def __init__(self, w, u, v):
        self._w = w
        self._u = u
        self._v = v

    def execute(self):
        key = (min(self._u, self._v), max(self._u, self._v))
        if key in self._w._edge_actors:
            self._w.plotter.remove_actor(self._w._edge_actors.pop(key))
        self._w._edge_collisions.discard(key)
        self._w._graph.remove_edge(self._u, self._v)
        self._w._refresh_edges_list()
        self._w._set_status(f"Ребро {self._u}—{self._v} удалено.")

    def undo(self):
        self._w._graph.add_edge(self._u, self._v)
        self._w._draw_edge_actor(self._u, self._v)
        self._w._refresh_edges_list()
        self._w._set_status(f"Отмена: ребро {self._u}—{self._v} восстановлено.")

    def description(self) -> str:
        return f"Удалить ребро {self._u}—{self._v}"


# команда добавления полилинии — создаёт сразу n узлов и n-1 рёбер за одну операцию
# вся трасса отменяется целиком одним ctrl+z
class _AddPolylineCmd(_Cmd):
    def __init__(self, w, pts: list):
        self._w    = w
        self._pts  = [tuple(float(c) for c in p) for p in pts]
        self._nids: list = []

    def execute(self):
        if not self._nids:
            self._nids = [self._w._graph.add_node(p) for p in self._pts]
        else:
            for nid, pos in zip(self._nids, self._pts):
                self._w._graph._g.add_node(nid, pos=pos)

        for nid, pos in zip(self._nids, self._pts):
            actor = self._w.plotter.add_mesh(
                pv.Sphere(radius=self._w._sphere_r, center=pos),
                color="#00cc66", smooth_shading=True, pickable=True,
                reset_camera=False,
            )
            self._w._node_actors[nid] = actor

        for i in range(len(self._nids) - 1):
            u, v = self._nids[i], self._nids[i + 1]
            self._w._graph.add_edge(u, v)
            self._w._draw_edge_actor(u, v)

        self._w._refresh_all_lists()
        self._w._set_status(
            f"Трасса добавлена: {len(self._nids)} узлов, {len(self._nids) - 1} рёбер."
        )

    def undo(self):
        for i in range(len(self._nids) - 1):
            u, v = self._nids[i], self._nids[i + 1]
            key = (min(u, v), max(u, v))
            if key in self._w._edge_actors:
                self._w.plotter.remove_actor(self._w._edge_actors.pop(key))
            try:
                self._w._graph.remove_edge(u, v)
            except Exception:
                pass
        for nid in self._nids:
            if nid in self._w._node_actors:
                self._w.plotter.remove_actor(self._w._node_actors.pop(nid))
            try:
                self._w._graph.remove_node(nid)
            except Exception:
                pass
        self._w._refresh_all_lists()
        self._w._set_status("Отмена: трасса удалена.")

    def description(self) -> str:
        return f"Нарисовать трассу ({len(self._pts)} точек)"


# стек отмены/повтора действий, хранит до 50 команд
class _UndoStack:
    MAX = 50

    def __init__(self):
        self._history: list = []
        # текущая позиция в истории (-1 означает пустой стек)
        self._pos: int = -1

    def push(self, cmd: _Cmd) -> None:
        del self._history[self._pos + 1:]
        cmd.execute()
        self._history.append(cmd)
        if len(self._history) > self.MAX:
            self._history.pop(0)
        self._pos = len(self._history) - 1

    def undo(self) -> bool:
        if self._pos < 0:
            return False
        self._history[self._pos].undo()
        self._pos -= 1
        return True

    def redo(self) -> bool:
        if self._pos >= len(self._history) - 1:
            return False
        self._pos += 1
        self._history[self._pos].execute()
        return True

    def can_undo(self) -> bool: return self._pos >= 0
    def can_redo(self) -> bool: return self._pos < len(self._history) - 1
    def undo_text(self) -> str:
        return self._history[self._pos].description() if self.can_undo() else ""
    def redo_text(self) -> str:
        return self._history[self._pos + 1].description() if self.can_redo() else ""
    def clear(self) -> None:
        self._history.clear()
        self._pos = -1


# воркер трассировки — запускает алгоритм в отдельном потоке, чтобы ui не зависал
# отправляет сигналы о прогрессе и завершении
class _TracingWorker(QThread):
    sig_progress = pyqtSignal(str, int)   # (текст статуса, процент 0-100)
    sig_done     = pyqtSignal(object)     # list[Route]

    def __init__(self, tracer, pairs, n_iters,
                 algorithm: str = "aco", aco_fallback: bool = True):
        super().__init__()
        self._tracer       = tracer
        self._pairs        = pairs
        self._n_iters      = n_iters
        self._algorithm    = algorithm
        self._aco_fallback = aco_fallback
        if algorithm == "dijkstra":
            self._total = max(len(pairs), 1)
        else:
            self._total = max(len(pairs) * n_iters, 1)
        self._cur_pair = 0

    def run(self):
        total_pairs = len(self._pairs)

        def pair_cb(p, tp, label):
            self._cur_pair = p
            if self._algorithm == "dijkstra":
                pct = int(100 * p / max(total_pairs, 1))
            else:
                pct = int(p * self._n_iters / self._total * 100)
            algo_tag = "" if self._algorithm == "aco" else "  [Дейкстра]"
            self.sig_progress.emit(f"Пара {p + 1}/{tp}: {label}{algo_tag}", pct)

        def iter_cb(t, T):
            p   = self._cur_pair
            pct = int((p * self._n_iters + t) / self._total * 100)
            self.sig_progress.emit(
                f"Пара {p + 1}/{total_pairs}  |  Итерация {t}/{T}", pct
            )

        routes = self._tracer.route_all(
            self._pairs, progress=pair_cb,
            iter_callback=iter_cb if self._algorithm == "aco" else None,
            algorithm=self._algorithm,
            aco_fallback=self._aco_fallback,
        )
        self.sig_done.emit(routes)

    def cancel(self):
        self._tracer.cancel()


# загружает gltf/glb модель через trimesh и возвращает список деталей
# каждая деталь: (pyvista-меш, hex-цвет, имя)
def _load_gltf_parts(path: str) -> list:
    import trimesh
    scene = trimesh.load(path, force="scene")
    if isinstance(scene, trimesh.Scene):
        geoms = [(name, g) for name, g in scene.geometry.items()
                 if hasattr(g, "faces") and len(g.faces) > 0]
    elif hasattr(scene, "faces") and len(scene.faces) > 0:
        geoms = [("Деталь 1", scene)]
    else:
        geoms = []
    if not geoms:
        raise ValueError("Модель не содержит полигональной геометрии")
    result = []
    for idx, (name, part) in enumerate(geoms):
        verts = np.asarray(part.vertices, dtype=float)
        faces = np.asarray(part.faces, dtype=int)
        face_col = np.full((len(faces), 1), 3, dtype=int)
        face_arr = np.hstack([face_col, faces]).ravel()
        pv_mesh = pv.PolyData(verts, face_arr)
        try:
            c = part.visual.to_color().main_color[:3]
            hex_color = "#{:02x}{:02x}{:02x}".format(int(c[0]), int(c[1]), int(c[2]))
        except Exception:
            hex_color = "#8ab4d4"
        label = name if name else f"Деталь {idx + 1}"
        result.append((pv_mesh, hex_color, label))
    return result


# воркер загрузки 3d-модели — читает файл в отдельном потоке
# поддерживает stl/obj/ply/vtk/glb/gltf через pyvista и trimesh
class _ModelLoadWorker(QThread):
    sig_done  = pyqtSignal(object, str)  # (raw_parts, orig_path)
    sig_error = pyqtSignal(str)          # сообщение об ошибке

    def __init__(self, path: str):
        super().__init__()
        self._path = path

    def run(self):
        path = self._path
        ext  = Path(path).suffix.lower()
        try:
            if ext in (".gltf", ".glb"):
                raw_parts = _load_gltf_parts(path)
            else:
                load_path = path
                if not all(ord(c) < 128 for c in path):
                    tmp_dir   = Path(tempfile.mkdtemp(prefix="kompas_"))
                    safe_name = "".join(c if ord(c) < 128 else "_" for c in Path(path).name) or "model"
                    dst = tmp_dir / safe_name
                    shutil.copy2(path, dst)
                    load_path = str(dst)
                raw = pv.read(load_path)
                if isinstance(raw, pv.MultiBlock):
                    merged = raw.combine(merge_points=False)
                    raw = merged if (merged is not None and merged.n_points > 0) else raw
                raw_parts = [(raw, "#8ab4d4", Path(path).stem)]
            self.sig_done.emit(raw_parts, path)
        except ImportError:
            self.sig_error.emit("__NO_TRIMESH__")
        except FileNotFoundError as exc:
            self.sig_error.emit(f"__FNFE__{exc}")
        except Exception as exc:
            self.sig_error.emit(str(exc))


# воркер авто-выбора рёбер сетки по близости к поверхности модели
# использует kdtree для поиска ближайших точек, convex hull для проверки внутренних точек
# рёбра проходящие сквозь деталь отфильтровываются через ray_trace
class _AutoSelectWorker(QThread):
    sig_progress = pyqtSignal(str, int)  # (текст, процент)
    sig_done     = pyqtSignal(object)    # set[int] или None при отмене

    def __init__(self, parts_data: list, grid_nodes: list,
                 grid_edge_pairs: list, threshold: float):
        super().__init__()
        self._parts_data      = parts_data
        self._grid_nodes      = grid_nodes
        self._grid_edge_pairs = grid_edge_pairs
        self._threshold       = threshold
        self._stop            = False

    def cancel(self):
        self._stop = True

    def run(self):
        from scipy.spatial import cKDTree, ConvexHull, Delaunay

        self.sig_progress.emit("Собираю вершины модели…", 5)
        all_pts = np.vstack([
            np.asarray(p["mesh"].points, dtype=float)
            for p in self._parts_data
        ])
        if self._stop:
            self.sig_done.emit(None); return

        self.sig_progress.emit("Вычисляю середины рёбер…", 15)
        nodes = np.array(self._grid_nodes, dtype=float)
        midpoints = np.array([
            (nodes[i] + nodes[j]) * 0.5
            for i, j in self._grid_edge_pairs
        ], dtype=float)
        if self._stop:
            self.sig_done.emit(None); return

        self.sig_progress.emit("KDTree: расстояния до поверхности…", 25)
        tree = cKDTree(all_pts)
        min_dists, _ = tree.query(midpoints, workers=-1)
        if self._stop:
            self.sig_done.emit(None); return

        self.sig_progress.emit("Проверяю принадлежность корпусу…", 45)
        try:
            hull = ConvexHull(all_pts)
            tri  = Delaunay(all_pts[hull.vertices])
            inside_mask = tri.find_simplex(midpoints) >= 0
        except Exception:
            inside_mask = np.ones(len(midpoints), dtype=bool)
        if self._stop:
            self.sig_done.emit(None); return

        self.sig_progress.emit("Фильтрую по расстоянию…", 60)
        candidates = {
            idx for idx, (d, ins) in enumerate(zip(min_dists, inside_mask))
            if d <= self._threshold and ins
        }
        if self._stop:
            self.sig_done.emit(None); return

        # Убираем рёбра, проходящие сквозь твёрдые детали.
        # Для каждого кандидата (A→B) кастуем луч по слегка укороченному
        # отрезку: если находим >= 2 пересечений с поверхностью любой детали,
        # значит ребро входит в тело и выходит из него — такое ребро исключаем.
        self.sig_progress.emit("Проверяю пересечения с деталями…", 65)
        part_meshes = [p["mesh"] for p in self._parts_data]
        selected: set[int] = set()
        n_total = max(len(candidates), 1)

        for k, idx in enumerate(sorted(candidates)):
            if self._stop:
                self.sig_done.emit(None); return
            if k % 50 == 0:
                pct = 65 + int(30 * k / n_total)
                self.sig_progress.emit(
                    f"Пересечения: {k}/{n_total} рёбер…", min(pct, 95)
                )

            i, j = self._grid_edge_pairs[idx]
            a = nodes[i]
            b = nodes[j]
            direction = b - a
            length = float(np.linalg.norm(direction))
            if length < 1e-9:
                selected.add(idx)
                continue

            # Укорачиваем на 2 % с каждой стороны, чтобы не считать
            # пересечения прямо в узловых точках сетки (лежащих на поверхности).
            eps = length * 0.02
            unit = direction / length
            start = (a + unit * eps).tolist()
            end   = (b - unit * eps).tolist()

            passes_through = False
            for mesh in part_meshes:
                pts_hit, _ = mesh.ray_trace(start, end, first_point=False)
                if len(pts_hit) >= 2:
                    passes_through = True
                    break

            if not passes_through:
                selected.add(idx)

        self.sig_done.emit(selected)


# воркер верификации рёбер графа — проверяет каждое ребро на пересечение с деталями
# если луч от одного конца ребра до другого пересекает поверхность дважды — ребро внутри тела
class _GraphEdgeVerifyWorker(QThread):
    sig_progress = pyqtSignal(str, int)
    sig_done     = pyqtSignal(object)   # set of (u,v) colliding edge keys

    def __init__(self, graph, parts_data):
        super().__init__()
        self._graph      = graph
        self._parts_data = parts_data
        self._stop       = False

    def cancel(self):
        self._stop = True

    def run(self):
        part_meshes = [p["mesh"] for p in self._parts_data]
        if not part_meshes:
            self.sig_done.emit(set())
            return

        edges   = list(self._graph.edges())
        n_total = max(len(edges), 1)
        colliding: set = set()

        for k, (u, v) in enumerate(edges):
            if self._stop:
                self.sig_done.emit(set())
                return
            if k % 20 == 0:
                pct = int(100 * k / n_total)
                self.sig_progress.emit(f"Проверка рёбер: {k}/{n_total}…", pct)

            a = np.array(self._graph.nodes[u]["pos"])
            b = np.array(self._graph.nodes[v]["pos"])
            direction = b - a
            length = float(np.linalg.norm(direction))
            if length < 1e-9:
                continue

            eps   = length * 0.02
            unit  = direction / length
            start = (a + unit * eps).tolist()
            end   = (b - unit * eps).tolist()

            for mesh in part_meshes:
                pts_hit, _ = mesh.ray_trace(start, end, first_point=False)
                if len(pts_hit) >= 2:
                    colliding.add((min(u, v), max(u, v)))
                    break

        self.sig_progress.emit("Готово", 100)
        self.sig_done.emit(colliding)


# классы верификации маршрутов — проверяют конечные точки, неразрывность и коллизии с деталями
from dataclasses import dataclass as _dc, field as _field

# результат верификации одного маршрута: три булевых поля и список описаний ошибок
@_dc
class _VerifyResult:
    idx:            int
    label:          str
    color:          str
    ok_endpoints:   bool      = True   # начало и конец совпадают с source/target
    ok_continuous:  bool      = True   # все соседние узлы соединены ребром графа
    ok_collision:   bool      = True   # маршрут не пересекает детали модели
    issues:         list      = _field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.ok_endpoints and self.ok_continuous and self.ok_collision


# воркер верификации маршрутов — запускает все три проверки в фоновом потоке
class _VerifyWorker(QThread):
    sig_progress = pyqtSignal(str, int)   # (текст, %)
    sig_done     = pyqtSignal(list)       # list[_VerifyResult]

    def __init__(self, routes, graph, parts_data):
        super().__init__()
        self._routes     = routes
        self._graph      = graph
        self._parts_data = parts_data
        self._stop       = False

    def cancel(self):
        self._stop = True

    def run(self):
        g           = self._graph.networkx_graph()
        part_meshes = [p["mesh"] for p in self._parts_data]
        results     = []
        n           = max(len(self._routes), 1)

        for ri, route in enumerate(self._routes):
            if self._stop:
                break
            self.sig_progress.emit(
                f"Маршрут {ri + 1}/{n}: {route.pair.label}…",
                int(100 * ri / n),
            )
            res = _VerifyResult(idx=ri, label=route.pair.label, color=route.color)
            path = route.path

            # ── 1. Пустой маршрут ──────────────────────────────────────
            if not path:
                res.ok_endpoints  = False
                res.ok_continuous = False
                res.issues.append("Маршрут пустой")
                results.append(res)
                continue

            # ── 2. Конечные точки ──────────────────────────────────────
            if path[0] != route.pair.source:
                res.ok_endpoints = False
                res.issues.append(
                    f"Начало пути ({path[0]}) ≠ источник ({route.pair.source})"
                )
            if path[-1] != route.pair.target:
                res.ok_endpoints = False
                res.issues.append(
                    f"Конец пути ({path[-1]}) ≠ цель ({route.pair.target})"
                )

            # ── 3. Неразрывность (все смежные узлы соединены ребром) ───
            for k in range(len(path) - 1):
                u, v = path[k], path[k + 1]
                if not g.has_node(u):
                    res.ok_continuous = False
                    res.issues.append(f"Узел {u} отсутствует в графе")
                    break
                if not g.has_node(v):
                    res.ok_continuous = False
                    res.issues.append(f"Узел {v} отсутствует в графе")
                    break
                if not g.has_edge(u, v):
                    res.ok_continuous = False
                    res.issues.append(
                        f"Разрыв: узлы {u} и {v} не соединены ребром графа"
                    )
                    break   # первый разрыв достаточен

            # ── 4. Коллизии с деталями (ray-trace) ────────────────────
            if part_meshes:
                positions = np.array(
                    [tuple(float(c) for c in p) for p in route.positions],
                    dtype=float,
                )
                for k in range(len(positions) - 1):
                    if self._stop:
                        break
                    a   = positions[k]
                    b   = positions[k + 1]
                    vec = b - a
                    lng = float(np.linalg.norm(vec))
                    if lng < 1e-9:
                        continue
                    eps   = lng * 0.02
                    unit  = vec / lng
                    start = (a + unit * eps).tolist()
                    end   = (b - unit * eps).tolist()
                    for mesh in part_meshes:
                        pts_hit, _ = mesh.ray_trace(start, end, first_point=False)
                        if len(pts_hit) >= 2:
                            res.ok_collision = False
                            res.issues.append(
                                f"Коллизия: отрезок {path[k]}→{path[k + 1]} "
                                f"пересекает деталь ({len(pts_hit)} пересечений)"
                            )
                            break   # первая коллизия на отрезке достаточна
                    if not res.ok_collision:
                        break       # первый проблемный отрезок достаточен

            results.append(res)

        self.sig_done.emit(results)


# диалог с таблицей результатов верификации маршрутов
# показывает три колонки проверок и список ошибок для выбранного маршрута
class _VerifyDialog(QDialog):
    _COL_OK  = "#a6e3a1"
    _COL_ERR = "#f38ba8"
    _COL_HDR = "#cdd6f4"

    def __init__(self, results: list, has_model: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Верификация маршрутов")
        self.setMinimumSize(700, 420)
        self.setModal(False)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(14, 14, 14, 14)

        # Сводка
        n_ok  = sum(1 for r in results if r.ok)
        n_all = len(results)
        summary_color = self._COL_OK if n_ok == n_all else self._COL_ERR
        lbl = QLabel(
            f"Проверено маршрутов: <b>{n_all}</b>   "
            f"Успешно: <b style='color:{summary_color}'>{n_ok}</b>   "
            f"С ошибками: <b style='color:{self._COL_ERR}'>{n_all - n_ok}</b>"
            + ("" if has_model else
               "   <span style='color:#f9e2af'>⚠ Модель не загружена — "
               "проверка коллизий пропущена</span>")
        )
        lbl.setTextFormat(Qt.RichText)
        lbl.setStyleSheet("font-size:9pt; padding:4px;")
        lbl.setWordWrap(True)
        lay.addWidget(lbl)

        # Таблица
        tbl = QTableWidget(n_all, 5)
        tbl.setHorizontalHeaderLabels(
            ["Маршрут", "Конечные точки", "Неразрывность", "Коллизии", "Итог"]
        )
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 5):
            tbl.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setAlternatingRowColors(False)
        tbl.setStyleSheet(
            "QTableWidget { background:#181825; border:1px solid #2a2a3d; "
            "gridline-color:#252535; }"
            "QTableWidget::item { padding:4px 8px; }"
            "QTableWidget::item:selected { background:#1e3358; }"
        )

        for ri, res in enumerate(results):
            def _cell(text, ok):
                it = QTableWidgetItem(text)
                it.setForeground(QColor(self._COL_OK if ok else self._COL_ERR))
                it.setTextAlignment(Qt.AlignCenter)
                return it

            # Маршрут
            name_item = QTableWidgetItem(res.label)
            name_item.setForeground(QColor(res.color))
            tbl.setItem(ri, 0, name_item)

            tbl.setItem(ri, 1, _cell("✓" if res.ok_endpoints  else "✗", res.ok_endpoints))
            tbl.setItem(ri, 2, _cell("✓" if res.ok_continuous else "✗", res.ok_continuous))

            if has_model:
                tbl.setItem(ri, 3, _cell("✓" if res.ok_collision else "✗", res.ok_collision))
            else:
                skip = QTableWidgetItem("—")
                skip.setForeground(QColor("#585b70"))
                skip.setTextAlignment(Qt.AlignCenter)
                tbl.setItem(ri, 3, skip)

            tbl.setItem(ri, 4, _cell("OK" if res.ok else "ОШИБКА", res.ok))

        lay.addWidget(tbl)

        # Список ошибок для выбранной строки
        lbl_issues_hdr = QLabel("Подробности (выберите строку):")
        lbl_issues_hdr.setStyleSheet("color:#6c7086; font-size:8pt;")
        lay.addWidget(lbl_issues_hdr)

        self._issues_box = QLabel("—")
        self._issues_box.setWordWrap(True)
        self._issues_box.setStyleSheet(
            "background:#181825; border:1px solid #2a2a3d; border-radius:5px;"
            "padding:6px 8px; color:#cdd6f4; font-size:8.5pt;"
        )
        self._issues_box.setMinimumHeight(52)
        lay.addWidget(self._issues_box)

        tbl.currentCellChanged.connect(
            lambda row, *_: self._show_issues(results[row] if 0 <= row < len(results) else None)
        )

        btn_close = QPushButton("Закрыть")
        btn_close.clicked.connect(self.accept)
        btn_close.setFixedWidth(100)
        row_btn = QHBoxLayout()
        row_btn.addStretch()
        row_btn.addWidget(btn_close)
        lay.addLayout(row_btn)

        # Тема
        self.setStyleSheet(
            "QDialog { background:#1e1e2e; color:#cdd6f4; }"
            "QPushButton { background:#2a2a3d; color:#cdd6f4; border:1px solid #3d3f5c;"
            "border-radius:6px; padding:4px 14px; }"
            "QPushButton:hover { background:#35364f; }"
        )

    def _show_issues(self, res: "_VerifyResult | None"):
        if res is None or not res.issues:
            self._issues_box.setText("Замечаний нет." if res else "—")
            self._issues_box.setStyleSheet(
                "background:#181825; border:1px solid #2a2a3d; border-radius:5px;"
                "padding:6px 8px; color:#6c7086; font-size:8.5pt;"
            )
        else:
            text = "\n".join(f"• {iss}" for iss in res.issues)
            self._issues_box.setText(text)
            self._issues_box.setStyleSheet(
                "background:#181825; border:1px solid #52243a; border-radius:5px;"
                "padding:6px 8px; color:#f38ba8; font-size:8.5pt;"
            )


# всплывающее уведомление в углу экрана, автоматически скрывается через заданное время
class _ToastWidget(QWidget):
    _COLORS = {
        "info":    ("#1e3358", "#89b4fa"),
        "success": ("#172d20", "#a6e3a1"),
        "warning": ("#3d2f10", "#f9e2af"),
        "error":   ("#3d1515", "#f38ba8"),
    }

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setWindowFlags(Qt.SubWindow)

        self._lbl = QLabel()
        self._lbl.setWordWrap(True)
        self._lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.addWidget(self._lbl)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, text: str, level: str = "info", ms: int = 3200):
        bg, fg = self._COLORS.get(level, self._COLORS["info"])
        self._lbl.setText(text)
        self._lbl.setStyleSheet(f"color:{fg}; font-size:9pt; font-weight:600;")
        self.setStyleSheet(
            f"background:{bg}; border:1px solid {fg}; border-radius:8px;"
        )
        self.adjustSize()
        self.setMinimumWidth(300)
        self._reposition()
        self.raise_()
        self.show()
        self._timer.start(ms)

    def _reposition(self):
        p = self.parent()
        if p is None:
            return
        margin = 16
        self.move(p.width() - self.width() - margin,
                  p.height() - self.height() - margin - 32)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition()


# главное окно приложения — объединяет 3d-вид, боковую панель и всю логику
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Трассировка жгутовых межмодульных соединений")
        self.setMinimumSize(1280, 700)
        s = QSettings("КАИ", "Трассировщик")
        self._is_dark_theme: bool = s.value("dark_theme", True, type=bool)
        self.setStyleSheet(_STYLE if self._is_dark_theme else _STYLE_LIGHT)

        # граф кабельных каналов, список пар соединений и найденных маршрутов
        self._graph = CableChannelGraph()
        self._pairs: list = []       # list[ConnectionPair]
        self._routes: list = []

        # текущий режим работы и вспомогательные переменные для пошаговых операций
        self._mode = MODE_NAVIGATE
        self._edge_first: Optional[int] = None    # первый узел при добавлении ребра
        self._pair_first: Optional[int] = None    # первый узел при добавлении пары
        self._worker: Optional[_TracingWorker] = None
        self._load_worker: Optional[_ModelLoadWorker] = None
        self._autosel_worker: Optional[_AutoSelectWorker] = None
        self._verify_worker: Optional[_VerifyWorker] = None
        self._undo_stack = _UndoStack()

        self._current_model_path: str = ""
        self._algo_mode: str = "aco"   # выбранный алгоритм: "aco" или "dijkstra"
        self._aco_fallback: bool = True

        # словари акторов pyvista — каждый ключ связан с актором в 3d-сцене
        self._parts_data: list[dict] = []           # каждая деталь: actor, color, name, visible, mesh
        self._highlighted_part: Optional[int] = None
        self._node_actors:    dict = {}             # id → actor
        self._edge_actors:    dict = {}             # (u,v) → actor
        self._edge_collisions: set = set()          # ключи рёбер, проходящих сквозь детали
        self._graph_verify_worker = None
        self._pair_actors:  list = []
        self._route_actors: list = []
        self._edges_visible: bool = True
        self._route_actor_map: dict = {}            # mapper → route index (для пикинга маршрутов)
        self._bundle_actors: list = []              # трубки-индикаторы объединения проводов
        self._emc_actors:    list = []              # красные маркеры эмс-нарушений
        self._highlight_actor = None

        # данные равномерной сетки для выбора рёбер каналов
        self._grid_nodes: list = []        # list of (x, y, z)
        self._grid_edge_pairs: list = []   # list of (i, j) — индексы узлов
        self._grid_selected: set = set()   # индексы выбранных рёбер
        self._grid_actor = None
        self._grid_hover_idx: Optional[int] = None
        self._grid_hover_actor = None

        # данные ручной трассировки — заполняются при нажатии "трассировать вручную"
        self._manual_pair: Optional[ConnectionPair] = None
        self._manual_path: list[int] = []
        self._manual_preview_actor = None   # трубка пройденного пути
        self._manual_cur_actor     = None   # сфера текущей позиции
        self._manual_nb_actors:  list = []  # сферы допустимых соседних узлов
        self._manual_tgt_actor     = None   # сфера узла-цели

        # точки и акторы при рисовании трассы полилинией (режим draw_channel)
        self._polyline_pts:         list = []   # накопленные 3d-точки
        self._polyline_seg_actors:  list = []   # акторы сегментов
        self._polyline_node_actors: list = []   # акторы сфер точек
        self._polyline_preview_actor     = None # превью-линия до курсора

        # размеры маркеров в мм — пересчитываются из диагонали загруженной модели
        self._sphere_r = 0.8
        self._tube_r   = 0.8

        self._build_ui()
        self._refresh_inline_styles()
        self._refresh_all_lists()
        self._set_status("Загрузите 3D-модель кнопкой «Открыть модель»")

    # построение интерфейса

    def _build_ui(self):
        self._build_menu()
        self._build_toolbar()
        self._build_viewport()
        self._build_left_dock()
        self._build_status_bar()
        self._install_shortcuts()
        self._toast_widget = _ToastWidget(self.centralWidget())

    def _toast(self, text: str, level: str = "info", ms: int = 3200):
        self._toast_widget._reposition()
        self._toast_widget.show_message(text, level, ms)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_toast_widget"):
            self._toast_widget._reposition()

    # ── Drag-and-drop ─────────────────────────────────────────────────────
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            exts = {".stl", ".obj", ".ply", ".vtk", ".vtp",
                    ".glb", ".gltf", ".wrl", ".vrml"}
            if any(
                Path(u.toLocalFile()).suffix.lower() in exts
                for u in event.mimeData().urls()
            ):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        self._load_model_path(path)

    def _build_menu(self):
        mb = self.menuBar()

        # ── Файл ──────────────────────────────────────────────────────────
        m_file = mb.addMenu("Файл")

        a = QAction("Открыть модель…", self)
        a.setShortcut("Ctrl+O")
        a.triggered.connect(self._open_model)
        m_file.addAction(a)

        self._recent_menu = m_file.addMenu("Недавние файлы")
        self._rebuild_recent_menu()

        m_file.addSeparator()

        a = QAction("Сохранить граф", self)
        a.setShortcut("Ctrl+S")
        a.triggered.connect(self._save_graph)
        m_file.addAction(a)

        a = QAction("Загрузить граф…", self)
        a.triggered.connect(self._load_graph)
        m_file.addAction(a)

        m_file.addSeparator()

        a = QAction("Экспорт маршрутов в DXF…", self)
        a.setShortcut("Ctrl+E")
        a.triggered.connect(self._export_dxf)
        m_file.addAction(a)

        # ── База данных ───────────────────────────────────────────────────
        m_db = mb.addMenu("База данных")

        a = QAction("Сохранить проект в БД…", self)
        a.setShortcut("Ctrl+Shift+S")
        a.triggered.connect(self._db_save)
        m_db.addAction(a)

        a = QAction("Загрузить проект из БД…", self)
        a.setShortcut("Ctrl+Shift+O")
        a.triggered.connect(self._db_load)
        m_db.addAction(a)

        m_db.addSeparator()

        a = QAction("Менеджер базы данных…", self)
        a.triggered.connect(self._open_db_manager)
        m_db.addAction(a)

        m_db.addSeparator()

        a = QAction("Настройки подключения к БД…", self)
        a.triggered.connect(self._open_db_settings)
        m_db.addAction(a)

        # ── Вид ───────────────────────────────────────────────────────────
        m_view = mb.addMenu("Вид")
        self._act_results_panel = QAction("Панель результатов", self)
        self._act_results_panel.setCheckable(True)
        self._act_results_panel.setChecked(True)
        self._act_results_panel.setShortcut("Ctrl+R")
        m_view.addAction(self._act_results_panel)

        m_view.addSeparator()

        self._act_light_theme = QAction("Светлая тема", self)
        self._act_light_theme.setCheckable(True)
        self._act_light_theme.setChecked(not self._is_dark_theme)
        self._act_light_theme.setShortcut("Ctrl+Shift+T")
        self._act_light_theme.triggered.connect(self._toggle_theme)
        m_view.addAction(self._act_light_theme)

    # ключ и максимальное количество недавних файлов в qsettings
    _RECENT_KEY = "recent_models"
    _RECENT_MAX = 5

    def _add_recent_file(self, path: str):
        s = QSettings("КАИ", "Трассировщик")
        files: list[str] = s.value(self._RECENT_KEY, []) or []
        path = str(Path(path).resolve())
        if path in files:
            files.remove(path)
        files.insert(0, path)
        s.setValue(self._RECENT_KEY, files[: self._RECENT_MAX])
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self):
        self._recent_menu.clear()
        s = QSettings("КАИ", "Трассировщик")
        files: list[str] = s.value(self._RECENT_KEY, []) or []
        if not files:
            a = QAction("(список пуст)", self)
            a.setEnabled(False)
            self._recent_menu.addAction(a)
            return
        for path in files:
            a = QAction(Path(path).name, self)
            a.setToolTip(path)
            a.triggered.connect(lambda checked, p=path: self._load_model_path(p))
            self._recent_menu.addAction(a)
        self._recent_menu.addSeparator()
        clr = QAction("Очистить список", self)
        clr.triggered.connect(self._clear_recent)
        self._recent_menu.addAction(clr)

    def _clear_recent(self):
        QSettings("КАИ", "Трассировщик").remove(self._RECENT_KEY)
        self._rebuild_recent_menu()

    def _load_model_path(self, path: str):
        if not Path(path).exists():
            QMessageBox.warning(self, "Файл не найден", f"Файл не существует:\n{path}")
            return
        self._load_worker = _ModelLoadWorker(path)
        self._load_worker.sig_done.connect(self._on_model_loaded)
        self._load_worker.sig_error.connect(self._on_model_error)
        self._load_worker.finished.connect(self._on_load_finished)
        self._set_status(f"Загружается: {Path(path).name}…")
        self._load_worker.start()

    def _undo(self):
        if self._undo_stack.undo():
            self._update_edit_actions()

    def _redo(self):
        if self._undo_stack.redo():
            self._update_edit_actions()

    def _update_edit_actions(self):
        can_u = self._undo_stack.can_undo()
        self._btn_undo.setEnabled(can_u)
        t = self._undo_stack.undo_text()
        self._btn_undo.setToolTip(f"Отменить: {t}  (Ctrl+Z)" if t else "Отменить (Ctrl+Z)")

        can_r = self._undo_stack.can_redo()
        self._btn_redo.setEnabled(can_r)
        t = self._undo_stack.redo_text()
        self._btn_redo.setToolTip(f"Повторить: {t}  (Ctrl+Y)" if t else "Повторить (Ctrl+Y)")

    # --- Строка состояния ----------------------------------------------
    def _build_status_bar(self):
        sb = self.statusBar()
        sb.setVisible(True)
        sb.setStyleSheet(
            "QStatusBar{background:#181825;color:#6c7086;"
            "border-top:1px solid #2a2a3d;padding:0 8px;font-size:8.5pt;}"
            "QStatusBar::item{border:none;}"
            "QLabel{color:#a6adc8;padding:0 4px;}"
        )

        self._lbl_hint = QLabel("")
        sb.addWidget(self._lbl_hint, 1)

        self._prog_bar = QProgressBar()
        self._prog_bar.setRange(0, 100)
        self._prog_bar.setFixedWidth(200)
        self._prog_bar.setFixedHeight(8)
        self._prog_bar.setTextVisible(False)
        self._prog_bar.setVisible(False)
        sb.addWidget(self._prog_bar)

        self._btn_cancel = QPushButton("Отменить")
        self._btn_cancel.setFixedHeight(22)
        self._btn_cancel.setFixedWidth(80)
        self._btn_cancel.setVisible(False)
        self._btn_cancel.setObjectName("dangerBtn")
        self._btn_cancel.setStyleSheet(
            "QPushButton#dangerBtn{border-radius:4px;padding:2px 8px;font-size:8pt;}"
        )
        self._btn_cancel.clicked.connect(self._cancel_current)
        sb.addWidget(self._btn_cancel)

        sep = QLabel("  │  ")
        sep.setStyleSheet("color:#2a2a3d;")
        sb.addPermanentWidget(sep)

        self._lbl_stats = QLabel("Узлов: 0   Рёбер: 0   Соединений: 0")
        pass  # стиль ставится в _refresh_inline_styles
        sb.addPermanentWidget(self._lbl_stats)

    def _update_stats(self):
        g = self._graph.networkx_graph()
        self._lbl_stats.setText(
            f"Узлов: {g.number_of_nodes()}   "
            f"Рёбер: {g.number_of_edges()}   "
            f"Соединений: {len(self._pairs)}"
        )

    # --- Клавиатурные сочетания ----------------------------------------
    def _install_shortcuts(self):
        def sc(key, slot):
            QShortcut(QKeySequence(key), self).activated.connect(slot)

        sc("Ctrl+O", self._open_model)
        sc("Ctrl+S", self._save_graph)
        sc("Ctrl+Shift+S", self._save_graph)
        sc("Ctrl+T", self._run_aco)
        sc("Delete", self._delete_selected)

        for i in range(4):
            idx = i
            sc(f"F{i + 1}", lambda checked=False, n=idx: self._tabs.setCurrentIndex(n))

        sc("R", self._reset_camera)
        sc("Space", self._toggle_navigate)
        sc("Return",       self._polyline_finish_if_active)
        sc("Escape",       self._polyline_cancel_if_active)

    def _delete_selected(self):
        focused = QApplication.focusWidget()
        if focused is self._lst_nodes:
            self._delete_selected_node()
        elif focused is self._lst_edges:
            self._delete_selected_edge()
        elif focused is self._lst_pairs:
            self._delete_selected_pair()

    def _reset_camera(self):
        self.plotter.reset_camera()
        self.plotter.render()

    def _toggle_navigate(self):
        if self._mode == MODE_NAVIGATE:
            self._set_mode(self._prev_mode if hasattr(self, "_prev_mode") else MODE_ADD_NODE)
        else:
            self._prev_mode = self._mode
            self._set_mode(MODE_NAVIGATE)

    # --- Панель инструментов -------------------------------------------
    def _build_toolbar(self):
        tb = QToolBar(self)
        tb.setMovable(False)
        tb.setFixedHeight(44)
        self.addToolBar(Qt.TopToolBarArea, tb)

        H = 28  # единая высота всех кнопок

        def _btn(text: str, name: str = None) -> QPushButton:
            b = QPushButton(text)
            b.setFixedHeight(H)
            if name: b.setObjectName(name)
            return b

        # Отменить / Повторить
        self._btn_undo = _btn("↩")
        self._btn_undo.setFixedWidth(32)
        self._btn_undo.setEnabled(False)
        self._btn_undo.setToolTip("Отменить (Ctrl+Z)")
        self._btn_undo.clicked.connect(self._undo)
        tb.addWidget(self._btn_undo)

        self._btn_redo = _btn("↪")
        self._btn_redo.setFixedWidth(32)
        self._btn_redo.setEnabled(False)
        self._btn_redo.setToolTip("Повторить (Ctrl+Y)")
        self._btn_redo.clicked.connect(self._redo)
        tb.addWidget(self._btn_redo)

        tb.addSeparator()

        # Сегментированные кнопки режима
        grp = QButtonGroup(self)
        grp.setExclusive(True)
        self._btn_nav  = self._mk_mode_btn("Навигация", MODE_NAVIGATE, grp, tb, "modeFirst")
        self._btn_node = self._mk_mode_btn("Узел",      MODE_ADD_NODE,  grp, tb, "modeMid")
        self._btn_edge = self._mk_mode_btn("Ребро",     MODE_ADD_EDGE,  grp, tb, "modeMid")
        self._btn_pair = self._mk_mode_btn("Пара",      MODE_ADD_PAIR,  grp, tb, "modeLast")
        self._btn_nav.setChecked(True)

        tb.addSeparator()

        # Трассировать
        self._btn_run = _btn("▶  Запустить трассировку", name="runBtn")
        self._btn_run.clicked.connect(self._run_aco)
        tb.addWidget(self._btn_run)

        tb.addSeparator()

        # Видимость рёбер канала
        self._btn_toggle_edges = _btn("Каналы", name="viewToggleBtn")
        self._btn_toggle_edges.setCheckable(True)
        self._btn_toggle_edges.setChecked(True)
        self._btn_toggle_edges.setToolTip("Показать / скрыть рёбра кабельных каналов")
        self._btn_toggle_edges.toggled.connect(self._toggle_edges_visibility)
        tb.addWidget(self._btn_toggle_edges)

        tb.addSeparator()

        # Очистка (danger)
        b_routes = _btn("Сбросить маршруты", name="dangerBtn")
        b_routes.setToolTip("Сбросить найденные маршруты")
        b_routes.clicked.connect(self._clear_routes)
        tb.addWidget(b_routes)

        tb.addSeparator()

        b_all = _btn("Очистить всё", name="dangerBtn")
        b_all.setToolTip("Очистить граф и маршруты")
        b_all.clicked.connect(self._confirm_clear_all)
        tb.addWidget(b_all)

    def _mk_mode_btn(self, text: str, mode: str,
                     grp: QButtonGroup, tb: QToolBar,
                     obj_name: str = "modeMid") -> QPushButton:
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setFixedHeight(28)
        btn.setObjectName(obj_name)
        btn.clicked.connect(lambda: self._set_mode(mode))
        grp.addButton(btn)
        tb.addWidget(btn)
        return btn

    # --- 3D-вид (центральный виджет) -----------------------------------
    def _build_viewport(self):
        self._viewport_frame = QFrame(self)
        self._viewport_frame.setObjectName("viewportFrame")
        layout = QVBoxLayout(self._viewport_frame)
        layout.setContentsMargins(0, 0, 0, 0)

        self.plotter = QtInteractor(self._viewport_frame)
        self.plotter.set_background([0.06, 0.06, 0.10])
        self.plotter.add_axes(line_width=2)
        layout.addWidget(self.plotter.interactor)

        self.setAcceptDrops(True)
        self.setCentralWidget(self._viewport_frame)

        # Контекстное меню по правому клику (постоянный фильтр)
        self._ctx_filter = _ContextMenuFilter(
            self.plotter.interactor, self._show_viewport_context_menu
        )
        self.plotter.interactor.installEventFilter(self._ctx_filter)

    # --- Левая боковая панель ------------------------------------------
    def _build_left_dock(self):
        dock = QDockWidget("Панель управления", self)
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._tab_parts(),      "Детали")
        self._tabs.addTab(self._tab_channels(),   "Кабельные каналы")
        self._tabs.addTab(self._tab_pairs(),      "Соединения")
        self._tabs.addTab(self._tab_aco(),        "Параметры алгоритма")
        vbox.addWidget(self._tabs)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(container)

        dock.setWidget(scroll)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        dock.setMinimumWidth(365)

        self._build_results_dock()
        self._act_results_panel.toggled.connect(self._results_dock.setVisible)
        self._results_dock.visibilityChanged.connect(self._act_results_panel.setChecked)


    # --- Вкладка «Детали» ----------------------------------------------
    def _tab_parts(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(8)
        v.setContentsMargins(8, 8, 8, 8)

        hint = QLabel("Загрузите GLTF/GLB модель,\nчтобы увидеть список деталей.")
        hint.setStyleSheet("color:#6c7086; font-size:8pt; padding:4px;")
        hint.setAlignment(Qt.AlignCenter)
        v.addWidget(hint)
        self._parts_hint = hint

        self._lst_parts = QListWidget()
        self._lst_parts.setMinimumHeight(200)
        self._lst_parts.itemChanged.connect(self._on_part_visibility_changed)
        self._lst_parts.currentRowChanged.connect(self._on_part_selected)
        v.addWidget(self._lst_parts)

        row = QHBoxLayout()
        btn_show = QPushButton("Показать все")
        btn_show.clicked.connect(self._show_all_parts)
        btn_iso = QPushButton("Только эта")
        btn_iso.clicked.connect(self._isolate_part)
        row.addWidget(btn_show)
        row.addWidget(btn_iso)
        v.addLayout(row)

        v.addStretch()
        return w

    # --- Вкладка «Кабельные каналы» ------------------------------------
    def _tab_channels(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(8)
        v.setContentsMargins(8, 8, 8, 8)

        # ── Переключатель способа задания ─────────────────────────────
        lbl_method = QLabel("Способ задания каналов:")
        lbl_method.setObjectName("accentLabel")
        v.addWidget(lbl_method)

        grp_switch = QButtonGroup(w)
        grp_switch.setExclusive(True)

        row_switch = QHBoxLayout()
        row_switch.setSpacing(0)

        btn_grid_mode = QPushButton("По сетке")
        btn_grid_mode.setCheckable(True)
        btn_grid_mode.setChecked(True)
        btn_grid_mode.setObjectName("modeFirst")
        btn_grid_mode.setMinimumHeight(32)
        btn_grid_mode.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        btn_pts_mode = QPushButton("По точкам")
        btn_pts_mode.setCheckable(True)
        btn_pts_mode.setObjectName("modeLast")
        btn_pts_mode.setMinimumHeight(32)
        btn_pts_mode.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        grp_switch.addButton(btn_grid_mode)
        grp_switch.addButton(btn_pts_mode)
        row_switch.addWidget(btn_grid_mode)
        row_switch.addWidget(btn_pts_mode)
        v.addLayout(row_switch)

        # ── Две панели (show/hide вместо QStackedWidget) ──────────────
        def _no_space_when_hidden(w):
            sp = w.sizePolicy()
            sp.setRetainSizeWhenHidden(False)
            w.setSizePolicy(sp)

        # ── Страница 0: По сетке ──────────────────────────────────────
        page_grid = QWidget()
        _no_space_when_hidden(page_grid)
        pg = QVBoxLayout(page_grid)
        pg.setContentsMargins(0, 4, 0, 0)
        pg.setSpacing(8)

        desc_grid = QLabel(
            "Равномерная сетка узлов строится вокруг 3D-модели. "
            "Выберите нужные рёбра вручную или автоматически по поверхности, "
            "затем нажмите «Применить к графу»."
        )
        desc_grid.setStyleSheet("color:#6c7086; font-size:8pt;")
        desc_grid.setWordWrap(True)
        pg.addWidget(desc_grid)

        gb_params = QGroupBox("Параметры сетки")
        form = QFormLayout(gb_params)
        form.setSpacing(9)
        form.setContentsMargins(10, 16, 10, 10)
        self._sp_grid_step = QDoubleSpinBox()
        self._sp_grid_step.setRange(0.5, 100000.0)
        self._sp_grid_step.setValue(50.0)
        self._sp_grid_step.setSuffix(" мм")
        self._sp_grid_step.setDecimals(1)
        form.addRow("Шаг сетки:", self._sp_grid_step)
        pg.addWidget(gb_params)

        btn_build = QPushButton("Создать сетку")
        btn_build.setFixedHeight(36)
        btn_build.clicked.connect(self._build_grid)
        pg.addWidget(btn_build)

        gb_auto = QGroupBox("Авто-выбор по поверхности модели")
        form2 = QFormLayout(gb_auto)
        form2.setSpacing(9)
        form2.setContentsMargins(10, 16, 10, 10)
        self._sp_grid_surf_dist = QDoubleSpinBox()
        self._sp_grid_surf_dist.setRange(0.1, 100000.0)
        self._sp_grid_surf_dist.setValue(30.0)
        self._sp_grid_surf_dist.setSuffix(" мм")
        self._sp_grid_surf_dist.setDecimals(1)
        form2.addRow("Порог расстояния:", self._sp_grid_surf_dist)
        note = QLabel("Рёбра, чья середина ближе к\nповерхности модели, выбираются.")
        note.setStyleSheet("color:#6c7086; font-size:8pt;")
        note.setWordWrap(True)
        form2.addRow(note)
        btn_auto = QPushButton("Выбрать по поверхности")
        btn_auto.setFixedHeight(34)
        btn_auto.clicked.connect(self._auto_select_near_surface)
        form2.addRow(btn_auto)
        pg.addWidget(gb_auto)

        gb_sel = QGroupBox("Ручная корректировка")
        vg = QVBoxLayout(gb_sel)
        vg.setSpacing(6)
        self._lbl_grid_count = QLabel("Сетка не создана")
        self._lbl_grid_count.setStyleSheet("color:#6c7086; font-size:8pt; padding:2px;")
        self._lbl_grid_count.setAlignment(Qt.AlignCenter)
        vg.addWidget(self._lbl_grid_count)
        hint2 = QLabel("Кликните ребро в 3D-виде — добавить/убрать")
        hint2.setStyleSheet("color:#6c7086; font-size:8pt;")
        hint2.setWordWrap(True)
        vg.addWidget(hint2)
        row = QHBoxLayout()
        btn_all = QPushButton("Выбрать все")
        btn_all.clicked.connect(self._select_all_grid_edges)
        btn_none = QPushButton("Снять всё")
        btn_none.clicked.connect(self._clear_grid_selection)
        row.addWidget(btn_all)
        row.addWidget(btn_none)
        vg.addLayout(row)
        pg.addWidget(gb_sel)

        btn_apply = QPushButton("Применить к графу")
        btn_apply.setObjectName("runBtn")
        btn_apply.setFixedHeight(36)
        btn_apply.clicked.connect(self._apply_grid_to_graph)
        pg.addWidget(btn_apply)

        btn_clear_grid = QPushButton("Удалить сетку")
        btn_clear_grid.setFixedHeight(34)
        btn_clear_grid.setObjectName("dangerBtn")
        btn_clear_grid.clicked.connect(self._clear_grid)
        pg.addWidget(btn_clear_grid)

        # ── Страница 1: По точкам ─────────────────────────────────────
        page_pts = QWidget()
        _no_space_when_hidden(page_pts)
        pp = QVBoxLayout(page_pts)
        pp.setContentsMargins(0, 4, 0, 0)
        pp.setSpacing(6)

        desc_pts = QLabel(
            "Кликайте по поверхности модели или существующим узлам. "
            "Узел/Ребро — через кнопки на панели инструментов."
        )
        desc_pts.setStyleSheet("color:#6c7086; font-size:8pt;")
        desc_pts.setWordWrap(True)
        pp.addWidget(desc_pts)

        gb_draw = QGroupBox("Нарисовать трассу (полилиния)")
        vd = QVBoxLayout(gb_draw)
        vd.setSpacing(5)
        vd.setContentsMargins(8, 12, 8, 8)

        self._lbl_polyline_status = QLabel("")
        self._lbl_polyline_status.setWordWrap(True)
        self._lbl_polyline_status.setVisible(False)
        vd.addWidget(self._lbl_polyline_status)

        self._btn_polyline_start = QPushButton("Нарисовать трассу")
        self._btn_polyline_start.setFixedHeight(34)
        self._btn_polyline_start.clicked.connect(
            lambda: self._set_mode(MODE_DRAW_CHANNEL)
        )
        vd.addWidget(self._btn_polyline_start)

        row_pl = QHBoxLayout()
        self._btn_polyline_undo = QPushButton("← Шаг назад")
        self._btn_polyline_undo.setEnabled(False)
        self._btn_polyline_undo.clicked.connect(self._polyline_undo_last)
        row_pl.addWidget(self._btn_polyline_undo)

        self._btn_polyline_ok = QPushButton("✓ Зафиксировать")
        self._btn_polyline_ok.setEnabled(False)
        self._btn_polyline_ok.clicked.connect(self._finalize_polyline)
        row_pl.addWidget(self._btn_polyline_ok)
        vd.addLayout(row_pl)

        self._btn_polyline_cancel = QPushButton("✕ Отменить трассу")
        self._btn_polyline_cancel.setObjectName("dangerBtn")
        self._btn_polyline_cancel.setEnabled(False)
        self._btn_polyline_cancel.setFixedHeight(30)
        self._btn_polyline_cancel.clicked.connect(self._cancel_polyline)
        vd.addWidget(self._btn_polyline_cancel)

        pp.addWidget(gb_draw)
        page_pts.setVisible(False)

        # ── Подключаем переключатель ──────────────────────────────────
        def _show_grid():
            page_grid.setVisible(True)
            page_pts.setVisible(False)

        def _show_pts():
            page_grid.setVisible(False)
            page_pts.setVisible(True)

        btn_grid_mode.clicked.connect(_show_grid)
        btn_pts_mode.clicked.connect(_show_pts)

        v.addWidget(page_grid)
        v.addWidget(page_pts)

        # ── Узлы (всегда видны) ───────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#2a2a3d;")
        v.addWidget(sep)

        gb_n = QGroupBox("Узлы кабельных каналов")
        vn = QVBoxLayout(gb_n)
        self._lst_nodes = QListWidget()
        self._lst_nodes.setMinimumHeight(110)
        vn.addWidget(self._lst_nodes)
        btn_del_n = QPushButton("Удалить выбранный узел")
        btn_del_n.setObjectName("delBtn")
        btn_del_n.clicked.connect(self._delete_selected_node)
        vn.addWidget(btn_del_n)
        v.addWidget(gb_n)

        # ── Рёбра (всегда видны) ──────────────────────────────────────
        gb_e = QGroupBox("Рёбра (сегменты каналов)")
        ve = QVBoxLayout(gb_e)
        self._lst_edges = QListWidget()
        self._lst_edges.setMinimumHeight(90)
        ve.addWidget(self._lst_edges)
        btn_del_e = QPushButton("Удалить выбранное ребро")
        btn_del_e.setObjectName("delBtn")
        btn_del_e.clicked.connect(self._delete_selected_edge)
        ve.addWidget(btn_del_e)

        self._btn_graph_verify = QPushButton("Верификация рёбер графа")
        self._btn_graph_verify.setToolTip(
            "Подсветить красным рёбра, проходящие сквозь детали модели"
        )
        self._btn_graph_verify.clicked.connect(self._run_graph_edge_verify)
        ve.addWidget(self._btn_graph_verify)
        v.addWidget(gb_e)
        return w

    # --- Вкладка «Соединения» ------------------------------------------
    def _tab_pairs(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(8)
        v.setContentsMargins(8, 8, 8, 8)

        # --- Список пар ---
        gb = QGroupBox("Соединения")
        vg = QVBoxLayout(gb)

        hint = QLabel(
            "Чтобы добавить пару:\n"
            "1. Нажмите кнопку «Пара» на панели\n"
            "2. Кликните узел-источник\n"
            "3. Кликните узел-цель"
        )
        hint.setStyleSheet("color:#6c7086; font-size:8pt; padding:4px;")
        hint.setWordWrap(True)
        vg.addWidget(hint)

        self._lst_pairs = QListWidget()
        self._lst_pairs.setMinimumHeight(120)
        self._lst_pairs.currentRowChanged.connect(self._on_pair_selected)
        vg.addWidget(self._lst_pairs)

        btn_del = QPushButton("Удалить выбранную пару")
        btn_del.setObjectName("delBtn")
        btn_del.clicked.connect(self._delete_selected_pair)
        vg.addWidget(btn_del)

        v.addWidget(gb)

        # --- Параметры выбранного соединения ---
        gb2 = QGroupBox("Параметры выбранного соединения")
        form = QFormLayout(gb2)
        form.setSpacing(9)
        form.setContentsMargins(10, 16, 10, 10)

        self._cmb_cable_type = QComboBox()
        self._cmb_cable_type.addItems(
            [wt.value for wt in WireType]
        )
        self._cmb_cable_type.setEnabled(False)
        self._cmb_cable_type.currentTextChanged.connect(self._on_emc_type_changed)
        form.addRow("Тип провода:", self._cmb_cable_type)

        self._chk_shielded = QCheckBox("Экранированный")
        self._chk_shielded.setEnabled(False)
        self._chk_shielded.stateChanged.connect(self._on_shielded_changed)
        form.addRow("Экранирование:", self._chk_shielded)

        v.addWidget(gb2)

        # --- Матрица ЭМС-совместимости ---
        gb3 = QGroupBox("Матрица ЭМС-совместимости")
        vg3 = QVBoxLayout(gb3)

        self._tbl_emc = QTableWidget()
        self._tbl_emc.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_emc.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._tbl_emc.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._tbl_emc.setMinimumHeight(80)
        vg3.addWidget(self._tbl_emc)

        v.addWidget(gb3)
        return w

    # возвращает цвет нужной семантики для текущей темы
    def _color(self, name: str) -> str:
        dark = {
            "hint":      "#6c7086",
            "secondary": "#7f849c",
            "stats":     "#585b70",
            "success":   "#a6e3a1",
            "warning":   "#fab387",
            "value":     "#a6e3a1",
            "primary":   "#cdd6f4",
            "muted":     "#94e2d5",
            "fallback":  "#a6adc8",
            "sep":       "#45475a",
        }
        light = {
            "hint":      "#6b7280",
            "secondary": "#6b7280",
            "stats":     "#6b7280",
            "success":   "#166534",
            "warning":   "#c2410c",
            "value":     "#166534",
            "primary":   "#212529",
            "muted":     "#059669",
            "fallback":  "#374151",
            "sep":       "#adb5bd",
        }
        return (dark if self._is_dark_theme else light).get(name, "#000000")

    # обновляет inline-стили виджетов которые не покрываются основным stylesheet
    def _refresh_inline_styles(self):
        dark = self._is_dark_theme
        # строка состояния
        self.statusBar().setStyleSheet(
            f"QStatusBar{{background:{'#181825' if dark else '#e9ecef'};"
            f"color:{self._color('hint')};"
            f"border-top:1px solid {'#2a2a3d' if dark else '#ced4da'};"
            f"padding:0 8px;font-size:8.5pt;}}"
            f"QStatusBar::item{{border:none;}}"
            f"QLabel{{color:{self._color('hint')};padding:0 4px;}}"
        )
        self._lbl_hint.setStyleSheet(
            f"color:{self._color('secondary')}; font-style:italic;"
        )
        self._lbl_stats.setStyleSheet(
            f"color:{self._color('stats')}; padding-right:6px; font-size:8pt;"
        )
        # блок метрик результатов
        bg  = "#172d20" if dark else "#dcfce7"
        brd = "#2d5040" if dark else "#86efac"
        self._metrics_frame.setStyleSheet(
            f"QFrame{{background:{bg};border:1px solid {brd};border-radius:6px;}}"
            f"QLabel{{background:transparent;border:none;}}"
        )
        val_color = self._color("value")
        for lbl in (self._lbl_f1_val, self._lbl_f2_val, self._lbl_obj_val):
            lbl.setStyleSheet(f"color:{val_color}; font-weight:600; font-size:9pt;")
        # параметры алгоритма
        self._lbl_lambda.setStyleSheet(
            f"color:{self._color('primary')}; font-size:8pt;"
        )
        self._chk_fallback.setStyleSheet(
            f"color:{self._color('fallback')}; font-size:8pt;"
        )
        self._lbl_polyline_status.setStyleSheet(
            f"color:{self._color('muted')}; font-size:8pt; padding:2px;"
        )
        self._lbl_manual_status.setStyleSheet(
            f"color:{self._color('hint')}; font-size:8pt; padding:2px;"
        )

    # переключает тему между тёмной и светлой и сохраняет выбор в настройках
    def _toggle_theme(self, checked: bool):
        self._is_dark_theme = not checked
        self.setStyleSheet(_STYLE if self._is_dark_theme else _STYLE_LIGHT)
        self._refresh_inline_styles()
        QSettings("КАИ", "Трассировщик").setValue("dark_theme", self._is_dark_theme)

    # создаёт маленькую кнопку ⓘ с подробной всплывающей подсказкой
    def _make_info_btn(self, text: str) -> QPushButton:
        btn = QPushButton("ⓘ")
        btn.setObjectName("infoBtn")
        btn.setFixedSize(22, 22)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setCursor(Qt.WhatsThisCursor)
        btn.setToolTip(f"<html><body style='font-size:8.5pt; max-width:280px;'>{text}</body></html>")
        btn.setToolTipDuration(12000)
        return btn

    # --- Вкладка «Параметры алгоритма» ---------------------------------
    def _tab_aco(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(8)
        v.setContentsMargins(8, 8, 8, 8)

        # === Выбор алгоритма ===
        gb_algo = QGroupBox("Алгоритм автоматической трассировки")
        vg_algo = QVBoxLayout(gb_algo)
        vg_algo.setSpacing(6)
        vg_algo.setContentsMargins(10, 14, 10, 10)

        grp_algo_btn = QButtonGroup(w)
        grp_algo_btn.setExclusive(True)
        row_algo = QHBoxLayout()
        row_algo.setSpacing(0)

        self._btn_algo_aco = QPushButton("Муравьиный алгоритм")
        self._btn_algo_aco.setCheckable(True)
        self._btn_algo_aco.setChecked(True)
        self._btn_algo_aco.setObjectName("modeFirst")
        self._btn_algo_aco.setMinimumHeight(36)
        self._btn_algo_aco.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_algo_aco.setToolTip(
            "Муравьиный алгоритм\n"
            "Учитывает объединение проводов и ЭМС; вероятностный поиск"
        )

        self._btn_algo_dijkstra = QPushButton("Алгоритм Дейкстры")
        self._btn_algo_dijkstra.setCheckable(True)
        self._btn_algo_dijkstra.setObjectName("modeLast")
        self._btn_algo_dijkstra.setMinimumHeight(36)
        self._btn_algo_dijkstra.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_algo_dijkstra.setToolTip(
            "Алгоритм Дейкстры\n"
            "Гарантированно находит кратчайший путь; мгновенно"
        )

        grp_algo_btn.addButton(self._btn_algo_aco)
        grp_algo_btn.addButton(self._btn_algo_dijkstra)
        row_algo.addWidget(self._btn_algo_aco)
        row_algo.addWidget(self._btn_algo_dijkstra)
        vg_algo.addLayout(row_algo)

        self._chk_fallback = QCheckBox(
            "Резерв: Дейкстра, если Муравьиный алгоритм не нашёл путь"
        )
        self._chk_fallback.setChecked(True)
        self._chk_fallback.setToolTip(
            "Если муравьиный алгоритм не нашёл маршрут для пары,\n"
            "автоматически применить Дейкстру как резервный метод"
        )
        vg_algo.addWidget(self._chk_fallback)

        algo_desc = QLabel(
            "Дейкстра — не требует настройки, всегда кратчайший путь.\n"
            "Параметры Муравьиного алгоритма — ниже на этой вкладке."
        )
        algo_desc.setStyleSheet("color:#6c7086; font-size:8pt;")
        algo_desc.setWordWrap(True)
        vg_algo.addWidget(algo_desc)

        self._btn_algo_aco.clicked.connect(lambda: self._set_algo("aco"))
        self._btn_algo_dijkstra.clicked.connect(lambda: self._set_algo("dijkstra"))
        v.addWidget(gb_algo)

        # === Пресеты ===
        gb_presets = QGroupBox("Пресеты")
        vp = QVBoxLayout(gb_presets)
        vp.setContentsMargins(10, 14, 10, 10)
        vp.setSpacing(6)

        preset_note = QLabel("Готовые наборы параметров:")
        preset_note.setStyleSheet("color:#6c7086; font-size:8pt;")
        vp.addWidget(preset_note)

        row_pre = QHBoxLayout()
        row_pre.setSpacing(4)

        btn_fast = QPushButton("Быстро")
        btn_fast.setFixedHeight(28)
        btn_fast.setToolTip(
            "15 муравьёв, 30 итераций\nБыстрый результат для проверки топологии"
        )
        btn_fast.clicked.connect(lambda: self._apply_preset("fast"))

        btn_balanced = QPushButton("Стандарт")
        btn_balanced.setFixedHeight(28)
        btn_balanced.setToolTip(
            "30 муравьёв, 100 итераций\nСбалансированный режим (по умолчанию)"
        )
        btn_balanced.clicked.connect(lambda: self._apply_preset("balanced"))

        btn_precise = QPushButton("Точно")
        btn_precise.setFixedHeight(28)
        btn_precise.setToolTip(
            "60 муравьёв, 250 итераций\nВысокое качество: сильнее объединение проводов,\n"
            "медленное испарение, агрессивная эвристика"
        )
        btn_precise.clicked.connect(lambda: self._apply_preset("precise"))

        row_pre.addWidget(btn_fast)
        row_pre.addWidget(btn_balanced)
        row_pre.addWidget(btn_precise)
        vp.addLayout(row_pre)
        v.addWidget(gb_presets)

        # === Основные параметры ===
        gb = QGroupBox("Основные параметры")
        vg = QVBoxLayout(gb)
        vg.setSpacing(6)
        vg.setContentsMargins(10, 14, 10, 10)

        self._sp_ants = self._make_int_param_row(vg, "Муравьёв:", 5, 500, 30,
            info_text=(
                "<b>Количество муравьёв</b> на каждую итерацию.<br><br>"
                "Больше муравьёв — лучше исследуется пространство решений, "
                "меньше шанс застрять в локальном минимуме, но медленнее.<br><br>"
                "<b>Диапазон:</b> 5 – 500<br>"
                "<b>Для скорости:</b> 10 – 20<br>"
                "<b>Стандарт:</b> 30<br>"
                "<b>Для точности:</b> 50 – 100"
            ))
        self._sp_iters = self._make_int_param_row(vg, "Итераций:", 10, 1000, 100,
            info_text=(
                "<b>Количество итераций</b> алгоритма.<br><br>"
                "Больше итераций — феромонный след точнее отражает лучший маршрут. "
                "При малом числе итераций алгоритм может не сойтись.<br><br>"
                "<b>Диапазон:</b> 10 – 1000<br>"
                "<b>Для скорости:</b> 20 – 50<br>"
                "<b>Стандарт:</b> 100<br>"
                "<b>Для точности:</b> 200 – 300"
            ))
        self._sp_rho = self._make_float_param_row(vg, "ρ испарение:", 1, 99, 15, scale=100,
            info_text=(
                "<b>Скорость испарения феромона</b> за одну итерацию (0 – 1).<br><br>"
                "Высокое ρ → феромон быстро исчезает, алгоритм активнее ищет новые пути "
                "(быстрее, но менее стабильно).<br>"
                "Низкое ρ → алгоритм дольше помнит найденные маршруты "
                "(медленнее, но точнее).<br><br>"
                "<b>Диапазон:</b> 0.01 – 0.99<br>"
                "<b>Для скорости:</b> 0.30 – 0.50<br>"
                "<b>Стандарт:</b> 0.15<br>"
                "<b>Для точности:</b> 0.05 – 0.10"
            ))
        self._sp_bundle = self._make_float_param_row(vg, "Жгут-бонус:", 0, 100, 15, scale=10,
            info_text=(
                "<b>Коэффициент поощрения совместной прокладки проводов.</b><br><br>"
                "Чем выше — тем активнее алгоритм укладывает провода рядом "
                "в один жгут. При значении 1.0 бонус не применяется.<br><br>"
                "<b>Диапазон:</b> 0.0 – 10.0<br>"
                "<b>Только длина:</b> 1.0 – 2.0<br>"
                "<b>Стандарт:</b> 1.5<br>"
                "<b>Жгутовая трассировка:</b> 3.0 – 5.0"
            ))

        v.addWidget(gb)

        # === Баланс критериев ===
        gb_bal = QGroupBox("Баланс критериев")
        vbal = QVBoxLayout(gb_bal)
        vbal.setContentsMargins(10, 14, 10, 10)

        row_lbl = QHBoxLayout()
        row_lbl.addWidget(QLabel("Только длина"))
        row_lbl.addStretch()
        row_lbl.addWidget(QLabel("Только ЭМС"))
        vbal.addLayout(row_lbl)

        self._sld_balance = QSlider(Qt.Horizontal)
        self._sld_balance.setRange(0, 100)
        self._sld_balance.setValue(0)
        vbal.addWidget(self._sld_balance)

        self._lbl_lambda = QLabel("λ₁ = 10.0    λ₂ = 0.0")
        self._lbl_lambda.setAlignment(Qt.AlignCenter)
        pass  # стиль ставится в _refresh_inline_styles
        vbal.addWidget(self._lbl_lambda)
        self._sld_balance.valueChanged.connect(self._on_balance_changed)

        v.addWidget(gb_bal)

        # === Расширенные параметры ===
        btn_adv = QPushButton("▸  Расширенные параметры")
        btn_adv.setCheckable(True)
        btn_adv.setChecked(False)
        btn_adv.setStyleSheet(
            "QPushButton { text-align:left; color:#585b70; font-size:8.5pt;"
            "background:transparent; border:none; border-top:1px solid #2a2a3d;"
            "padding:6px 0; min-width:0; }"
            "QPushButton:hover { color:#89b4fa; }"
            "QPushButton:checked { color:#89b4fa; }"
        )
        v.addWidget(btn_adv)

        frame_adv = QFrame()
        frame_adv.setVisible(False)
        adv_layout = QVBoxLayout(frame_adv)
        adv_layout.setContentsMargins(0, 0, 0, 4)
        adv_layout.setSpacing(6)

        self._sp_alpha = self._make_float_param_row(adv_layout, "α феромон:", 1, 100, 10, scale=10,
            info_text=(
                "<b>Влияние феромонного следа</b> на выбор ребра (α).<br><br>"
                "Высокое α → алгоритм активнее следует накопленному опыту, "
                "меньше случайности в выборе пути.<br>"
                "Низкое α → больше случайного поиска.<br><br>"
                "<b>Диапазон:</b> 0.1 – 10.0<br>"
                "<b>Рекомендуется:</b> 1.0 – 2.0"
            ))
        self._sp_beta = self._make_float_param_row(adv_layout, "β эвристика:", 1, 100, 25, scale=10,
            info_text=(
                "<b>Влияние длины ребра</b> (эвристики) на выбор пути (β).<br><br>"
                "Высокое β → алгоритм предпочитает короткие рёбра, "
                "маршруты получаются компактнее.<br>"
                "Низкое β → длина ребра почти не влияет на выбор.<br><br>"
                "<b>Диапазон:</b> 0.1 – 10.0<br>"
                "<b>Для коротких маршрутов:</b> 3.0 – 5.0<br>"
                "<b>Рекомендуется:</b> 2.5"
            ))

        v.addWidget(frame_adv)

        def _toggle_adv(checked):
            btn_adv.setText(("▾" if checked else "▸") + "  Расширенные параметры")
            frame_adv.setVisible(checked)

        btn_adv.toggled.connect(_toggle_adv)

        # === Ручная трассировка ===
        gb_manual = QGroupBox("Ручная трассировка")
        vg_m = QVBoxLayout(gb_manual)
        vg_m.setSpacing(6)
        vg_m.setContentsMargins(10, 14, 10, 10)

        note_m = QLabel("Выберите пару на вкладке «Соединения», затем нажмите кнопку.\n"
                         "Кликайте по соседним узлам в 3D-виде.")
        note_m.setStyleSheet("color:#6c7086; font-size:8pt;")
        note_m.setWordWrap(True)
        vg_m.addWidget(note_m)

        self._btn_manual_start = QPushButton("▶  Трассировать вручную")
        self._btn_manual_start.setEnabled(False)
        self._btn_manual_start.clicked.connect(self._start_manual_route)
        vg_m.addWidget(self._btn_manual_start)

        row_manual = QHBoxLayout()
        self._btn_manual_undo = QPushButton("← Шаг назад")
        self._btn_manual_undo.setEnabled(False)
        self._btn_manual_undo.clicked.connect(self._undo_manual_step)
        row_manual.addWidget(self._btn_manual_undo)

        self._btn_manual_cancel = QPushButton("✕ Отменить")
        self._btn_manual_cancel.setObjectName("dangerBtn")
        self._btn_manual_cancel.setEnabled(False)
        self._btn_manual_cancel.clicked.connect(self._cancel_manual_route)
        row_manual.addWidget(self._btn_manual_cancel)
        vg_m.addLayout(row_manual)

        self._lbl_manual_status = QLabel("")
        self._lbl_manual_status.setWordWrap(True)
        vg_m.addWidget(self._lbl_manual_status)

        v.addWidget(gb_manual)
        v.addStretch()
        return w

    # создаёт строку с подписью, слайдером и spinbox синхронизированными между собой
    def _make_int_param_row(self, layout, label: str, lo: int, hi: int, init: int,
                            info_text: str = "") -> QSpinBox:
        sp = QSpinBox()
        sp.setRange(lo, hi)
        sp.setValue(init)
        sp.setFixedWidth(68)

        sld = QSlider(Qt.Horizontal)
        sld.setRange(lo, hi)
        sld.setValue(init)

        def sld_to_sp(val):
            sp.blockSignals(True); sp.setValue(val); sp.blockSignals(False)

        def sp_to_sld(val):
            sld.blockSignals(True); sld.setValue(val); sld.blockSignals(False)

        sld.valueChanged.connect(sld_to_sp)
        sp.valueChanged.connect(sp_to_sld)

        lbl = QLabel(label)
        lbl.setFixedWidth(88)
        row = QHBoxLayout()
        row.addWidget(lbl)
        row.addWidget(sld)
        row.addWidget(sp)
        if info_text:
            row.addWidget(self._make_info_btn(info_text))
        layout.addLayout(row)
        return sp

    # то же что make_int_param_row, но для вещественных параметров
    # значение spinbox = значение слайдера / scale
    def _make_float_param_row(self, layout, label: str,
                              sld_lo: int, sld_hi: int, sld_init: int,
                              scale: int = 100, info_text: str = "") -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(sld_lo / scale, sld_hi / scale)
        sp.setDecimals(2 if scale >= 100 else 1)
        sp.setSingleStep(1.0 / scale)
        sp.setValue(sld_init / scale)
        sp.setFixedWidth(68)

        sld = QSlider(Qt.Horizontal)
        sld.setRange(sld_lo, sld_hi)
        sld.setValue(sld_init)

        def sld_to_sp(val):
            sp.blockSignals(True); sp.setValue(val / scale); sp.blockSignals(False)

        def sp_to_sld(val):
            sld.blockSignals(True); sld.setValue(round(val * scale)); sld.blockSignals(False)

        sld.valueChanged.connect(sld_to_sp)
        sp.valueChanged.connect(sp_to_sld)

        lbl = QLabel(label)
        lbl.setFixedWidth(88)
        row = QHBoxLayout()
        row.addWidget(lbl)
        row.addWidget(sld)
        row.addWidget(sp)
        if info_text:
            row.addWidget(self._make_info_btn(info_text))
        layout.addLayout(row)
        return sp

    def _on_balance_changed(self, val: int):
        l1 = (100 - val) / 10.0
        l2 = val / 10.0
        self._lbl_lambda.setText(f"λ₁ = {l1:.1f}    λ₂ = {l2:.1f}")

    _PRESETS = {
        # n_ants, n_iters, rho, bundle_bonus, alpha, beta
        "fast":     (15,  30,  0.25, 1.5, 1.0, 2.5),
        "balanced": (30,  100, 0.15, 1.5, 1.0, 2.5),
        "precise":  (60,  250, 0.08, 2.5, 1.0, 3.0),
    }

    # применяет готовый набор параметров алгоритма (быстро/стандарт/точно)
    def _apply_preset(self, preset: str):
        if preset not in self._PRESETS:
            return
        ants, iters, rho, bundle, alpha, beta = self._PRESETS[preset]
        self._sp_ants.setValue(ants)
        self._sp_iters.setValue(iters)
        self._sp_rho.setValue(rho)
        self._sp_bundle.setValue(bundle)
        self._sp_alpha.setValue(alpha)
        self._sp_beta.setValue(beta)
        names = {"fast": "Быстро", "balanced": "Стандарт", "precise": "Точно"}
        self._toast(f"Пресет «{names[preset]}» применён", "info", 2000)

    # переключает алгоритм трассировки и блокирует чекбокс резерва если выбрана дейкстра
    def _set_algo(self, mode: str):
        self._algo_mode = mode
        if hasattr(self, "_chk_fallback"):
            self._chk_fallback.setEnabled(mode == "aco")

    # --- Правый dock «Результаты» --------------------------------------
    def _build_results_dock(self):
        dock = QDockWidget("Результаты трассировки", self)
        dock.setFeatures(
            QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable
        )
        dock.setAllowedAreas(Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea)

        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(8)
        v.setContentsMargins(8, 8, 8, 8)

        gb = QGroupBox("Найденные маршруты")
        vg = QVBoxLayout(gb)
        self._lst_routes = QListWidget()
        self._lst_routes.setMinimumHeight(180)
        vg.addWidget(self._lst_routes)
        v.addWidget(gb)

        self._metrics_frame = QFrame()
        metrics_frame = self._metrics_frame
        mg = QGridLayout(metrics_frame)
        mg.setContentsMargins(10, 8, 10, 8)
        mg.setSpacing(5)
        mg.setColumnStretch(0, 1)

        def _key_lbl(text):
            l = QLabel(text)
            l.setStyleSheet("color:#6c7086; font-size:8pt;")
            return l

        def _val_lbl():
            l = QLabel("—")
            l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            l.setStyleSheet("color:#a6e3a1; font-weight:600; font-size:9pt;")
            return l

        mg.addWidget(_key_lbl("Суммарная длина:"), 0, 0)
        self._lbl_f1_val = _val_lbl()
        mg.addWidget(self._lbl_f1_val, 0, 1)

        mg.addWidget(_key_lbl("ЭМС-конфликты:"), 1, 0)
        self._lbl_f2_val = _val_lbl()
        mg.addWidget(self._lbl_f2_val, 1, 1)

        mg.addWidget(_key_lbl("Целевая функция:"), 2, 0)
        self._lbl_obj_val = _val_lbl()
        mg.addWidget(self._lbl_obj_val, 2, 1)

        v.addWidget(metrics_frame)

        self._btn_verify = QPushButton("Верификация маршрутов…")
        self._btn_verify.setToolTip(
            "Проверить: неразрывность пути и отсутствие коллизий с деталями"
        )
        self._btn_verify.clicked.connect(self._run_verify)
        v.addWidget(self._btn_verify)

        btn_export = QPushButton("Экспорт маршрутов в DXF…")
        btn_export.setObjectName("runBtn")
        btn_export.clicked.connect(self._export_dxf)
        v.addWidget(btn_export)

        btn_clear = QPushButton("Сбросить маршруты")
        btn_clear.setObjectName("dangerBtn")
        btn_clear.clicked.connect(self._clear_routes)
        v.addWidget(btn_clear)

        v.addStretch()
        dock.setWidget(w)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        dock.setMinimumWidth(260)

        # Показать/скрыть из меню View
        self._results_dock = dock

    # управление режимами

    # переключает активный режим и устанавливает соответствующие обработчики событий
    def _set_mode(self, mode: str):
        if mode != self._mode:
            self._cancel_pending()
        self._mode = mode

        self._remove_click_filter()
        try:
            self.plotter.disable_picking()
        except Exception:
            pass

        if mode == MODE_ADD_NODE:
            self.plotter.enable_surface_point_picking(
                callback=self._on_pick,
                left_clicking=True,
                show_message=False,
                show_point=False,
                pickable_window=True,
            )
        elif mode in (MODE_ADD_EDGE, MODE_ADD_PAIR, MODE_MANUAL_ROUTE):
            self._add_node_select_observers()
        elif mode == MODE_NAVIGATE and self._parts_data:
            self._add_navigate_observers()
        elif mode == MODE_GRID_EDIT and self._grid_edge_pairs:
            self._add_grid_observers()
        elif mode == MODE_DRAW_CHANNEL:
            self._add_polyline_observers()
            self._btn_polyline_cancel.setEnabled(True)

        self._set_status(_HINTS.get(mode, ""))
        self._apply_mode_style(mode)

    # цвет рамки вокруг 3d-вида и курсор для каждого режима
    _MODE_BORDER = {
        MODE_NAVIGATE:     ("",        Qt.ArrowCursor),
        MODE_ADD_NODE:     ("#89b4fa", Qt.CrossCursor),
        MODE_ADD_EDGE:     ("#a6e3a1", Qt.CrossCursor),
        MODE_ADD_PAIR:     ("#f9e2af", Qt.CrossCursor),
        MODE_GRID_EDIT:    ("#cba6f7", Qt.CrossCursor),
        MODE_MANUAL_ROUTE: ("#fab387", Qt.CrossCursor),
        MODE_DRAW_CHANNEL: ("#94e2d5", Qt.CrossCursor),
    }

    def _apply_mode_style(self, mode: str):
        color, cursor_shape = self._MODE_BORDER.get(mode, ("", Qt.ArrowCursor))
        if color:
            self._viewport_frame.setStyleSheet(
                f"#viewportFrame {{ border: 2px solid {color}; }}"
            )
        else:
            self._viewport_frame.setStyleSheet("")
        self.plotter.interactor.setCursor(QCursor(cursor_shape))

    # --- Контекстное меню в 3D-виде ------------------------------------

    def _show_viewport_context_menu(self, global_pos, vtk_x: int, vtk_y: int):
        from PyQt5.QtWidgets import QMenu
        nid = self._nearest_node_screen(vtk_x, vtk_y, threshold_px=30)

        menu = QMenu(self)

        if nid is not None:
            menu.addSection(f"Узел  {nid}")
            a_del = menu.addAction("Удалить узел")
            a_del.triggered.connect(lambda: self._ctx_delete_node(nid))

            a_src = menu.addAction("Добавить пару отсюда…")
            a_src.triggered.connect(lambda: self._ctx_start_pair(nid))

            menu.addSeparator()

        menu.addSection("Переключить режим")
        for label, mode in [
            ("Навигация",   MODE_NAVIGATE),
            ("Добавить узел",  MODE_ADD_NODE),
            ("Добавить ребро", MODE_ADD_EDGE),
            ("Добавить пару",  MODE_ADD_PAIR),
        ]:
            a = menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(self._mode == mode)
            a.triggered.connect(lambda checked, m=mode: self._set_mode(m))

        menu.exec_(global_pos)

    def _ctx_delete_node(self, nid: int):
        from core.graph import CableChannelGraph
        self._undo_stack.push(_RemoveNodeCmd(self, nid))
        self._update_edit_actions()

    def _ctx_start_pair(self, nid: int):
        self._set_mode(MODE_ADD_PAIR)
        self._do_add_pair_by_node(nid)

    # --- Qt event-filter для клика по деталям в режиме навигации ------

    def _add_navigate_observers(self):
        from vtkmodules.vtkRenderingCore import vtkCellPicker
        self._part_picker = vtkCellPicker()
        self._part_picker.SetTolerance(0.002)

        def do_pick(vtk_x, vtk_y):
            self._part_picker.Pick(vtk_x, vtk_y, 0, self.plotter.renderer)
            self._on_pick_actor(self._part_picker.GetActor())

        def do_hover(vtk_x, vtk_y):
            widget = self.plotter.interactor
            nid = self._nearest_node_screen(vtk_x, vtk_y, threshold_px=25)
            if nid is not None and nid in self._graph.nodes:
                pos = self._graph.nodes[nid]["pos"]
                tip = (
                    f"Узел {nid}\n"
                    f"X: {pos[0]:.1f}   Y: {pos[1]:.1f}   Z: {pos[2]:.1f}"
                )
                qt_y = widget.height() - vtk_y - 1
                global_pt = widget.mapToGlobal(QPoint(vtk_x, qt_y))
                QToolTip.showText(global_pt, tip, widget)
            else:
                QToolTip.hideText()

        self._pick_filter = _PartClickFilter(
            self.plotter.interactor, do_pick, hover_cb=do_hover
        )
        self.plotter.interactor.installEventFilter(self._pick_filter)

    # устанавливает фильтр кликов по узлам для режимов ребро/пара/ручная трассировка
    def _add_node_select_observers(self):
        def do_pick(vtk_x, vtk_y):
            nid = self._nearest_node_screen(vtk_x, vtk_y)
            if self._mode == MODE_ADD_EDGE:
                self._do_add_edge_by_node(nid)
            elif self._mode == MODE_ADD_PAIR:
                self._do_add_pair_by_node(nid)
            elif self._mode == MODE_MANUAL_ROUTE:
                self._step_manual_route(nid)

        self._pick_filter = _PartClickFilter(self.plotter.interactor, do_pick)
        self.plotter.interactor.installEventFilter(self._pick_filter)

    def _add_grid_observers(self):
        def do_click(vtk_x, vtk_y):
            idx = self._grid_nearest_edge_screen(vtk_x, vtk_y)
            if idx is not None:
                self._toggle_grid_edge(idx)

        def do_hover(vtk_x, vtk_y):
            idx = self._grid_nearest_edge_screen(vtk_x, vtk_y)
            self._update_grid_hover(idx)

        self._pick_filter = _PartClickFilter(
            self.plotter.interactor, do_click, hover_cb=do_hover
        )
        self.plotter.interactor.installEventFilter(self._pick_filter)

    # рисование трасс полилиниями (режим draw_channel)

    def _add_polyline_observers(self):
        from vtkmodules.vtkRenderingCore import vtkCellPicker
        self._polyline_click_picker = vtkCellPicker()
        self._polyline_click_picker.SetTolerance(0.002)
        self._polyline_hover_picker = vtkCellPicker()
        self._polyline_hover_picker.SetTolerance(0.002)

        self._pick_filter = _PolylineEventFilter(
            self.plotter.interactor,
            click_cb    = self._on_polyline_pick_coords,
            hover_cb    = self._update_polyline_preview,
            dblclick_cb = self._finalize_polyline,
        )
        self.plotter.interactor.installEventFilter(self._pick_filter)

    # определяет 3d-точку под курсором с помощью vtk-пикера и добавляет в полилинию
    def _on_polyline_pick_coords(self, vtk_x: int, vtk_y: int):
        self._polyline_click_picker.Pick(vtk_x, vtk_y, 0, self.plotter.renderer)
        if self._polyline_click_picker.GetCellId() >= 0:
            pos = tuple(self._polyline_click_picker.GetPickPosition())
        else:
            # Запасной вариант: привязка к ближайшему существующему узлу
            nid = self._nearest_node_screen(vtk_x, vtk_y, threshold_px=25)
            if nid is None:
                self._set_status("Кликните на поверхность модели или существующий узел.")
                return
            pos = tuple(self._graph.nodes[nid]["pos"])

        self._add_polyline_point(pos)

    def _add_polyline_point(self, pos):
        pos = tuple(float(c) for c in pos)

        # Рисуем сегмент от предыдущей точки
        if self._polyline_pts:
            p0 = np.array(self._polyline_pts[-1])
            p1 = np.array(pos)
            if np.linalg.norm(p1 - p0) > 1e-6:
                tube = pv.Line(p0, p1).tube(radius=self._tube_r * 0.5, n_sides=8)
                a = self.plotter.add_mesh(
                    tube, color="#94e2d5", smooth_shading=True,
                    reset_camera=False, pickable=False,
                )
                self._polyline_seg_actors.append(a)

        # Сфера в точке
        sph = self.plotter.add_mesh(
            pv.Sphere(radius=self._sphere_r * 1.05, center=pos),
            color="#94e2d5", smooth_shading=True,
            reset_camera=False, pickable=False,
        )
        self._polyline_node_actors.append(sph)
        self._polyline_pts.append(pos)
        self.plotter.render()
        self._update_polyline_ui()

    # показывает пунктирную превью-линию от последней точки до текущей позиции курсора
    def _update_polyline_preview(self, vtk_x: int, vtk_y: int):
        if not self._polyline_pts:
            return
        self._polyline_hover_picker.Pick(vtk_x, vtk_y, 0, self.plotter.renderer)
        if self._polyline_hover_picker.GetCellId() < 0:
            # Попробуем snap к узлу
            nid = self._nearest_node_screen(vtk_x, vtk_y, threshold_px=25)
            if nid is None:
                self._clear_polyline_preview()
                return
            cur_pos = np.array(self._graph.nodes[nid]["pos"])
        else:
            cur_pos = np.array(self._polyline_hover_picker.GetPickPosition())

        p0 = np.array(self._polyline_pts[-1])
        if np.linalg.norm(cur_pos - p0) < 1e-6:
            return

        self._clear_polyline_preview()
        tube = pv.Line(p0, cur_pos).tube(radius=self._tube_r * 0.28, n_sides=6)
        self._polyline_preview_actor = self.plotter.add_mesh(
            tube, color="#94e2d5", opacity=0.40, smooth_shading=True,
            reset_camera=False, pickable=False,
        )
        self.plotter.render()

    def _clear_polyline_preview(self):
        if self._polyline_preview_actor is not None:
            self.plotter.remove_actor(self._polyline_preview_actor)
            self._polyline_preview_actor = None

    def _polyline_undo_last(self):
        if not self._polyline_pts:
            return
        self._polyline_pts.pop()
        if self._polyline_node_actors:
            self.plotter.remove_actor(self._polyline_node_actors.pop())
        if self._polyline_seg_actors:
            self.plotter.remove_actor(self._polyline_seg_actors.pop())
        self.plotter.render()
        self._update_polyline_ui()

    def _finalize_polyline(self):
        pts = list(self._polyline_pts)
        if len(pts) < 2:
            self._set_status("Нужно минимум 2 точки для трассы.")
            return

        self._clear_polyline_actors()
        self._polyline_pts = []
        self._undo_stack.push(_AddPolylineCmd(self, pts))
        self._update_edit_actions()
        self._update_polyline_ui()
        # Остаёмся в режиме — можно сразу рисовать следующую трассу

    def _cancel_polyline(self):
        self._clear_polyline_actors()
        self._polyline_pts = []
        self._update_polyline_ui()
        self._set_mode(MODE_NAVIGATE)

    def _clear_polyline_actors(self):
        self._clear_polyline_preview()
        for a in self._polyline_seg_actors:
            self.plotter.remove_actor(a)
        self._polyline_seg_actors = []
        for a in self._polyline_node_actors:
            self.plotter.remove_actor(a)
        self._polyline_node_actors = []
        self.plotter.render()

    def _update_polyline_ui(self):
        n = len(self._polyline_pts)
        if n == 0:
            self._lbl_polyline_status.setVisible(False)
            self._lbl_polyline_status.setText("")
        else:
            length = sum(
                float(np.linalg.norm(
                    np.array(self._polyline_pts[i + 1]) - np.array(self._polyline_pts[i])
                ))
                for i in range(n - 1)
            )
            self._lbl_polyline_status.setText(f"Точек: {n}   Длина: {length:.1f} мм")
            self._lbl_polyline_status.setVisible(True)
        self._btn_polyline_undo.setEnabled(n > 0)
        self._btn_polyline_ok.setEnabled(n >= 2)
        self._btn_polyline_cancel.setEnabled(self._mode == MODE_DRAW_CHANNEL)

    def _polyline_finish_if_active(self):
        if self._mode == MODE_DRAW_CHANNEL:
            self._finalize_polyline()

    def _polyline_cancel_if_active(self):
        if self._mode == MODE_DRAW_CHANNEL:
            self._cancel_polyline()

    def _remove_click_filter(self):
        if hasattr(self, "_pick_filter"):
            if hasattr(self._pick_filter, "cleanup"):
                self._pick_filter.cleanup()
            self.plotter.interactor.removeEventFilter(self._pick_filter)
            del self._pick_filter
        self._clear_grid_hover()
        # Убираем превью полилинии при выходе из режима
        self._clear_polyline_preview()

    def _cancel_pending(self):
        self._edge_first = None
        self._pair_first = None
        if self._highlight_actor is not None:
            self.plotter.remove_actor(self._highlight_actor)
            self._highlight_actor = None
        # Сбросить ручную трассировку без UI-очистки (только акторы)
        if self._manual_path:
            self._clear_manual_actors()
            self._manual_pair = None
            self._manual_path = []
            self._btn_manual_undo.setEnabled(False)
            self._btn_manual_cancel.setEnabled(False)
            row = self._lst_pairs.currentRow()
            self._btn_manual_start.setEnabled(0 <= row < len(self._pairs))
        # Сбросить рисование полилинии
        if self._polyline_pts:
            self._clear_polyline_actors()
            self._polyline_pts = []
            self._update_polyline_ui()

    # обработка кликов в 3d-виде

    def _on_pick(self, point):
        if point is None:
            return
        if self._mode == MODE_ADD_NODE:
            self._do_add_node(point)

    # находит ближайший узел графа к экранным координатам клика
    # проекция из мировых координат в пиксели через vtk-матрицу камеры
    def _nearest_node_screen(self, vtk_x: int, vtk_y: int, threshold_px: int = 20) -> Optional[int]:
        from vtkmodules.vtkRenderingCore import vtkCoordinate
        renderer = self.plotter.renderer
        coord = vtkCoordinate()
        coord.SetCoordinateSystemToWorld()

        best_id = None
        best_d2 = threshold_px ** 2

        for nid, data in self._graph.nodes(data=True):
            x, y, z = data["pos"]
            coord.SetValue(float(x), float(y), float(z))
            sx, sy = coord.GetComputedDisplayValue(renderer)
            dx = vtk_x - int(sx)
            dy = vtk_y - int(sy)   # оба в VTK-координатах (Y снизу)
            d2 = dx * dx + dy * dy
            if d2 < best_d2:
                best_d2 = d2
                best_id = nid

        return best_id

    def _on_pick_actor(self, actor):
        if actor is None:
            return
        # vtkCellPicker возвращает vtkActor из VTK-движка; PyVista-обёртка хранит
        # тот же mapper, поэтому сравниваем через GetMapper(), а не через `is`.
        picked_mapper = actor.GetMapper()

        # Клик по маршрутной трубке → выделить строку в «Результатах»
        if picked_mapper in self._route_actor_map:
            row = self._route_actor_map[picked_mapper]
            self._tabs.setCurrentIndex(5)   # вкладка «Результаты»
            self._lst_routes.setCurrentRow(row)
            self._set_status(
                f"Маршрут: {self._routes[row].pair.label}   "
                f"L={self._routes[row].length:.1f} мм"
            )
            return

        # Клик по детали модели → подсветить деталь
        for i, part in enumerate(self._parts_data):
            if part["actor"].GetMapper() is picked_mapper:
                self._lst_parts.blockSignals(True)
                self._lst_parts.setCurrentRow(i)
                self._lst_parts.blockSignals(False)
                self._on_part_selected(i)
                self._tabs.setCurrentIndex(0)
                break

    # операции добавления/редактирования элементов графа

    def _do_add_node(self, point):
        self._undo_stack.push(_AddNodeCmd(self, point))
        self._update_edit_actions()

    def _do_add_edge_by_node(self, nid: Optional[int]):
        if nid is None:
            self._set_status("Нет узла рядом с кликом — кликните ближе к зелёной сфере.")
            return

        if self._edge_first is None:
            self._edge_first = nid
            self._highlight_actor = self.plotter.add_mesh(
                pv.Sphere(radius=self._sphere_r * 1.9,
                          center=self._graph.nodes[nid]["pos"]),
                color="yellow", smooth_shading=True, opacity=0.6,
                reset_camera=False,
            )
            self._set_status(f"Узел {nid} выбран — кликните второй узел.")
        else:
            u, v = self._edge_first, nid
            self._remove_highlight()
            self._edge_first = None
            if u == v:
                self._set_status("Нельзя соединить узел с самим собой.")
                return
            g = self._graph.networkx_graph()
            if not (g.has_node(u) and g.has_node(v)):
                self._set_status(f"Узел {u} или {v} был удалён — начните заново.")
                return
            if self._graph.has_edge(u, v):
                self._set_status(f"Ребро {u}—{v} уже существует.")
                return
            self._undo_stack.push(_AddEdgeCmd(self, u, v))
            self._update_edit_actions()

    def _do_add_pair_by_node(self, nid: Optional[int]):
        if nid is None:
            self._set_status("Нет узла рядом — кликни ближе к зелёной сфере.")
            return

        if self._pair_first is None:
            self._pair_first = nid
            self._highlight_actor = self.plotter.add_mesh(
                pv.Sphere(radius=self._sphere_r * 1.9,
                          center=self._graph.nodes[nid]["pos"]),
                color="#ff8800", smooth_shading=True, opacity=0.7,
                reset_camera=False,
            )
            self._set_status(f"Узел {nid} выбран как источник — выбери второй узел соединения")
        else:
            if nid == self._pair_first:
                self._remove_highlight()
                self._pair_first = None
                self._set_status("Выбор отменён — выбери первый узел соединения")
                return
            src, tgt = self._pair_first, nid
            self._remove_highlight()
            self._pair_first = None
            g = self._graph.networkx_graph()
            if not (g.has_node(src) and g.has_node(tgt)):
                self._set_status(f"Узел {src} или {tgt} был удалён — начните заново.")
                return
            label = f"Проводник {len(self._pairs) + 1}"
            self._pairs.append(ConnectionPair(source=src, target=tgt, label=label))
            for node_id, color in [(src, "#ff3333"), (tgt, "#ff8800")]:
                pos = self._graph.nodes[node_id]["pos"]
                a = self.plotter.add_mesh(
                    pv.Sphere(radius=self._sphere_r * 1.35, center=pos),
                    color=color, smooth_shading=True, opacity=0.75,
                )
                self._pair_actors.append(a)
            self._refresh_pairs_list()
            self._set_status(f"{label} создан: {src} → {tgt}   |   выбери первый узел соединения")

    # ручная трассировка — пользователь кликает по соседним узлам шаг за шагом

    def _start_manual_route(self):
        row = self._lst_pairs.currentRow()
        if not (0 <= row < len(self._pairs)):
            return
        if not self._graph.nodes:
            self._set_status("Граф пуст — добавьте узлы.")
            return

        self._manual_pair = self._pairs[row]
        src = self._manual_pair.source
        if src not in self._graph.nodes:
            self._set_status(f"Узел-источник {src} отсутствует в графе.")
            return

        self._manual_path = [src]
        self._btn_manual_start.setEnabled(False)
        self._btn_manual_undo.setEnabled(False)
        self._btn_manual_cancel.setEnabled(True)
        self._set_mode(MODE_MANUAL_ROUTE)
        self._update_manual_visual()
        self._update_manual_status()

    def _step_manual_route(self, nid: Optional[int]):
        if nid is None:
            self._set_status("Кликни ближе к соседнему узлу (зелёная сфера).")
            return
        if not self._manual_path or self._manual_pair is None:
            return

        cur = self._manual_path[-1]
        tgt = self._manual_pair.target

        if nid == cur:
            return  # клик по текущей позиции

        if not self._graph.has_edge(cur, nid):
            self._set_status(
                f"Узел {nid} не соединён с текущей позицией {cur} — "
                "выбери соседний узел (зелёная сфера)."
            )
            return

        if nid in self._manual_path and nid != tgt:
            self._set_status(f"Узел {nid} уже в пути — выбери другой.")
            return

        self._manual_path.append(nid)
        self._btn_manual_undo.setEnabled(True)
        self._update_manual_visual()
        self._update_manual_status()

        if nid == tgt:
            self._finalize_manual_route()

    def _undo_manual_step(self):
        if len(self._manual_path) <= 1:
            return
        self._manual_path.pop()
        self._btn_manual_undo.setEnabled(len(self._manual_path) > 1)
        self._update_manual_visual()
        self._update_manual_status()

    def _finalize_manual_route(self):
        path = self._manual_path
        g    = self._graph.networkx_graph()
        positions = [self._graph.nodes[n]["pos"] for n in path]
        length = sum(
            g[path[k]][path[k + 1]].get("weight", 0.0)
            for k in range(len(path) - 1)
        )
        color = ROUTE_COLORS[len(self._routes) % len(ROUTE_COLORS)]
        route = Route(
            pair=self._manual_pair,
            path=list(path),
            positions=positions,
            length=length,
            color=color,
        )
        # Помечаем маршрут как ручной через label-суффикс
        route.pair = ConnectionPair(
            source=self._manual_pair.source,
            target=self._manual_pair.target,
            label=f"{self._manual_pair.label} [Ручной]",
            cable_class=self._manual_pair.cable_class,
        )
        self._routes.append(route)

        # Рисуем финальный маршрут (те же акторы, что и у ACO)
        self._draw_route_actor(route, len(self._routes) - 1)

        f1 = sum(r.length for r in self._routes)
        f2 = self._compute_f2(self._routes)
        self._refresh_routes_list(f1, f2)

        self._lbl_manual_status.setText(
            f"Готово!  L = {length:.1f} мм  |  {len(path)} узлов"
        )
        self._lbl_manual_status.setStyleSheet(
            f"color:{self._color('success')}; font-size:8pt; padding:2px; font-weight:600;"
        )
        self._set_status(
            f"Ручной маршрут добавлен: {route.pair.label}  |  "
            f"L={length:.1f} мм  |  {len(path)} узлов"
        )
        self._clear_manual_actors()
        self._manual_pair = None
        self._manual_path = []
        self._btn_manual_undo.setEnabled(False)
        self._btn_manual_cancel.setEnabled(False)
        self._set_mode(MODE_NAVIGATE)
        row = self._lst_pairs.currentRow()
        self._btn_manual_start.setEnabled(0 <= row < len(self._pairs))

    def _cancel_manual_route(self):
        self._clear_manual_actors()
        self._manual_pair = None
        self._manual_path = []
        self._btn_manual_undo.setEnabled(False)
        self._btn_manual_cancel.setEnabled(False)
        self._lbl_manual_status.setText("—")
        self._lbl_manual_status.setStyleSheet("color:#6c7086; font-size:8pt; padding:2px;")
        row = self._lst_pairs.currentRow()
        self._btn_manual_start.setEnabled(0 <= row < len(self._pairs))
        self._set_mode(MODE_NAVIGATE)
        self._set_status("Ручная трассировка отменена.")

    # перерисовывает визуализацию ручной трассировки: путь, текущую позицию, соседей и цель
    def _update_manual_visual(self):
        self._clear_manual_actors()
        if not self._manual_path:
            return

        pts  = np.array(self._manual_nodes_pos(), dtype=float)
        tgt  = self._manual_pair.target
        cur  = self._manual_path[-1]

        # Текущий путь как сплайн-трубка
        if len(pts) >= 2:
            spline = pv.Spline(pts, n_points=max(len(pts) * 6, 30))
            tube = spline.tube(radius=self._tube_r * 0.85, n_sides=10)
            self._manual_preview_actor = self.plotter.add_mesh(
                tube, color="#fab387", smooth_shading=True,
                pickable=False, reset_camera=False,
            )

        # Текущая позиция — оранжевая сфера
        cur_pos = self._graph.nodes[cur]["pos"]
        self._manual_cur_actor = self.plotter.add_mesh(
            pv.Sphere(radius=self._sphere_r * 1.6, center=cur_pos),
            color="#fab387", smooth_shading=True,
            opacity=0.9, pickable=False, reset_camera=False,
        )

        # Цель — отдельная пульсирующая сфера (красная/белая)
        if tgt in self._graph.nodes and tgt != cur:
            tgt_pos = self._graph.nodes[tgt]["pos"]
            self._manual_tgt_actor = self.plotter.add_mesh(
                pv.Sphere(radius=self._sphere_r * 1.6, center=tgt_pos),
                color="#f38ba8", smooth_shading=True,
                opacity=0.85, pickable=False, reset_camera=False,
            )

        # Допустимые соседи — зелёные сферы
        visited = set(self._manual_path)
        for nb in self._graph.networkx_graph().neighbors(cur):
            if nb in visited and nb != tgt:
                continue
            pos = self._graph.nodes[nb]["pos"]
            a = self.plotter.add_mesh(
                pv.Sphere(radius=self._sphere_r * 1.2, center=pos),
                color="#a6e3a1", smooth_shading=True,
                opacity=0.75, pickable=False, reset_camera=False,
            )
            self._manual_nb_actors.append(a)

        self.plotter.render()

    def _manual_nodes_pos(self) -> list:
        return [self._graph.nodes[n]["pos"] for n in self._manual_path]

    def _update_manual_status(self):
        if not self._manual_pair or not self._manual_path:
            return
        cur = self._manual_path[-1]
        tgt = self._manual_pair.target
        n   = len(self._manual_path)
        g   = self._graph.networkx_graph()
        partial_len = sum(
            g[self._manual_path[k]][self._manual_path[k + 1]].get("weight", 0.0)
            for k in range(n - 1)
        )
        self._lbl_manual_status.setText(
            f"{self._manual_pair.label}:  {self._manual_pair.source} → {tgt}\n"
            f"Текущий узел: {cur}   Шагов: {n - 1}   L = {partial_len:.1f} мм"
        )
        self._lbl_manual_status.setStyleSheet(
            f"color:{self._color('warning')}; font-size:8pt; padding:2px;"
        )

    def _clear_manual_actors(self):
        for a in [self._manual_preview_actor,
                  self._manual_cur_actor,
                  self._manual_tgt_actor]:
            if a is not None:
                self.plotter.remove_actor(a)
        self._manual_preview_actor = None
        self._manual_cur_actor     = None
        self._manual_tgt_actor     = None
        for a in self._manual_nb_actors:
            self.plotter.remove_actor(a)
        self._manual_nb_actors.clear()

    # рисование объектов в 3d-сцене

    def _draw_edge_actor(self, u: int, v: int):
        p0  = np.array(self._graph.nodes[u]["pos"])
        p1  = np.array(self._graph.nodes[v]["pos"])
        key = (min(u, v), max(u, v))
        color = "#ff4444" if key in self._edge_collisions else "#4488ff"
        tube  = pv.Line(p0, p1).tube(radius=self._tube_r * 0.55, n_sides=8)
        actor = self.plotter.add_mesh(tube, color=color, smooth_shading=True, reset_camera=False)
        actor.SetVisibility(self._edges_visible)
        self._edge_actors[key] = actor

    def _toggle_edges_visibility(self, visible: bool):
        self._edges_visible = visible
        for actor in self._edge_actors.values():
            actor.SetVisibility(visible)
        for actor in self._node_actors.values():
            actor.SetVisibility(visible)
        self.plotter.render()

    def _draw_route_actor(self, route, route_idx: int):
        if len(route.positions) < 2:
            return
        pts = np.array(route.positions, dtype=float)
        spline = pv.Spline(pts, n_points=max(len(pts) * 6, 30))
        tube = spline.tube(radius=self._tube_r, n_sides=12)
        actor = self.plotter.add_mesh(
            tube, color=route.color, smooth_shading=True, pickable=True
        )
        self._route_actors.append(actor)
        self._route_actor_map[actor.GetMapper()] = route_idx

    # рисует голубые ореолы-жгуты на рёбрах с несколькими проводами
    # и красные маркеры там где нарушается эмс-совместимость
    def _draw_bundles_and_violations(self, routes):
        # ── Построить edge → [route_idx] ─────────────────────────────────
        edge_data: dict = {}
        for ri, route in enumerate(routes):
            for a, b in zip(route.path, route.path[1:]):
                key = (min(a, b), max(a, b))
                edge_data.setdefault(key, []).append(ri)

        # ── Предварительный проход: выявить ЭМС-нарушения по рёбрам ─────
        route_has_violation: list[bool] = [False] * len(routes)
        edge_has_violation: dict = {}
        for (u, v), idxs in edge_data.items():
            viol = False
            for i in range(len(idxs)):
                for j in range(i + 1, len(idxs)):
                    if emc_compatibility(routes[idxs[i]].pair.cable_class,
                                         routes[idxs[j]].pair.cable_class) < 0.5:
                        viol = True
                        route_has_violation[idxs[i]] = True
                        route_has_violation[idxs[j]] = True
            edge_has_violation[(u, v)] = viol

        # ── Отрисовка по рёбрам ──────────────────────────────────────────
        for (u, v), idxs in edge_data.items():
            count = len(idxs)
            p0 = np.array(self._graph.nodes[u]["pos"])
            p1 = np.array(self._graph.nodes[v]["pos"])
            if np.linalg.norm(p1 - p0) < 1e-9:
                continue

            # Жгут-индикатор: голубой ореол; толщина растёт с числом кабелей
            if count > 1:
                bundle_r = self._tube_r * (0.7 + count * 0.55)
                tube = pv.Line(p0, p1).tube(radius=bundle_r, n_sides=10)
                a = self.plotter.add_mesh(
                    tube, color="#4488ff", opacity=0.40,
                    smooth_shading=True, pickable=False
                )
                self._bundle_actors.append(a)

            # ЭМС-нарушение на ребре: красный маркер
            if edge_has_violation.get((u, v), False):
                emc_r = self._tube_r * (0.75 + count * 0.55)
                tube = pv.Line(p0, p1).tube(radius=emc_r, n_sides=10)
                a = self.plotter.add_mesh(
                    tube, color="#ff2244", opacity=0.45,
                    smooth_shading=True, pickable=False
                )
                self._emc_actors.append(a)

        # ── Оранжевый ореол вдоль маршрутов с ЭМС-нарушениями ───────────
        for ri, route in enumerate(routes):
            if not route_has_violation[ri] or len(route.positions) < 2:
                continue
            pts = np.array(route.positions, dtype=float)
            spline = pv.Spline(pts, n_points=max(len(pts) * 6, 30))
            halo = spline.tube(radius=self._tube_r * 1.65, n_sides=12)
            a = self.plotter.add_mesh(
                halo, color="#ff7700", opacity=0.30,
                smooth_shading=True, pickable=False
            )
            self._emc_actors.append(a)

    # запуск автоматической трассировки (муравьиный алгоритм или дейкстра)

    def _run_aco(self):
        if not self._pairs:
            QMessageBox.warning(self, "Нет пар",
                                "Добавьте пары соединений (режим «Пара»).")
            return
        g = self._graph.networkx_graph()
        if g.number_of_edges() == 0:
            QMessageBox.warning(self, "Граф пуст",
                                "Добавьте рёбра кабельных каналов (режим «Ребро»).")
            return

        invalid = [
            p.label for p in self._pairs
            if not g.has_node(p.source) or not g.has_node(p.target)
        ]
        if invalid:
            QMessageBox.warning(
                self, "Недействительные пары",
                "Следующие пары ссылаются на несуществующие узлы и будут пропущены:\n"
                + "\n".join(invalid)
            )

        # ── Проверка связности: нет ли пар без пути в графе ──────────────
        unreachable = []
        for pair in self._pairs:
            if g.has_node(pair.source) and g.has_node(pair.target):
                if not nx.has_path(g, pair.source, pair.target):
                    unreachable.append(pair.label)
        if unreachable:
            msg = (
                "Между узлами следующих пар нет пути в графе\n"
                "(компоненты несвязны — добавьте рёбра):\n\n"
                + "\n".join(f"  • {lbl}" for lbl in unreachable)
                + "\n\nПродолжить трассировку остальных пар?"
            )
            ans = QMessageBox.warning(
                self, "Недостижимые пары", msg,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if ans != QMessageBox.Yes:
                return
        # ─────────────────────────────────────────────────────────────────

        self._clear_routes()

        algo = self._algo_mode
        use_fallback = (
            self._chk_fallback.isChecked()
            if hasattr(self, "_chk_fallback") else True
        )

        bal = self._sld_balance.value()
        n_iters = self._sp_iters.value()
        params = ACOParams(
            n_ants=self._sp_ants.value(),
            n_iterations=n_iters,
            alpha=self._sp_alpha.value(),
            beta=self._sp_beta.value(),
            rho=self._sp_rho.value(),
            bundle_bonus=self._sp_bundle.value(),
            lambda1=(100 - bal) / 100.0,
        )
        tracer = Tracer(self._graph, params)

        self._worker = _TracingWorker(
            tracer, list(self._pairs), n_iters,
            algorithm=algo, aco_fallback=use_fallback,
        )
        self._worker.sig_progress.connect(self._on_tracing_progress)
        self._worker.sig_done.connect(self._on_tracing_done)
        self._worker.finished.connect(self._on_tracing_finished)

        algo_name = "Муравьиный алгоритм" if algo == "aco" else "Дейкстра"
        self._btn_run.setEnabled(False)
        self._show_progress()
        self._set_status(f"Трассировка запущена ({algo_name})…")
        self._worker.start()

    def _on_tracing_progress(self, text: str, pct: int):
        self._prog_bar.setValue(pct)
        self._lbl_hint.setText(text)
        self._update_stats()

    def _on_tracing_finished(self):
        self._worker = None

    def _on_tracing_done(self, routes):
        self._hide_progress()

        self._routes = routes
        for idx, route in enumerate(self._routes):
            self._draw_route_actor(route, idx)

        f1 = sum(r.length for r in self._routes)
        f2 = self._compute_f2(self._routes)
        self._refresh_routes_list(f1, f2)
        self._set_status(
            f"Готово: {len(self._routes)}/{len(self._pairs)} пар.   "
            f"F₁={f1:.1f} мм   F₂={f2:.1f} мм"
        )

    # управление прогресс-баром в строке состояния

    def _show_progress(self, indeterminate: bool = False):
        if indeterminate:
            self._prog_bar.setRange(0, 0)   # «бегущая» анимация
        else:
            self._prog_bar.setRange(0, 100)
            self._prog_bar.setValue(0)
        self._prog_bar.setVisible(True)
        self._btn_cancel.setVisible(True)
        self._btn_cancel.setEnabled(True)

    def _hide_progress(self):
        self._prog_bar.setRange(0, 100)
        self._prog_bar.setVisible(False)
        self._btn_cancel.setVisible(False)
        self._update_run_button()

    def _cancel_current(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._btn_cancel.setEnabled(False)
            self._set_status("Отмена трассировки…")
        elif self._autosel_worker and self._autosel_worker.isRunning():
            self._autosel_worker.cancel()
            self._btn_cancel.setEnabled(False)
            self._set_status("Отмена авто-выбора…")
        elif self._load_worker and self._load_worker.isRunning():
            self._btn_cancel.setEnabled(False)
            self._set_status("Ожидание завершения загрузки…")

    def _cancel_tracing(self):
        self._cancel_current()

    # вычисляет вторую целевую функцию: сумма произведений числа конфликтов на длину ребра
    def _compute_f2(self, routes) -> float:
        g = self._graph.networkx_graph()
        edge_routes: dict = {}
        for ri, route in enumerate(routes):
            for a, b in zip(route.path, route.path[1:]):
                key = (min(a, b), max(a, b))
                edge_routes.setdefault(key, []).append(ri)

        f2 = 0.0
        for (u, v), idxs in edge_routes.items():
            d = g[u][v].get("weight", 0.0)
            n_l = 0
            for i in range(len(idxs)):
                for j in range(i + 1, len(idxs)):
                    pi = routes[idxs[i]].pair
                    pj = routes[idxs[j]].pair
                    if emc_compatibility(pi.cable_class, pj.cable_class) < 1.0:
                        n_l += 1
            f2 += n_l * d
        return f2

    # управление деталями загруженной 3d-модели

    # конвертирует hex-цвет в кортеж (r, g, b) в диапазоне 0.0–1.0 для vtk
    @staticmethod
    def _hex_to_rgb01(hex_color: str) -> tuple:
        h = hex_color.lstrip("#")
        return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))

    def _refresh_parts_list(self):
        self._lst_parts.blockSignals(True)
        self._lst_parts.clear()
        for part in self._parts_data:
            item = QListWidgetItem(part["name"])
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if part["visible"] else Qt.Unchecked)
            bg = QColor(part["color"])
            bg.setAlpha(55)
            item.setBackground(bg)
            self._lst_parts.addItem(item)
        has = bool(self._parts_data)
        self._parts_hint.setVisible(not has)
        self._lst_parts.setVisible(has)
        self._lst_parts.blockSignals(False)

    def _on_part_visibility_changed(self, item: QListWidgetItem):
        idx = self._lst_parts.row(item)
        if not (0 <= idx < len(self._parts_data)):
            return
        visible = item.checkState() == Qt.Checked
        self._parts_data[idx]["visible"] = visible
        self._parts_data[idx]["actor"].SetVisibility(visible)
        self.plotter.render()

    def _on_part_selected(self, row: int):
        # Снять предыдущую подсветку
        if self._highlighted_part is not None:
            prev = self._parts_data[self._highlighted_part]
            r, g, b = self._hex_to_rgb01(prev["color"])
            prev["actor"].GetProperty().SetColor(r, g, b)
            prev["actor"].GetProperty().SetEdgeVisibility(False)
        self._highlighted_part = None

        if 0 <= row < len(self._parts_data):
            self._highlighted_part = row
            actor = self._parts_data[row]["actor"]
            actor.GetProperty().SetColor(1.0, 0.85, 0.1)   # жёлтая подсветка
            actor.GetProperty().SetEdgeVisibility(True)
            actor.GetProperty().SetEdgeColor(1.0, 0.6, 0.0)
        self.plotter.render()

    def _show_all_parts(self):
        for part in self._parts_data:
            part["visible"] = True
            part["actor"].SetVisibility(True)
        self._refresh_parts_list()
        self.plotter.render()

    def _isolate_part(self):
        row = self._lst_parts.currentRow()
        for i, part in enumerate(self._parts_data):
            visible = (i == row)
            part["visible"] = visible
            part["actor"].SetVisibility(visible)
        self._refresh_parts_list()
        self.plotter.render()

    # построение равномерной сетки кабельных каналов и операции над ней

    def _build_grid(self):
        if not self._parts_data:
            QMessageBox.warning(self, "Нет модели",
                                "Сначала загрузите 3D-модель.")
            return

        step = self._sp_grid_step.value()

        # Границы по всем деталям
        all_b = [p["actor"].GetBounds() for p in self._parts_data]
        x0 = min(b[0] for b in all_b); x1 = max(b[1] for b in all_b)
        y0 = min(b[2] for b in all_b); y1 = max(b[3] for b in all_b)
        z0 = min(b[4] for b in all_b); z1 = max(b[5] for b in all_b)

        xs = np.arange(x0, x1 + step * 0.01, step)
        ys = np.arange(y0, y1 + step * 0.01, step)
        zs = np.arange(z0, z1 + step * 0.01, step)

        # Защита от слишком мелкого шага (> 5000 рёбер — предупреждение)
        n_edges_est = (
            (len(xs) - 1) * len(ys) * len(zs) +
            len(xs) * (len(ys) - 1) * len(zs) +
            len(xs) * len(ys) * (len(zs) - 1)
        )
        if n_edges_est > 5000:
            ans = QMessageBox.question(
                self, "Много рёбер",
                f"При шаге {step:.1f} мм получится ~{n_edges_est} рёбер.\n"
                "Это может замедлить работу. Продолжить?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if ans != QMessageBox.Yes:
                return

        # Генерация узлов
        node_idx: dict = {}
        self._grid_nodes = []
        for iz, z in enumerate(zs):
            for iy, y in enumerate(ys):
                for ix, x in enumerate(xs):
                    node_idx[(ix, iy, iz)] = len(self._grid_nodes)
                    self._grid_nodes.append((float(x), float(y), float(z)))

        nx_c = len(xs); ny_c = len(ys); nz_c = len(zs)

        # Генерация рёбер (6 направлений)
        self._grid_edge_pairs = []
        for iz in range(nz_c):
            for iy in range(ny_c):
                for ix in range(nx_c):
                    i = node_idx[(ix, iy, iz)]
                    if ix + 1 < nx_c:
                        self._grid_edge_pairs.append((i, node_idx[(ix+1, iy, iz)]))
                    if iy + 1 < ny_c:
                        self._grid_edge_pairs.append((i, node_idx[(ix, iy+1, iz)]))
                    if iz + 1 < nz_c:
                        self._grid_edge_pairs.append((i, node_idx[(ix, iy, iz+1)]))

        self._grid_selected = set()
        self._render_grid()
        self._update_grid_count()
        self._set_mode(MODE_GRID_EDIT)

    def _render_grid(self):
        if self._grid_actor is not None:
            self.plotter.remove_actor(self._grid_actor)
            self._grid_actor = None

        if not self._grid_nodes or not self._grid_edge_pairs:
            return

        pts = np.array(self._grid_nodes, dtype=float)

        lines = []
        for i, j in self._grid_edge_pairs:
            lines.extend([2, i, j])

        mesh = pv.PolyData()
        mesh.points = pts
        mesh.lines = np.array(lines, dtype=int)

        scalars = np.array(
            [1.0 if idx in self._grid_selected else 0.0
             for idx in range(len(self._grid_edge_pairs))],
            dtype=float,
        )
        mesh.cell_data["sel"] = scalars

        self._grid_actor = self.plotter.add_mesh(
            mesh,
            scalars="sel",
            cmap=["#44445a", "#4488ff"],
            clim=[0.0, 1.0],
            line_width=2,
            show_scalar_bar=False,
            pickable=False,
            reset_camera=False,
        )
        self.plotter.render()

    # находит ближайшее ребро сетки к позиции курсора в экранных пикселях
    # использует векторизованную проекцию через матрицу камеры для быстрого поиска
    def _grid_nearest_edge_screen(self, vtk_x: int, vtk_y: int,
                                    threshold_px: int = 28) -> Optional[int]:
        if not self._grid_nodes or not self._grid_edge_pairs:
            return None

        renderer = self.plotter.renderer
        camera   = renderer.GetActiveCamera()
        w, h     = renderer.GetSize()
        if w == 0 or h == 0:
            return None

        # Векторизованная проекция всех середин рёбер в NDC через матрицу камеры
        nodes    = np.array(self._grid_nodes, dtype=float)
        midpts   = np.array(
            [(nodes[i] + nodes[j]) * 0.5 for i, j in self._grid_edge_pairs],
            dtype=float,
        )
        aspect   = renderer.GetTiledAspectRatio()
        m_vtk    = camera.GetCompositeProjectionTransformMatrix(aspect, -1, 1)
        mat      = np.array(
            [[m_vtk.GetElement(r, c) for c in range(4)] for r in range(4)]
        )

        pts_h = np.hstack([midpts, np.ones((len(midpts), 1))])  # Nx4
        clip  = (mat @ pts_h.T).T                               # Nx4
        w_c   = clip[:, 3]
        valid = w_c > 0
        # Проецируем только видимые точки
        w_c_safe = np.where(valid, w_c, 1.0)
        sx = (clip[:, 0] / w_c_safe + 1.0) * 0.5 * w
        sy = (clip[:, 1] / w_c_safe + 1.0) * 0.5 * h

        dx = sx - vtk_x
        dy = sy - vtk_y
        d2 = dx * dx + dy * dy
        d2[~valid] = np.inf

        best = int(np.argmin(d2))
        return best if d2[best] <= threshold_px ** 2 else None

    # обновляет подсветку ребра сетки под курсором при наведении
    def _update_grid_hover(self, idx: Optional[int]):
        if idx == self._grid_hover_idx:
            return
        self._clear_grid_hover()
        self._grid_hover_idx = idx
        if idx is None:
            return
        i, j = self._grid_edge_pairs[idx]
        pts  = np.array(self._grid_nodes, dtype=float)
        p0, p1 = pts[i], pts[j]
        tube = pv.Line(p0, p1).tube(radius=self._tube_r * 0.45, n_sides=8)
        self._grid_hover_actor = self.plotter.add_mesh(
            tube, color="#cba6f7", smooth_shading=True,
            pickable=False, reset_camera=False,
        )
        self.plotter.render()

    def _clear_grid_hover(self):
        if self._grid_hover_actor is not None:
            self.plotter.remove_actor(self._grid_hover_actor)
            self._grid_hover_actor = None
        self._grid_hover_idx = None

    def _toggle_grid_edge(self, idx: int):
        if idx in self._grid_selected:
            self._grid_selected.discard(idx)
        else:
            self._grid_selected.add(idx)
        self._render_grid()
        self._update_grid_count()

    def _update_grid_count(self):
        total = len(self._grid_edge_pairs)
        sel = len(self._grid_selected)
        if total == 0:
            self._lbl_grid_count.setText("Сетка не создана")
        else:
            self._lbl_grid_count.setText(
                f"Выбрано: <b>{sel}</b> / {total} рёбер"
            )
        self._lbl_grid_count.setStyleSheet(
            "color:#a6e3a1; font-size:8pt; padding:2px;" if sel > 0
            else "color:#6c7086; font-size:8pt; padding:2px;"
        )

    def _select_all_grid_edges(self):
        self._grid_selected = set(range(len(self._grid_edge_pairs)))
        self._render_grid()
        self._update_grid_count()

    def _clear_grid_selection(self):
        self._grid_selected.clear()
        self._render_grid()
        self._update_grid_count()

    def _auto_select_near_surface(self):
        if not self._grid_edge_pairs:
            QMessageBox.warning(self, "Нет сетки", "Сначала создайте сетку.")
            return
        if not self._parts_data:
            QMessageBox.warning(self, "Нет модели", "Сначала загрузите 3D-модель.")
            return

        threshold = self._sp_grid_surf_dist.value()
        self._autosel_worker = _AutoSelectWorker(
            self._parts_data, self._grid_nodes, self._grid_edge_pairs, threshold
        )
        self._autosel_worker.sig_progress.connect(self._on_autosel_progress)
        self._autosel_worker.sig_done.connect(self._on_autosel_done)
        self._autosel_worker.finished.connect(self._on_autosel_finished)

        self._show_progress()
        self._set_status("Авто-выбор: подготовка…")
        self._autosel_worker.start()

    def _on_autosel_progress(self, text: str, pct: int):
        self._prog_bar.setValue(pct)
        self._lbl_hint.setText(text)

    def _on_autosel_finished(self):
        self._autosel_worker = None

    def _on_autosel_done(self, selected):
        self._hide_progress()
        if selected is None:
            self._set_status("Авто-выбор отменён.")
            return
        threshold = self._sp_grid_surf_dist.value()
        self._grid_selected = selected
        self._render_grid()
        self._update_grid_count()
        self._set_status(
            f"Авто-выбор завершён: {len(self._grid_selected)} из "
            f"{len(self._grid_edge_pairs)} рёбер (порог {threshold:.1f} мм)"
        )

    # запуск верификации маршрутов

    def _run_verify(self):
        if not self._routes:
            QMessageBox.information(self, "Верификация",
                                    "Нет маршрутов для проверки.")
            return
        if self._verify_worker and self._verify_worker.isRunning():
            return

        self._btn_verify.setEnabled(False)
        self._show_progress()
        self._set_status("Верификация маршрутов…")

        self._verify_worker = _VerifyWorker(
            list(self._routes), self._graph, list(self._parts_data)
        )
        self._verify_worker.sig_progress.connect(self._on_verify_progress)
        self._verify_worker.sig_done.connect(self._on_verify_done)
        self._verify_worker.finished.connect(self._on_verify_finished)
        self._verify_worker.start()

    def _on_verify_progress(self, text: str, pct: int):
        self._prog_bar.setValue(pct)
        self._lbl_hint.setText(text)

    def _on_verify_finished(self):
        self._verify_worker = None

    def _on_verify_done(self, results: list):
        self._hide_progress()
        self._btn_verify.setEnabled(True)

        n_ok = sum(1 for r in results if r.ok)
        n    = len(results)
        self._set_status(
            f"Верификация завершена: {n_ok}/{n} маршрутов прошли проверку."
        )

        # Обновить цвет меток в списке маршрутов
        for ri, res in enumerate(results):
            if ri < self._lst_routes.count():
                item = self._lst_routes.item(ri)
                if item:
                    marker = "✓ " if res.ok else "✗ "
                    text = item.text().lstrip("✓✗ ")
                    item.setText(marker + text)
                    item.setForeground(
                        QColor(res.color if res.ok else "#f38ba8")
                    )

        dlg = _VerifyDialog(results, bool(self._parts_data), parent=self)
        dlg.show()

    # запуск верификации рёбер графа на пересечение с деталями модели

    def _run_graph_edge_verify(self):
        if not self._parts_data:
            QMessageBox.information(self, "Верификация графа",
                                    "Сначала загрузите 3D-модель.")
            return
        g = self._graph.networkx_graph()
        if g.number_of_edges() == 0:
            QMessageBox.information(self, "Верификация графа",
                                    "Граф каналов не содержит рёбер.")
            return
        if self._graph_verify_worker and self._graph_verify_worker.isRunning():
            return

        self._btn_graph_verify.setEnabled(False)
        self._show_progress()
        self._set_status("Верификация рёбер графа…")

        self._graph_verify_worker = _GraphEdgeVerifyWorker(
            self._graph, list(self._parts_data)
        )
        self._graph_verify_worker.sig_progress.connect(
            lambda text, pct: (self._lbl_hint.setText(text),
                               self._prog_bar.setValue(pct))
        )
        self._graph_verify_worker.sig_done.connect(self._on_graph_edge_verify_done)
        self._graph_verify_worker.finished.connect(
            lambda: setattr(self, "_graph_verify_worker", None)
        )
        self._graph_verify_worker.start()

    def _on_graph_edge_verify_done(self, colliding: set):
        self._hide_progress()
        self._btn_graph_verify.setEnabled(True)
        self._edge_collisions = colliding

        for key, actor in self._edge_actors.items():
            color = (1.0, 0.2, 0.2) if key in colliding else (0.267, 0.533, 1.0)
            actor.GetProperty().SetColor(*color)
        self.plotter.render()

        self._refresh_edges_list()
        n_bad = len(colliding)
        n_tot = len(self._edge_actors)
        if n_bad:
            self._set_status(
                f"Верификация: {n_bad} из {n_tot} рёбер пересекают детали — выделены красным."
            )
            self._toast(
                f"{n_bad} рёбер проходят сквозь детали модели", "warning"
            )
        else:
            self._set_status(
                f"Верификация: все {n_tot} рёбер чисты — коллизий не обнаружено."
            )
            self._toast("Коллизий не обнаружено", "success")

    # применяет выбранные рёбра сетки как граф кабельных каналов
    def _apply_grid_to_graph(self):
        if not self._grid_selected:
            QMessageBox.warning(self, "Нет рёбер",
                                "Выберите хотя бы одно ребро сетки.")
            return

        self._clear_all(confirmed=True)

        used_nodes: set = set()
        for idx in self._grid_selected:
            i, j = self._grid_edge_pairs[idx]
            used_nodes.add(i)
            used_nodes.add(j)

        node_map: dict = {}
        for grid_idx in sorted(used_nodes):
            pos = self._grid_nodes[grid_idx]
            nid = self._graph.add_node(pos)
            node_map[grid_idx] = nid
            actor = self.plotter.add_mesh(
                pv.Sphere(radius=self._sphere_r, center=pos),
                color="#00cc66", smooth_shading=True, pickable=True,
            )
            self._node_actors[nid] = actor

        for idx in self._grid_selected:
            i, j = self._grid_edge_pairs[idx]
            u, v = node_map[i], node_map[j]
            self._graph.add_edge(u, v)
            self._draw_edge_actor(u, v)

        self._refresh_all_lists()
        self._set_mode(MODE_NAVIGATE)
        self._set_status(
            f"Граф построен из сетки: {len(used_nodes)} узлов, "
            f"{len(self._grid_selected)} рёбер"
        )

    def _clear_grid(self):
        if self._grid_actor is not None:
            self.plotter.remove_actor(self._grid_actor)
            self._grid_actor = None
        self._grid_nodes = []
        self._grid_edge_pairs = []
        self._grid_selected = set()
        self._update_grid_count()
        if self._mode == MODE_GRID_EDIT:
            self._set_mode(MODE_NAVIGATE)
        self.plotter.render()

    # файловые операции: открытие модели и сохранение/загрузка графа

    def _open_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Открыть 3D модель", "",
            "3D модели (*.stl *.obj *.ply *.vtk *.vtp *.glb *.gltf *.wrl *.vrml);;"
            "STL (*.stl);;"
            "OBJ + MTL — Blender экспорт (*.obj);;"
            "GLTF/GLB — Blender экспорт (*.glb *.gltf);;"
            "Все файлы (*.*)",
        )
        if not path:
            return

        self._load_worker = _ModelLoadWorker(path)
        self._load_worker.sig_done.connect(self._on_model_loaded)
        self._load_worker.sig_error.connect(self._on_model_error)
        self._load_worker.finished.connect(self._on_load_finished)

        self._set_status(f"Загружается: {Path(path).name}…")
        self._load_worker.start()

    def _on_load_finished(self):
        self._load_worker = None

    def _on_model_loaded(self, raw_parts: list, path: str):

        total_pts = sum(m.n_points for m, _, _n in raw_parts if hasattr(m, "n_points"))
        if total_pts == 0:
            QMessageBox.warning(
                self, "Пустая модель",
                "Файл загружен, но не содержит видимой геометрии.\n"
                "Попробуйте экспортировать модель в формате STL или OBJ.",
            )
            return

        self._highlighted_part = None
        for pd in self._parts_data:
            self.plotter.remove_actor(pd["actor"])
        self._parts_data.clear()

        all_b = [m.bounds for m, _, _n in raw_parts if hasattr(m, "bounds")]
        bx0 = min(b[0] for b in all_b); bx1 = max(b[1] for b in all_b)
        by0 = min(b[2] for b in all_b); by1 = max(b[3] for b in all_b)
        bz0 = min(b[4] for b in all_b); bz1 = max(b[5] for b in all_b)
        diag = math.sqrt((bx1-bx0)**2 + (by1-by0)**2 + (bz1-bz0)**2)
        self._sphere_r = max(diag * 0.005, 0.2)
        self._tube_r   = max(diag * 0.005, 0.2)

        for mesh, color, name in raw_parts:
            actor = self.plotter.add_mesh(
                mesh, color=color, show_edges=False, smooth_shading=True,
                ambient=0.15, diffuse=0.75, specular=0.3, specular_power=30,
                opacity=1.0, pickable=True,
            )
            self._parts_data.append({
                "actor": actor, "color": color,
                "name": name,  "visible": True, "mesh": mesh,
            })

        self._current_model_path = path
        self._refresh_parts_list()
        self.plotter.reset_camera()
        self._set_mode(self._mode)
        self._add_recent_file(path)

        self._set_status(
            f"Загружено: {Path(path).name}   {len(raw_parts)} деталей   "
            f"{total_pts:,} точек   диагональ={diag:.1f}"
        )

    def _on_model_error(self, msg: str):
        if msg == "__NO_TRIMESH__":
            QMessageBox.critical(
                self, "Нет библиотеки trimesh",
                "Для загрузки GLTF/GLB установите trimesh:\n\n"
                "  pip install trimesh\n\n"
                "Либо экспортируйте модель в формат STL или OBJ.",
            )
        elif msg.startswith("__FNFE__"):
            exc_text = msg[len("__FNFE__"):]
            missing = Path(exc_text.split("'")[-2]) if "'" in exc_text else exc_text
            QMessageBox.critical(
                self, "Ошибка",
                f"Не найден файл, на который ссылается модель:\n{missing}\n\n"
                "При экспорте GLTF Blender создаёт два файла (.gltf + .bin) —\n"
                "оба должны лежать в одной папке.\n\n"
                "Проще всего экспортировать в формат GLB (один файл).",
            )
        else:
            QMessageBox.critical(self, "Ошибка загрузки", msg)


    # работа с базой данных: сохранение и загрузка проектов

    # собирает граф в словарь для сохранения
    def _current_graph_dict(self) -> dict:
        return self._graph.to_dict()

    def _current_pairs_list(self) -> list[dict]:
        return [
            {"source": p.source, "target": p.target, "label": p.label,
             "wire_type": p.cable_class.wire_type.value,
             "shielded":  p.cable_class.shielded}
            for p in self._pairs
        ]

    # экспорт найденных маршрутов в dxf-файл для autocad

    def _export_dxf(self):
        if not self._routes:
            QMessageBox.warning(
                self, "Нет маршрутов",
                "Сначала запустите трассировку (▶ Запустить)."
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить маршруты в DXF",
            "routes.dxf",
            "DXF файлы (*.dxf);;Все файлы (*.*)",
        )
        if not path:
            return

        try:
            n = export_routes_dxf(self._routes, path)
        except ImportError as e:
            QMessageBox.critical(self, "Нет ezdxf", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "Ошибка экспорта", str(e))
            return

        self._set_status(f"Экспортировано {n} маршрутов → {Path(path).name}")
        self._toast(f"Экспорт завершён: {n} маршрутов\n{Path(path).name}", "success")

    def _open_db_settings(self):
        DBSettingsDialog(self).exec_()

    def _open_db_manager(self):
        try:
            db.init_schema()
        except ImportError as e:
            QMessageBox.critical(self, "Нет psycopg2", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "Ошибка БД", f"Не удалось подключиться:\n{e}")
            return
        DBManagerDialog(self).exec_()

    def _db_save(self):
        try:
            db.init_schema()
        except ImportError as e:
            QMessageBox.critical(self, "Нет psycopg2", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "Ошибка БД", f"Не удалось подключиться:\n{e}")
            return

        dlg = ProjectDialog(mode="save", parent=self)
        if dlg.exec_() != ProjectDialog.Accepted:
            return
        data = dlg.result_data()
        if data is None:
            return

        g = self._current_graph_dict()
        p = self._current_pairs_list()
        try:
            if data["action"] == "save_new":
                pid = db.save_project(data["name"], data["description"], g, p,
                                      model_path=self._current_model_path)
                self._set_status(f"Проект «{data['name']}» сохранён в БД (ID {pid}).")
                self._toast(f"Проект сохранён\n«{data['name']}» (ID {pid})", "success")
            else:
                db.update_project(data["project_id"], data["name"],
                                  data["description"], g, p,
                                  model_path=self._current_model_path)
                self._set_status(
                    f"Проект «{data['name']}» обновлён (ID {data['project_id']}).")
                self._toast(f"Проект обновлён\n«{data['name']}»", "success")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сохранения", str(e))

    def _db_load(self):
        try:
            db.init_schema()
        except ImportError as e:
            QMessageBox.critical(self, "Нет psycopg2", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "Ошибка БД", f"Не удалось подключиться:\n{e}")
            return

        dlg = ProjectDialog(mode="load", parent=self)
        if dlg.exec_() != ProjectDialog.Accepted:
            return
        data = dlg.result_data()
        if data is None or data.get("action") != "load":
            return

        try:
            proj = db.load_project(data["project_id"])
        except Exception as e:
            QMessageBox.critical(self, "Ошибка загрузки", str(e))
            return

        self._clear_all(confirmed=True)
        self._graph.from_dict(proj["graph"])
        self._pairs = [
            ConnectionPair(
                source=p["source"], target=p["target"],
                label=p.get("label", ""),
                cable_class=CableClass(
                    wire_type=WireType(p.get("wire_type", WireType.DIGITAL.value)),
                    shielded=bool(p.get("shielded", False)),
                ),
            )
            for p in proj["pairs"]
        ]

        for nid, nd in self._graph.nodes(data=True):
            actor = self.plotter.add_mesh(
                pv.Sphere(radius=self._sphere_r, center=nd["pos"]),
                color="#00cc66", smooth_shading=True,
            )
            self._node_actors[nid] = actor

        for u, v in self._graph.edges():
            self._draw_edge_actor(u, v)

        for pair in self._pairs:
            for nid, color in [(pair.source, "#ff3333"), (pair.target, "#ff8800")]:
                pos = self._graph.nodes[nid]["pos"]
                a = self.plotter.add_mesh(
                    pv.Sphere(radius=self._sphere_r * 1.35, center=pos),
                    color=color, smooth_shading=True, opacity=0.75,
                )
                self._pair_actors.append(a)

        self._refresh_all_lists()
        g = self._graph.networkx_graph()
        self._set_status(
            f"Загружен «{proj['name']}»: "
            f"{g.number_of_nodes()} узлов, "
            f"{g.number_of_edges()} рёбер, {len(self._pairs)} пар."
        )

        model_path = proj.get("model_path", "")
        if model_path and Path(model_path).exists():
            self._load_model_path(model_path)
        elif model_path:
            self._set_status(
                f"Загружен «{proj['name']}», но файл модели не найден: {model_path}"
            )

    def _save_graph(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить граф каналов", "", "JSON (*.json);;Все файлы (*.*)",
        )
        if not path:
            return
        data = self._graph.to_dict()
        data["pairs"] = [
            {"source": p.source, "target": p.target, "label": p.label,
             "wire_type": p.cable_class.wire_type.value,
             "shielded":  p.cable_class.shielded}
            for p in self._pairs
        ]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self._set_status(f"Граф сохранён: {Path(path).name}")
        self._toast(f"Граф сохранён\n{Path(path).name}", "success")

    def _load_graph(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Загрузить граф каналов", "", "JSON (*.json);;Все файлы (*.*)",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Ошибка чтения JSON:\n{exc}")
            return

        self._clear_all(confirmed=True)
        self._graph.from_dict(data)
        self._pairs = [
            ConnectionPair(
                source=p["source"], target=p["target"],
                label=p.get("label", f"Проводник {i+1}"),
                cable_class=CableClass(
                    wire_type=WireType(p.get("wire_type", WireType.DIGITAL.value)),
                    shielded=bool(p.get("shielded", False)),
                ),
            )
            for i, p in enumerate(data.get("pairs", []))
        ]

        for nid, nd in self._graph.nodes(data=True):
            actor = self.plotter.add_mesh(
                pv.Sphere(radius=self._sphere_r, center=nd["pos"]),
                color="#00cc66", smooth_shading=True,
            )
            self._node_actors[nid] = actor

        for u, v in self._graph.edges():
            self._draw_edge_actor(u, v)

        for pair in self._pairs:
            for nid, color in [(pair.source, "#ff3333"), (pair.target, "#ff8800")]:
                pos = self._graph.nodes[nid]["pos"]
                a = self.plotter.add_mesh(
                    pv.Sphere(radius=self._sphere_r * 1.35, center=pos),
                    color=color, smooth_shading=True, opacity=0.75,
                )
                self._pair_actors.append(a)

        self._refresh_all_lists()
        g = self._graph.networkx_graph()
        self._set_status(
            f"Загружено: {g.number_of_nodes()} узлов, "
            f"{g.number_of_edges()} рёбер, {len(self._pairs)} пар"
        )
        self._toast(
            f"Граф загружен: {g.number_of_nodes()} узлов, "
            f"{g.number_of_edges()} рёбер", "info"
        )

    # методы очистки данных и 3d-сцены

    def _clear_routes(self):
        for a in self._route_actors:
            self.plotter.remove_actor(a)
        self._route_actors.clear()
        self._route_actor_map.clear()
        for a in self._bundle_actors:
            self.plotter.remove_actor(a)
        self._bundle_actors.clear()
        for a in self._emc_actors:
            self.plotter.remove_actor(a)
        self._emc_actors.clear()
        self._routes.clear()
        self._refresh_routes_list()
        self._update_run_button()

    def _confirm_clear_all(self):
        ans = QMessageBox.question(
            self, "Очистить всё",
            "Удалить граф, пары соединений и все маршруты?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ans == QMessageBox.Yes:
            self._clear_all()

    def _clear_all(self, confirmed: bool = False):
        self._clear_routes()
        for a in self._pair_actors:    self.plotter.remove_actor(a)
        self._pair_actors.clear()
        for a in self._edge_actors.values(): self.plotter.remove_actor(a)
        self._edge_actors.clear()
        for a in self._node_actors.values(): self.plotter.remove_actor(a)
        self._node_actors.clear()
        self._cancel_pending()
        self._graph = CableChannelGraph()
        self._pairs.clear()
        self._undo_stack.clear()
        self._update_edit_actions()
        self._refresh_all_lists()
        self._set_status("Граф очищен.")

    # удаление выбранных элементов через кнопку или клавишу delete

    def _delete_selected_node(self):
        item = self._lst_nodes.currentItem()
        if item is None:
            return
        nid = item.data(Qt.UserRole)
        if nid is None:
            return
        self._undo_stack.push(_RemoveNodeCmd(self, nid))
        self._update_edit_actions()

    def _delete_selected_edge(self):
        item = self._lst_edges.currentItem()
        if item is None:
            return
        key = item.data(Qt.UserRole)
        if key is None:
            return
        u, v = key
        self._undo_stack.push(_RemoveEdgeCmd(self, u, v))
        self._update_edit_actions()

    def _delete_selected_pair(self):
        row = self._lst_pairs.currentRow()
        if 0 <= row < len(self._pairs):
            label = self._pairs[row].label
            del self._pairs[row]
            self._refresh_pairs_list()
            self._set_status(f"Пара «{label}» удалена.")

    def _on_pair_selected(self, row: int):
        has = 0 <= row < len(self._pairs)
        self._cmb_cable_type.setEnabled(has)
        self._chk_shielded.setEnabled(has)
        can_manual = has and bool(self._graph.nodes)
        self._btn_manual_start.setEnabled(
            can_manual and self._mode != MODE_MANUAL_ROUTE
        )
        if not has:
            return
        pair = self._pairs[row]
        self._cmb_cable_type.blockSignals(True)
        self._chk_shielded.blockSignals(True)
        self._cmb_cable_type.setCurrentText(pair.cable_class.wire_type.value)
        self._chk_shielded.setChecked(pair.cable_class.shielded)
        self._cmb_cable_type.blockSignals(False)
        self._chk_shielded.blockSignals(False)

    def _on_emc_type_changed(self, text: str):
        row = self._lst_pairs.currentRow()
        if 0 <= row < len(self._pairs):
            try:
                wt = WireType(text)
            except ValueError:
                return
            cc = self._pairs[row].cable_class
            self._pairs[row].cable_class = CableClass(wire_type=wt, shielded=cc.shielded)
            self._refresh_pairs_list()

    def _on_shielded_changed(self, state: int):
        row = self._lst_pairs.currentRow()
        if 0 <= row < len(self._pairs):
            cc = self._pairs[row].cable_class
            self._pairs[row].cable_class = CableClass(wire_type=cc.wire_type,
                                                       shielded=bool(state))

    def _update_emc_matrix(self):
        n = len(self._pairs)
        self._tbl_emc.setRowCount(n)
        self._tbl_emc.setColumnCount(n)
        if n == 0:
            return
        headers = [p.label for p in self._pairs]
        self._tbl_emc.setHorizontalHeaderLabels(headers)
        self._tbl_emc.setVerticalHeaderLabels(headers)
        for i, pi in enumerate(self._pairs):
            for j, pj in enumerate(self._pairs):
                p_ij = emc_compatibility(pi.cable_class, pj.cable_class)
                item = QTableWidgetItem(f"{p_ij:.2f}")
                item.setTextAlignment(Qt.AlignCenter)
                if p_ij >= 0.9:
                    item.setBackground(QColor("#1a3a2a"))
                    item.setForeground(QColor("#a6e3a1"))
                elif p_ij >= 0.5:
                    item.setBackground(QColor("#2a2a10"))
                    item.setForeground(QColor("#f9e2af"))
                else:
                    item.setBackground(QColor("#3a1a1a"))
                    item.setForeground(QColor("#f38ba8"))
                self._tbl_emc.setItem(i, j, item)

    # обновление списков в боковой панели после изменений

    def _refresh_all_lists(self):
        self._refresh_nodes_list()
        self._refresh_edges_list()
        self._refresh_pairs_list()
        self._refresh_routes_list()
        self._update_run_button()

    # разблокирует кнопку запуска если есть рёбра и пары, и не идёт трассировка
    def _update_run_button(self):
        g = self._graph.networkx_graph()
        ok = g.number_of_edges() > 0 and len(self._pairs) > 0
        self._btn_run.setEnabled(ok and self._worker is None)

    def _refresh_nodes_list(self):
        self._lst_nodes.clear()
        for nid, data in self._graph.nodes(data=True):
            pos = data["pos"]
            item = QListWidgetItem(
                f"  N{nid}   ({pos[0]:.1f},  {pos[1]:.1f},  {pos[2]:.1f})"
            )
            item.setData(Qt.UserRole, nid)
            item.setForeground(QColor("#00cc66"))
            self._lst_nodes.addItem(item)

    def _refresh_edges_list(self):
        self._lst_edges.clear()
        g = self._graph.networkx_graph()
        for u, v in self._graph.edges():
            w    = g[u][v].get("weight", 0.0)
            load = g[u][v].get("load", 0)
            key  = (min(u, v), max(u, v))
            collides = key in self._edge_collisions
            label = f"  {'⚠ ' if collides else ''}{u}—{v}   L={w:.1f}   провод: {load}"
            item  = QListWidgetItem(label)
            item.setData(Qt.UserRole, key)
            item.setForeground(QColor("#ff4444" if collides else "#4488ff"))
            self._lst_edges.addItem(item)
        self._update_run_button()

    def _refresh_pairs_list(self):
        cur = self._lst_pairs.currentRow()
        # переименовываем старые метки "Жгут N" в "Проводник N"
        for pair in self._pairs:
            if pair.label and pair.label.startswith("Жгут "):
                pair.label = "Проводник " + pair.label[len("Жгут "):]
        self._lst_pairs.clear()
        for pair in self._pairs:
            item = QListWidgetItem(
                f"  {pair.label}:  {pair.source} → {pair.target}"
                f"  [{pair.cable_class.wire_type.value}{'  Э' if pair.cable_class.shielded else ''}]"
            )
            item.setForeground(QColor("#ffaa00"))
            self._lst_pairs.addItem(item)
        if 0 <= cur < len(self._pairs):
            self._lst_pairs.setCurrentRow(cur)
        self._update_emc_matrix()
        self._update_run_button()

    # группирует маршруты в жгуты через union-find:
    # маршруты, проходящие через общее ребро, объединяются в один жгут
    @staticmethod
    def _compute_bundles(n: int, edge_routes: dict) -> list:
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        for idxs in edge_routes.values():
            for i in range(1, len(idxs)):
                union(idxs[0], idxs[i])

        groups: dict = {}
        for ri in range(n):
            groups.setdefault(find(ri), []).append(ri)
        return list(groups.values())

    def _refresh_routes_list(self, f1: float = None, f2: float = None):
        self._lst_routes.clear()
        total = 0.0

        if not self._routes:
            self._lbl_f1_val.setText("—")
            self._lbl_f2_val.setText("—")
            self._lbl_obj_val.setText("—")
            return

        g = self._graph.networkx_graph()

        # ── Ребро → список маршрутов ─────────────────────────────────
        edge_routes: dict = {}
        for ri, route in enumerate(self._routes):
            for a, b in zip(route.path, route.path[1:]):
                key = (min(a, b), max(a, b))
                edge_routes.setdefault(key, []).append(ri)

        # ── ЭМС-конфликты на маршрут ─────────────────────────────────
        route_emc = [{"n": 0, "len": 0.0} for _ in self._routes]
        for (u, v), idxs in edge_routes.items():
            d = g[u][v].get("weight", 0.0) if g.has_edge(u, v) else 0.0
            for i in range(len(idxs)):
                for j in range(i + 1, len(idxs)):
                    ri, rj = idxs[i], idxs[j]
                    pi = self._routes[ri].pair
                    pj = self._routes[rj].pair
                    if emc_compatibility(pi.cable_class, pj.cable_class) < 1.0:
                        route_emc[ri]["n"] += 1
                        route_emc[ri]["len"] += d
                        route_emc[rj]["n"] += 1
                        route_emc[rj]["len"] += d

        # ── Группировка в жгуты ───────────────────────────────────────
        bundles = self._compute_bundles(len(self._routes), edge_routes)
        multi   = sorted([b for b in bundles if len(b) > 1], key=lambda b: b[0])
        singles = [b[0] for b in bundles if len(b) == 1]

        def _add_route_item(ri: int, prefix: str):
            nonlocal total
            route    = self._routes[ri]
            n_conf   = route_emc[ri]["n"]
            conf_len = route_emc[ri]["len"]
            emc_str  = f"конфл. {conf_len:.1f} мм ({n_conf} реб.)" if n_conf else "норма"
            item = QListWidgetItem(
                f"{prefix}{route.pair.label}   L={route.length:.1f}   ЭМС: {emc_str}"
            )
            item.setForeground(QColor(route.color))
            item.setToolTip(
                f"Маршрут: {route.pair.label}\n"
                f"Длина: {route.length:.1f} мм\n"
                f"Узлов: {len(route.path)}\n"
                f"Тип кабеля: {route.pair.cable_class.wire_type.value}  "
                f"{'экранированный' if route.pair.cable_class.shielded else 'неэкранированный'}\n"
                f"ЭМС-конфликты: {n_conf} рёбер  {conf_len:.1f} мм"
            )
            self._lst_routes.addItem(item)
            total += route.length

        def _add_bundle_header(text: str, multi: bool):
            item = QListWidgetItem(text)
            item.setFlags(Qt.ItemIsEnabled)
            item.setBackground(QColor("#252545" if multi else "#1e2030"))
            item.setForeground(QColor("#89b4fa" if multi else "#585b70"))
            f = item.font()
            f.setBold(True)
            item.setFont(f)
            self._lst_routes.addItem(item)

        # ── Многопроводные жгуты ──────────────────────────────────────
        for bi, bundle in enumerate(multi):
            bundle_set = set(bundle)
            shared_len = sum(
                g[u][v].get("weight", 0.0)
                for (u, v), idxs in edge_routes.items()
                if g.has_edge(u, v) and len(set(idxs) & bundle_set) >= 2
            )
            wire_word = "провода" if 2 <= len(bundle) <= 4 else "проводов"
            _add_bundle_header(
                f"  Жгут {bi + 1}   ▪   {len(bundle)} {wire_word}"
                f"   ▪   общий участок {shared_len:.1f} мм",
                multi=True,
            )
            for k, ri in enumerate(bundle):
                prefix = "    └  " if k == len(bundle) - 1 else "    ├  "
                _add_route_item(ri, prefix)

        # ── Одиночные провода ─────────────────────────────────────────
        if singles:
            _add_bundle_header(
                f"  Одиночные провода   ▪   {len(singles)} шт.", multi=False
            )
            for k, ri in enumerate(singles):
                prefix = "    └  " if k == len(singles) - 1 else "    ├  "
                _add_route_item(ri, prefix)

        # ── Итоговая строка ───────────────────────────────────────────
        if f1 is None:
            f1 = total
        if f2 is None:
            f2 = self._compute_f2(self._routes)
        bal = self._sld_balance.value()
        l1 = (100 - bal) / 100.0
        l2 = bal / 100.0
        obj = l1 * f1 + l2 * f2
        self._lbl_f1_val.setText(f"{f1:.1f} мм")
        self._lbl_f2_val.setText(f"{f2:.1f} мм")
        self._lbl_obj_val.setText(f"{obj:.1f} мм")

    # вспомогательные методы

    def _remove_highlight(self):
        if self._highlight_actor is not None:
            self.plotter.remove_actor(self._highlight_actor)
            self._highlight_actor = None

    def _set_status(self, text: str):
        self._lbl_hint.setText(text)
        self._update_stats()

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        self.plotter.close()
        super().closeEvent(event)


# точка входа — создаёт qt-приложение и запускает главное окно
def run():
    import os
    # устанавливаем переменные окружения для корректного масштабирования на hdpi-экранах
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
    os.environ.pop("QT_DEVICE_PIXEL_RATIO", None)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Трассировка жгутов")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
