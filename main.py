import sys
from pathlib import Path

# добавляем корневую папку проекта в путь поиска модулей,
# чтобы можно было импортировать пакеты ui и core
sys.path.insert(0, str(Path(__file__).resolve().parent))

# импортируем функцию запуска главного окна
from ui.main_window import run

# точка входа — запускаем приложение только если файл запущен напрямую
if __name__ == "__main__":
    run()
