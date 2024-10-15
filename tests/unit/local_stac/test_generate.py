from __future__ import annotations

import datetime as dt
from pathlib import Path
from unittest.mock import MagicMock, patch

import pystac
import pytest
from shapely.geometry import Polygon, mapping

from src.local_stac.generate import generate_stac, prepare_stac_item


@pytest.fixture()
def example_polygon() -> Polygon:
    return Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])


@pytest.fixture()
def example_path() -> Path:
    return Path.cwd() / ("fake_cog.tif")


@pytest.fixture()
def example_transform() -> list[float]:
    return [0.1, 0, 0, 0, 0.1, 0]


def test_prepare_stac_item(example_polygon: Polygon, example_path: Path, example_transform: list[float]) -> None:
    # Mocking required data
    id_item = "test-item"
    epsg = 4326
    datetime_str = "2023-09-27T10:00:00Z"
    additional_prop = {"key": {"subkey": "value"}}
    asset_extra_fields = {"field": [{"subfield": "value"}]}

    # Call the function
    item = prepare_stac_item(
        file_path=example_path,
        id_item=id_item,
        geometry=example_polygon,
        epsg=epsg,
        transform=example_transform,
        datetime=datetime_str,
        additional_prop=additional_prop,
        asset_extra_fields=asset_extra_fields,
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
    assert asset.href == example_path.as_posix()
    assert asset.media_type == pystac.MediaType.COG
    assert asset.extra_fields == asset_extra_fields


@pytest.fixture()
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
@patch("pystac.Collection")
def test_generate_stac(
    mock_collection_class: MagicMock,
    mock_catalog_class: MagicMock,
    example_items: list[pystac.Item],
    example_polygon: Polygon,
) -> None:
    # Mocking required data
    start_date = "2023-09-27T00:00:00Z"
    end_date = "2023-09-28T00:00:00Z"
    description = "Test Catalog"

    # Create mock catalog and collection instances
    mock_catalog_instance = mock_catalog_class.return_value
    mock_collection_instance = mock_collection_class.return_value

    # Create mock catalog and collection instances
    mock_catalog_instance = mock_catalog_class.return_value
    mock_collection_instance = mock_collection_class.return_value

    # Call the function
    generate_stac(
        items=example_items,
        geometry=example_polygon,
        start_date=start_date,
        end_date=end_date,
        description=description,
    )

    # Check if Catalog was created with correct parameters
    mock_catalog_class.assert_called_once_with(id="catalog", description=description)

    # Manually verify the extent instead of comparing object instances
    _, called_kwargs = mock_collection_class.call_args
    extent = called_kwargs["extent"]

    # Verify spatial extent
    assert extent.spatial.bboxes[0] == list(example_polygon.bounds)

    # Verify temporal extent
    temporal_extent = extent.temporal.intervals[0]
    assert temporal_extent[0] == dt.datetime.fromisoformat(start_date)
    assert temporal_extent[1] == dt.datetime.fromisoformat(end_date)

    # Check if the collection was added to the catalog
    mock_catalog_instance.add_child.assert_called_once_with(mock_collection_instance)

    # Check if items were added to the collection
    for item in example_items:
        mock_collection_instance.add_item.assert_any_call(item)

    # Check if normalize_and_save was called with the correct arguments
    mock_catalog_instance.normalize_and_save.assert_called_once_with(
        "stac-catalog", catalog_type=pystac.CatalogType.SELF_CONTAINED
    )
