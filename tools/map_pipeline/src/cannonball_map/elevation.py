from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import rasterio
from pyproj import Transformer

from cannonball_map.manifest import compute_sha256


@dataclass(frozen=True)
class ElevationMetadata:
    product_id: str
    product_title: str
    product_resolution: str
    raster_crs: str
    horizontal_datum: str
    vertical_datum: str
    elevation_units: str
    artifact_sha256: str


class ElevationSampler:
    def __init__(
        self,
        raster_path: Path,
        metadata: ElevationMetadata,
        source_crs: str,
    ) -> None:
        actual_hash = compute_sha256(raster_path)
        if actual_hash != metadata.artifact_sha256:
            raise ValueError(
                "Elevation raster SHA-256 mismatch: "
                f"lock={metadata.artifact_sha256}, raster={actual_hash}."
            )
        self._dataset = rasterio.open(raster_path)
        actual_crs = self._dataset.crs.to_string() if self._dataset.crs else None
        if actual_crs != metadata.raster_crs:
            self._dataset.close()
            raise ValueError(
                f"Elevation raster CRS mismatch: lock={metadata.raster_crs}, raster={actual_crs}."
            )
        self.metadata = metadata
        self._transform = Transformer.from_crs(source_crs, metadata.raster_crs, always_xy=True)

    def sample(self, x: float, y: float) -> float:
        longitude, latitude = self._transform.transform(x, y)
        value = float(next(self._dataset.sample([(longitude, latitude)]))[0])
        nodata = self._dataset.nodata
        if nodata is not None and value == nodata:
            raise ValueError("Route sample intersects elevation NoData.")
        if not (value == value):
            raise ValueError("Route sample elevation is not finite.")
        return value

    def close(self) -> None:
        self._dataset.close()

    def __enter__(self) -> ElevationSampler:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
