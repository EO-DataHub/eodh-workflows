from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from eodh_workflows.utils.raster import image_to_base64


def _base64_to_image(base64_string: str) -> np.ndarray:  # type: ignore[type-arg]
    img_bytes = base64.b64decode(base64_string)
    img = Image.open(BytesIO(img_bytes))
    return np.array(img)


def test_image_to_base64(tmpdir: Path) -> None:
    # Arrange
    rng = np.random.RandomState(42)
    random_image = rng.randint(0, 256, (100, 100, 3), dtype=np.uint8)
    img_path = Path(tmpdir) / "test_image.png"

    img = Image.fromarray(random_image)
    img.save(img_path)

    # Act
    base64_string = image_to_base64(img_path)

    # Assert
    restored_image = _base64_to_image(base64_string)
    assert np.array_equal(random_image, restored_image), "The restored image does not match the original."
