from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import pyproj
import pytest
import rasterio
from rasterio import CRS, DatasetReader
from rasterio.features import shapes
from rasterio.transform import from_origin
from shapely.geometry.geo import shape
from shapely.geometry.multipolygon import MultiPolygon
from shapely.geometry.polygon import Polygon
from shapely.ops import transform

from eodh_workflows.utils.logging import get_logger
from eodh_workflows.workflows.legacy.raster.clip import clip_raster

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from affine import Affine

_logger = get_logger(__name__)


@pytest.fixture
def dummy_large_raster(tmp_path: Path) -> Generator[tuple[Path, dict[str, Any]]]:
    """Creates a large raster file with specified dimensions and a dummy AOI."""
    raster_fp = tmp_path / "large_test_raster.tif"
    aoi = {
        "type": "Polygon",
        "coordinates": [
            [
                [14.898945373329379, 50.880263263046096],
                [14.872173344124963, 50.888433380175378],
                [14.860468363914659, 50.893146257566649],
                [14.851751889289963, 50.899193751570706],
                [14.85100476289356, 50.906496820673375],
                [14.858476026857582, 50.912778114130944],
                [14.868313191076879, 50.915996948510198],
                [14.876033497173044, 50.92439627254322],
                [14.886368745656608, 50.931852345662328],
                [14.912642690596753, 50.932244737457609],
                [14.928705908119408, 50.926280024894041],
                [14.935554566753098, 50.91882305855497],
                [14.928830429185478, 50.915211887482066],
                [14.924596712939197, 50.913798744257306],
                [14.927709739590874, 50.912464069589127],
                [14.927211655326603, 50.911678948963861],
                [14.92272889694819, 50.910108667981142],
                [14.923226981212453, 50.909244990859385],
                [14.944769125642061, 50.900214679566382],
                [14.941158014726115, 50.897701585773028],
                [14.925468360401663, 50.894245860344043],
                [14.914759548719896, 50.88827627604973],
                [14.898945373329379, 50.880263263046096],
            ]
        ],
    }

    # Set raster parameters
    width = 1972
    height = 1698
    pixel_size_x = 0.0001466649985548684754
    pixel_size_y = -9.165600994265332702e-05
    origin_x = 14.7630787570352275
    origin_y = 50.9892007192024437

    # Create transform
    transform = from_origin(origin_x, origin_y, pixel_size_x, -pixel_size_y)

    # Create the raster dataset
    new_dataset = rasterio.open(
        raster_fp,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=rasterio.float64,
        crs="EPSG:4326",
        transform=transform,
    )

    # Fill raster with random values
    rng = np.random.RandomState()
    array = rng.random((height, width)).astype(np.float32)
    new_dataset.write(array, 1)
    new_dataset.close()

    yield raster_fp, aoi  # noqa: PT022


def _assert_expected_overlap(
    clipped_data: np.ndarray,  # type: ignore[type-arg]
    raster_transform: Affine,
    crs: CRS,
    aoi: dict[str, Any],
    overlap_threshold: float = 99,
) -> None:
    # Convert to binary mask
    binary_mask = clipped_data > 0  # You can adjust this based on real data

    # Vectorize the mask
    mask_shapes = shapes(binary_mask.astype(np.uint8), transform=raster_transform)
    vectors = [shape(geom) for geom, val in mask_shapes if val == 1]

    # Combine all shapes into a MultiPolygon
    vectorized_polygon = MultiPolygon([geom for geom in vectors if isinstance(geom, Polygon)])

    # Reproject AOI to match raster CRS
    project = pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
    aoi_reprojected = transform(project, shape(aoi))

    # Calculate the intersection area and the area of the AOI
    intersection_area = vectorized_polygon.intersection(aoi_reprojected).area
    aoi_area = aoi_reprojected.area

    # Calculate the percentage of overlap
    overlap_percentage = (intersection_area / aoi_area) * 100

    # Assert that the overlap is at least 99%
    assert overlap_percentage >= overlap_threshold, f"Overlap is less than {overlap_threshold}%: {overlap_percentage}%"


def test_clip_raster_and_vectorize(dummy_large_raster: tuple[Path, dict[str, Any]], tmp_path: Path) -> None:
    """Test clipping raster and verifying the resulting polygon is close to the AOI."""
    # Arrange
    raster_fp, aoi = dummy_large_raster
    expected_overlap_percent = 99

    # Act
    output_fp = clip_raster(fp=raster_fp, aoi=aoi, output_dir=tmp_path)

    # Assert
    assert output_fp.exists(), "Output file should exist"
    assert output_fp.suffix == ".tif", "Output file should be a TIFF"

    src: DatasetReader
    with rasterio.open(output_fp) as src:
        clipped_data = src.read(1)

        assert not np.isnan(clipped_data).all(), "The output data should not be completely NaN"
        assert clipped_data.shape[0] > 0, "The output should have a non-zero shape"
        assert clipped_data.shape[1] > 0, "The output should have a non-zero shape"

        _assert_expected_overlap(
            clipped_data=clipped_data,
            raster_transform=src.transform,
            crs=src.crs,
            aoi=aoi,
            overlap_threshold=expected_overlap_percent,
        )
