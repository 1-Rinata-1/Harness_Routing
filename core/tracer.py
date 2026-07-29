# этот модуль запускает трассировку всех пар соединений
# он координирует работу муравьиного алгоритма или дейкстры

from dataclasses import dataclass, field
from typing import Callable, Optional

import networkx as nx

from .aco import ACOParams, ACORouter, CableClass, WireType
from .graph import CableChannelGraph

# цвета для отображения маршрутов в 3d-виде, каждый маршрут получает свой цвет
ROUTE_COLORS = [
    "#ff4444", "#44dd44", "#4488ff", "#ffaa00",
    "#ff44ff", "#22dddd", "#ffff44", "#ff8844",
    "#88ff44", "#aa44ff", "#ff4488", "#44ffaa",
]


# пара соединений: два узла графа, которые нужно соединить проводом
@dataclass
class ConnectionPair:
    source:      int           # id узла-источника
    target:      int           # id узла-цели
    label:       str        = ""   # имя соединения, например "J1-J2"
    cable_class: CableClass = field(default_factory=CableClass)  # тип провода


# результат трассировки одной пары: найденный путь и метрики
@dataclass
class Route:
    pair:      ConnectionPair  # пара соединений для которой найден маршрут
    path:      list[int]       # список id узлов от источника до цели
    positions: list[tuple]     # список 3d-координат точек маршрута
    length:    float = 0.0     # суммарная длина маршрута в мм
    color:     str   = "#ff6600"  # цвет для отображения в интерфейсе


# класс запускает трассировку всех пар через граф каналов
class Tracer:

    def __init__(self, graph: CableChannelGraph, params: ACOParams = None):
        # сохраняем граф каналов и параметры алгоритма
        self.graph = graph
        self.params = params or ACOParams()
        # ссылка на текущий роутер (нужна чтобы можно было его остановить)
        self._router: Optional[ACORouter] = None

    # метод для остановки трассировки снаружи (по кнопке отмены)
    def cancel(self) -> None:
        if self._router is not None:
            self._router.request_stop()

    # главный метод: трассирует все переданные пары соединений
    def route_all(
        self,
        pairs: list[ConnectionPair],
        progress: Callable[[int, int, str], None] = None,
        iter_callback: Callable[[int, int], None] = None,
        algorithm: str = "aco",        # "aco" или "dijkstra"
        aco_fallback: bool = True,     # если aco не нашёл путь, попробовать дейкстру
    ) -> list[Route]:
        # берём networkx-граф для алгоритмов
        g = self.graph.networkx_graph()
        # сбрасываем нагрузку рёбер перед новой трассировкой
        self.graph.reset_loads()

        # создаём роутер только для муравьиного алгоритма
        if algorithm == "aco":
            self._router = ACORouter(g, self.params)
        else:
            self._router = None

        routes: list[Route] = []

        # обходим все пары и находим путь для каждой
        for i, pair in enumerate(pairs):
            # если пришёл сигнал остановки — прерываем цикл
            if self._router is not None and self._router._stop:
                break
            # вызываем коллбэк прогресса если он передан
            if progress:
                progress(i, len(pairs), pair.label)

            path: Optional[list[int]] = None

            if algorithm == "aco" and self._router is not None:
                # запускаем муравьиный алгоритм для текущей пары
                path = self._router.route(
                    pair.source, pair.target,
                    cable=pair.cable_class,
                    iter_callback=iter_callback,
                )
                # если aco не нашёл путь и включён резерв — пробуем дейкстру
                if path is None and aco_fallback:
                    try:
                        path = nx.shortest_path(g, pair.source, pair.target,
                                                weight="weight")
                        print(f"[Дейкстра резерв] {pair.label}: "
                              f"{pair.source}→{pair.target}")
                    except (nx.NetworkXNoPath, nx.NodeNotFound):
                        pass
            else:
                # режим дейкстры: ищем кратчайший путь напрямую
                try:
                    path = nx.shortest_path(g, pair.source, pair.target,
                                            weight="weight")
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    path = None

            # если путь не найден — пропускаем эту пару
            if not path:
                print(f"[Трассировщик] Путь не найден: "
                      f"{pair.label} ({pair.source}→{pair.target})")
                continue

            # регистрируем кабель на рёбрах пути для учёта эмс
            if self._router is not None:
                self._router.register_cable_on_path(path, pair.cable_class)

            # собираем 3d-координаты точек маршрута
            positions = [self.graph.nodes[nid]["pos"] for nid in path]
            # считаем суммарную длину маршрута
            length = sum(
                g[path[j]][path[j + 1]].get("weight", 0.0)
                for j in range(len(path) - 1)
            )
            # назначаем цвет из списка по порядку
            color = ROUTE_COLORS[i % len(ROUTE_COLORS)]
            routes.append(Route(pair=pair, path=path, positions=positions,
                                length=length, color=color))
            # увеличиваем нагрузку на рёбра пройденного пути
            self.graph.increment_load(path)

        # сбрасываем роутер после завершения
        self._router = None
        return routes
