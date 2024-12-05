from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pystac
import pytest
from shapely.geometry import Polygon, mapping

from src import consts
from src.local_stac.generate import generate_stac, prepare_stac_asset, prepare_stac_item, prepare_thumbnail_asset

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def example_polygon() -> Polygon:
    return Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])


@pytest.fixture
def example_cog_path() -> Path:
    return consts.directories.TESTS_DIR / "data" / "test-raster.tif"


@pytest.fixture
def example_thumbnail_fp() -> Path:
    return consts.directories.TESTS_DIR / "data" / "test-thumbnail.png"


@pytest.fixture
def example_transform() -> list[float]:
    return [0.1, 0, 0, 0, 0.1, 0]


def test_prepare_stac_item(
    example_polygon: Polygon,
    example_cog_path: Path,
    example_thumbnail_fp: Path,
    example_transform: list[float],
) -> None:
    # Mocking required data
    id_item = "test-item"
    epsg = 4326
    datetime_str = "2023-09-27T10:00:00Z"
    additional_prop = {"key": {"subkey": "value"}}
    asset_extra_fields = {"field": [{"subfield": "value"}]}

    # Call the function
    assets = {
        "thumbnail": prepare_thumbnail_asset(example_thumbnail_fp),
        "data": prepare_stac_asset(
            file_path=example_cog_path,
            asset_extra_fields=asset_extra_fields,
        ),
    }

    item = prepare_stac_item(
        id_item=id_item,
        geometry=example_polygon,
        epsg=epsg,
        transform=example_transform,
        datetime=datetime_str,
        additional_prop=additional_prop,
        assets=assets,
    )

    # Assertions for pystac.Item attributes
    assert item.id == id_item
    assert item.geometry == mapping(example_polygon)
    assert item.bbox == example_polygon.bounds
    assert item.datetime == datetime_str
    assert item.properties == additional_prop

    # Check projection extension
    projection = pystac.extensions.projection.ProjectionExtension.ext(item)
    assert projection.epsg == epsg
    assert projection.transform == example_transform

    # Check asset
    assert "data" in item.assets
    asset = item.assets["data"]
    assert asset.href == f"../{example_cog_path.name}"
    assert asset.media_type == pystac.MediaType.COG
    assert asset.extra_fields == asset_extra_fields

    assert "thumbnail" in item.assets
    asset = item.assets["thumbnail"]
    assert asset.href == f"../{example_thumbnail_fp.name}"
    assert asset.media_type == pystac.MediaType.PNG
    assert asset.extra_fields == {
        "size": example_thumbnail_fp.stat().st_size,
    }


@pytest.fixture
def example_items() -> list[pystac.Item]:
    item = pystac.Item(
        id="test-item",
        geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
        bbox=[0, 0, 1, 1],
        datetime="2023-09-27T10:00:00Z",
        properties={},
    )
    return [item]


# Mock pystac.Catalog and pystac.Collection classes using @patch
@patch("pystac.Catalog")
def test_generate_stac(mock_catalog_class: MagicMock, example_items: list[pystac.Item], tmp_path: Path) -> None:
    # Mocking required data
    title = "Test Catalog Title"
    description = "Test Catalog"

    # Create mock catalog instances
    mock_catalog_instance = mock_catalog_class.return_value

    # Create mock catalog instances
    mock_catalog_instance = mock_catalog_class.return_value

    # Call the function
    generate_stac(
        items=example_items,
        title=title,
        description=description,
        output_dir=tmp_path,
    )

    # Check if Catalog was created with correct parameters
    mock_catalog_class.assert_called_once_with(id="catalog", title=title, description=description)

    # Check if items were added to the collection
    for item in example_items:
        mock_catalog_instance.add_item.assert_any_call(item)

    # Check if normalize_and_save was called with the correct arguments
    mock_catalog_instance.normalize_and_save.assert_called_once_with(
        tmp_path.as_posix(), catalog_type=pystac.CatalogType.SELF_CONTAINED
    )
