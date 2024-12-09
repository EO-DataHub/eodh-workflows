from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from src.utils.geom import calculate_geodesic_area


def test_calculate_geodesic_area() -> None:
    polygon = Polygon([(1, 1), (1, -0.6), (-1, -1), (-1, 1), (0.5, 2), (1, 1)])

    area = calculate_geodesic_area(polygon)
    assert area == pytest.approx(56622213363.238686, abs=1e-4)
