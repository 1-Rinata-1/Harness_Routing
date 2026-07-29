# реализация муравьиного алгоритма оптимизации для трассировки проводов
# также здесь хранится классификация типов проводов и расчёт эмс-совместимости

import random
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import networkx as nx


# перечисление типов проводов по их электромагнитным свойствам
class WireType(Enum):
    POWER     = "Силовой"
    DIGITAL   = "Цифровой"
    ANALOG_LF = "Аналоговый НЧ"
    ANALOG_HF = "Аналоговый ВЧ"


# уровень электромагнитного излучения для каждого типа провода (от 0 до 1)
_EMISSION: dict[WireType, float] = {
    WireType.POWER:     1.0,   # силовые провода излучают сильнее всего
    WireType.DIGITAL:   0.7,
    WireType.ANALOG_HF: 0.5,
    WireType.ANALOG_LF: 0.2,
}

# уровень чувствительности к помехам для каждого типа провода (от 0 до 1)
_SENSITIVITY: dict[WireType, float] = {
    WireType.ANALOG_HF: 1.0,   # высокочастотная аналогика наиболее чувствительна
    WireType.ANALOG_LF: 0.7,
    WireType.DIGITAL:   0.3,
    WireType.POWER:     0.1,
}


# класс описывает характеристики одного провода: тип и наличие экранирования
@dataclass
class CableClass:
    wire_type: WireType = WireType.DIGITAL
    shielded:  bool     = False

    # если провод экранирован, излучение равно нулю
    @property
    def emission_intensity(self) -> float:
        return 0.0 if self.shielded else _EMISSION[self.wire_type]

    # если провод экранирован, чувствительность тоже равна нулю
    @property
    def reception_sensitivity(self) -> float:
        return 0.0 if self.shielded else _SENSITIVITY[self.wire_type]


# вычисляет коэффициент эмс-совместимости двух проводов (от 0 до 1)
# чем ближе к 1, тем совместимее провода
def emc_compatibility(a: CableClass, b: CableClass) -> float:
    # несовместимость = максимальное произведение излучения одного на чувствительность другого
    incompatibility = max(
        a.emission_intensity * b.reception_sensitivity,
        b.emission_intensity * a.reception_sensitivity,
    )
    return 1.0 - incompatibility


# параметры муравьиного алгоритма, можно менять через интерфейс
@dataclass
class ACOParams:
    n_ants:       int   = 30      # количество муравьёв за одну итерацию
    n_iterations: int   = 100     # количество итераций алгоритма
    alpha:        float = 1.0     # степень влияния феромона на выбор пути
    beta:         float = 2.5     # степень влияния эвристики (1/длина ребра)
    rho:          float = 0.15    # скорость испарения феромона за итерацию
    q:            float = 100.0   # количество феромона, откладываемого муравьём
    bundle_bonus: float = 1.5     # бонус за ребро, по которому уже идут другие провода
    tau_min:      float = 0.01    # минимально допустимый уровень феромона
    lambda1:      float = 10.0    # вес критерия длины в целевой функции


# основной класс маршрутизатора, реализующий муравьиный алгоритм
class ACORouter:

    def __init__(self, graph: nx.Graph, params: ACOParams = None):
        # сохраняем граф и параметры
        self._g = graph
        self.p = params or ACOParams()
        # словарь феромонов: ключ — пара узлов, значение — уровень феромона
        self._pheromone:   dict[tuple, float]            = {}
        # словарь кабелей на рёбрах: ключ — ребро, значение — список кабелей
        self._edge_cables: dict[tuple, list[CableClass]] = {}
        # флаг для остановки алгоритма извне
        self._stop: bool = False
        # инициализируем феромон на всех рёбрах
        self._init_pheromone()

    # метод для внешней остановки алгоритма (например по кнопке отмены)
    def request_stop(self) -> None:
        self._stop = True

    # устанавливаем начальный уровень феромона 1.0 на всех рёбрах
    def _init_pheromone(self) -> None:
        for u, v in self._g.edges():
            self._pheromone[(u, v)] = 1.0
            self._pheromone[(v, u)] = 1.0

    # возвращает уровень феромона для ребра u-v
    def _tau(self, u: int, v: int) -> float:
        return self._pheromone.get((u, v), self.p.tau_min)

    # эвристическая оценка ребра: чем короче, тем лучше
    def _eta(self, u: int, v: int) -> float:
        length = self._g[u][v].get("weight", 1.0)
        return 1.0 / max(length, 1e-9)

    # считает эмс-фактор: насколько ребро подходит с точки зрения совместимости
    def _emc_factor(self, u: int, v: int,
                    current: Optional[CableClass]) -> float:
        if current is None:
            return 1.0
        key = (min(u, v), max(u, v))
        cables = self._edge_cables.get(key, [])
        if not cables:
            return 1.0
        # берём минимум из всех совместимостей с уже проложенными кабелями
        return min(emc_compatibility(current, c) for c in cables)

    # итоговая привлекательность ребра с учётом феромона, длины, нагрузки и эмс
    def _attractiveness(self, u: int, v: int,
                        current: Optional[CableClass] = None) -> float:
        load = self._g[u][v].get("load", 0)
        # бонус за совместное прохождение с другими кабелями
        bundle = 1.0 + self.p.bundle_bonus * load
        emc    = self._emc_factor(u, v, current)
        return (self._tau(u, v) ** self.p.alpha) * \
               (self._eta(u, v) ** self.p.beta) * bundle * emc

    # один муравей строит путь от source до target методом рулетки
    def _build_path(self, source: int, target: int,
                    cable: Optional[CableClass] = None) -> Optional[list[int]]:
        current = source
        path    = [current]
        visited = {current}
        # ограничиваем максимальное количество шагов чтобы не зависнуть
        max_steps = self._g.number_of_nodes() * 3

        for _ in range(max_steps):
            if current == target:
                return path

            # собираем соседей, которых ещё не посещали
            candidates, weights = [], []
            for nb in self._g.neighbors(current):
                if nb in visited and nb != target:
                    continue
                a = self._attractiveness(current, nb, cable)
                if a > 0:
                    candidates.append(nb)
                    weights.append(a)

            if not candidates:
                return None

            # выбираем следующий узел методом рулетки (вероятностно)
            total = sum(weights)
            r = random.random() * total
            cumulative_sum, chosen = 0.0, candidates[-1]
            for c, w in zip(candidates, weights):
                cumulative_sum += w
                if r <= cumulative_sum:
                    chosen = c
                    break

            path.append(chosen)
            visited.add(chosen)
            current = chosen

        return path if current == target else None

    # запоминает какой кабель прошёл по каждому ребру пути
    def register_cable_on_path(self, path: list[int],
                                cable: CableClass) -> None:
        for i in range(len(path) - 1):
            key = (min(path[i], path[i + 1]), max(path[i], path[i + 1]))
            self._edge_cables.setdefault(key, []).append(cable)

    # испарение: уменьшаем феромон на всех рёбрах
    def _evaporate(self) -> None:
        for key in self._pheromone:
            self._pheromone[key] = max(
                self._pheromone[key] * (1.0 - self.p.rho),
                self.p.tau_min,
            )

    # откладывание феромона: лучший путь итерации получает больше феромона
    def _deposit(self, path: list[int], cost: float) -> None:
        amount = self.p.q / max(cost, 1e-9)
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            self._pheromone[(u, v)] = self._pheromone.get((u, v), 0.0) + amount
            self._pheromone[(v, u)] = self._pheromone.get((v, u), 0.0) + amount

    # считает суммарную длину пути
    @staticmethod
    def _path_cost(g: nx.Graph, path: list[int]) -> float:
        return sum(
            g[path[i]][path[i + 1]].get("weight", 1.0)
            for i in range(len(path) - 1)
        )

    # главный метод: запускает алгоритм и возвращает лучший найденный путь
    def route(self, source: int, target: int,
              cable: Optional[CableClass] = None,
              iter_callback=None) -> Optional[list[int]]:
        # если начало и конец совпадают, путь тривиален
        if source == target:
            return [source]
        # если хотя бы одного узла нет в графе, путь невозможен
        if not (self._g.has_node(source) and self._g.has_node(target)):
            return None

        best_path: Optional[list[int]] = None
        best_cost = float("inf")

        for t in range(self.p.n_iterations):
            # проверяем флаг остановки перед каждой итерацией
            if self._stop:
                break
            if iter_callback:
                iter_callback(t + 1, self.p.n_iterations)

            iter_best: Optional[list[int]] = None
            iter_cost = float("inf")

            # каждый муравей строит свой путь
            for _ in range(self.p.n_ants):
                path = self._build_path(source, target, cable)
                if path and path[-1] == target:
                    cost = self._path_cost(self._g, path)
                    if cost < iter_cost:
                        iter_cost = cost
                        iter_best = path

            # испаряем феромон и откладываем на лучшем пути итерации
            self._evaporate()
            if iter_best:
                self._deposit(iter_best, iter_cost)
                if iter_cost < best_cost:
                    best_cost = iter_cost
                    best_path = iter_best

        return best_path
