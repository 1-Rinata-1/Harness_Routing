# этот файл описывает граф кабельных каналов
# граф состоит из узлов (точек разветвления) и рёбер (отрезков каналов)

import numpy as np
import networkx as nx


# класс для хранения и управления графом кабельных каналов
class CableChannelGraph:

    def __init__(self):
        # внутри используем граф из библиотеки networkx
        self._g: nx.Graph = nx.Graph()
        # счётчик для генерации уникальных id узлов
        self._next_id: int = 0

    # метод добавляет новый узел в граф по заданным координатам
    def add_node(self, pos) -> int:
        node_id = self._next_id
        self._next_id += 1
        # сохраняем координаты как кортеж из float
        self._g.add_node(node_id, pos=tuple(float(c) for c in pos))
        return node_id

    # метод добавляет ребро между двумя узлами
    def add_edge(self, u: int, v: int) -> None:
        # проверяем что оба узла существуют
        if not (self._g.has_node(u) and self._g.has_node(v)):
            raise ValueError(f"Узлы {u} или {v} не существуют в графе")
        # вычисляем длину ребра как евклидово расстояние
        pos_u = np.array(self._g.nodes[u]["pos"])
        pos_v = np.array(self._g.nodes[v]["pos"])
        length = float(np.linalg.norm(pos_v - pos_u))
        # сохраняем длину как вес ребра, нагрузка изначально 0
        self._g.add_edge(u, v, weight=length, load=0)

    # удаляет узел из графа (рёбра тоже удаляются автоматически)
    def remove_node(self, node_id: int) -> None:
        self._g.remove_node(node_id)

    # удаляет ребро между двумя узлами
    def remove_edge(self, u: int, v: int) -> None:
        self._g.remove_edge(u, v)

    # увеличивает счётчик нагрузки для каждого ребра вдоль маршрута
    def increment_load(self, path: list) -> None:
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            if self._g.has_edge(u, v):
                self._g[u][v]["load"] = self._g[u][v].get("load", 0) + 1

    # сбрасывает нагрузку всех рёбер в 0 (нужно перед новой трассировкой)
    def reset_loads(self) -> None:
        for u, v in self._g.edges():
            self._g[u][v]["load"] = 0

    # проверяет существует ли ребро между двумя узлами
    def has_edge(self, u: int, v: int) -> bool:
        return self._g.has_edge(u, v)

    # свойство для получения словаря узлов
    @property
    def nodes(self):
        return self._g.nodes

    # свойство для получения списка рёбер
    @property
    def edges(self):
        return self._g.edges

    # возвращает внутренний граф networkx (нужен для алгоритмов трассировки)
    def networkx_graph(self) -> nx.Graph:
        return self._g

    # ищет ближайший узел к заданной точке в пространстве
    def find_nearest_node(self, point, tolerance: float = None) -> int | None:
        point = np.array(point, dtype=float)
        best_id = None
        best_dist = float("inf")
        # перебираем все узлы и считаем расстояние до каждого
        for node_id, data in self._g.nodes(data=True):
            dist = float(np.linalg.norm(np.array(data["pos"]) - point))
            if dist < best_dist:
                # если задан порог допуска, проверяем его
                if tolerance is None or dist <= tolerance:
                    best_dist = dist
                    best_id = node_id
        return best_id

    # сохраняет граф в словарь (для записи в json)
    def to_dict(self) -> dict:
        return {
            "next_id": self._next_id,
            # список всех узлов с их координатами
            "nodes": [
                {"id": nid, "pos": list(d["pos"])}
                for nid, d in self._g.nodes(data=True)
            ],
            # список всех рёбер
            "edges": [
                {"u": u, "v": v}
                for u, v in self._g.edges()
            ],
        }

    # загружает граф из словаря (после чтения из json)
    def from_dict(self, data: dict) -> None:
        # очищаем текущий граф перед загрузкой
        self._g.clear()
        self._next_id = data.get("next_id", 0)
        # восстанавливаем узлы
        for n in data["nodes"]:
            self._g.add_node(n["id"], pos=tuple(n["pos"]))
        # восстанавливаем рёбра
        for e in data["edges"]:
            self.add_edge(e["u"], e["v"])
