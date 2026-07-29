# модуль для экспорта маршрутов трассировки в формат dxf
# dxf-файл можно открыть в autocad или любой другой cad-программе

# пробуем импортировать библиотеку для работы с dxf
try:
    import ezdxf
    from ezdxf.colors import rgb2int
    _EZDXF_OK = True
except ImportError:
    # если ezdxf не установлен, экспорт будет недоступен
    _EZDXF_OK = False

# набор цветов aci (индексная палитра autocad) для слоёв по порядку
_ACI_PALETTE = [1, 2, 3, 4, 5, 6, 30, 40, 50, 70, 90, 130]


# конвертирует hex-цвет в кортеж (r, g, b)
def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# главная функция экспорта: записывает маршруты в dxf-файл
def export_routes_dxf(routes, path: str) -> int:
    # проверяем что библиотека установлена
    if not _EZDXF_OK:
        raise ImportError("Установите ezdxf:  pip install ezdxf")
    # проверяем что есть что экспортировать
    if not routes:
        raise ValueError("Нет маршрутов для экспорта.")

    # создаём новый dxf-документ формата autocad 2010
    doc = ezdxf.new("R2010")
    # устанавливаем единицы измерения: миллиметры
    doc.header["$INSUNITS"] = 4
    # получаем пространство модели для добавления объектов
    msp = doc.modelspace()

    # словарь для отслеживания уже созданных слоёв
    created_layers: dict[str, int] = {}
    exported = 0

    for idx, route in enumerate(routes):
        pair = route.pair
        # преобразуем координаты точек в кортежи float
        pts = [tuple(float(c) for c in p) for p in route.positions]
        # пропускаем маршруты с менее чем 2 точками
        if len(pts) < 2:
            continue

        # имя слоя формируем из типа провода и признака экранирования
        shield_tag = "Э" if pair.cable_class.shielded else "НЭ"
        raw_name = f"{pair.cable_class.wire_type.value}_{shield_tag}"
        # ограничиваем длину имени слоя до 31 символа (лимит dxf)
        layer_name = raw_name[:31]

        # создаём слой только один раз для каждого типа провода
        if layer_name not in created_layers:
            aci = _ACI_PALETTE[len(created_layers) % len(_ACI_PALETTE)]
            created_layers[layer_name] = aci
            layer = doc.layers.new(layer_name)
            layer.color = aci

        # конвертируем цвет маршрута из hex в формат true color для dxf
        route_color_rgb = _hex_to_rgb(route.color)
        true_color_int  = rgb2int(route_color_rgb)

        # добавляем 3d-полилинию маршрута в пространство модели
        msp.add_polyline3d(
            pts,
            dxfattribs={
                "layer":      layer_name,
                "true_color": true_color_int,
            },
        )

        # добавляем текстовую подпись у начала маршрута
        label = pair.label or f"Route {idx + 1}"
        msp.add_text(
            label,
            dxfattribs={
                "insert":     pts[0],
                "height":     5.0,
                "layer":      layer_name,
                "true_color": true_color_int,
            },
        )

        exported += 1

    # сохраняем файл по указанному пути
    doc.saveas(path)
    return exported
