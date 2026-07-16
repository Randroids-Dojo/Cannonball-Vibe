from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cannonball_map.acquisition import acquire_nhpn


class FakeArcGis:
    def __init__(
        self,
        *,
        fail_once: bool = False,
        missing: int | None = None,
        duplicate: int | None = None,
    ) -> None:
        self.fail_once = fail_once
        self.missing = missing
        self.duplicate = duplicate
        self.calls: list[dict[str, str]] = []

    def post(self, _url: str, form: dict[str, str]) -> dict[str, Any]:
        self.calls.append(form)
        if form.get("returnCountOnly") == "true":
            return {"count": 5}
        if form.get("returnIdsOnly") == "true":
            return {"objectIdFieldName": "OBJECTID", "objectIds": [5, 2, 4, 1, 3]}
        if self.fail_once:
            self.fail_once = False
            raise OSError("transient")
        ids = [int(value) for value in form["objectIds"].split(",")]
        if self.missing in ids:
            ids.remove(self.missing)
        features = [
                {"attributes": {"OBJECTID": value}, "geometry": {"paths": []}}
                for value in ids
            ]
        if self.duplicate in ids:
            duplicate = next(
                feature
                for feature in features
                if feature["attributes"]["OBJECTID"] == self.duplicate
            )
            features.append(duplicate)
        return {"features": features}


def test_nhpn_acquisition_retries_pages_and_resumes(tmp_path: Path) -> None:
    transport = FakeArcGis(fail_once=True)
    result = acquire_nhpn(
        transport,
        "https://example.gov/query",
        {"where": "1=1"},
        tmp_path,
        page_size=2,
        sleep=lambda _: None,
    )

    assert result.object_ids == (1, 2, 3, 4, 5)
    assert [feature["attributes"]["OBJECTID"] for feature in result.features] == [1, 2, 3, 4, 5]
    assert result.retries == 1
    assert result.resumed_pages == 0

    replay = FakeArcGis()
    resumed = acquire_nhpn(
        replay,
        "https://example.gov/query",
        {"where": "1=1"},
        tmp_path,
        page_size=2,
        sleep=lambda _: None,
    )
    assert resumed.resumed_pages == 3
    assert len(replay.calls) == 2

    changed_query = FakeArcGis()
    changed = acquire_nhpn(
        changed_query,
        "https://example.gov/query",
        {"where": "STATUS=1"},
        tmp_path,
        page_size=2,
        sleep=lambda _: None,
    )
    assert changed.resumed_pages == 0
    assert len(changed_query.calls) == 5


def test_nhpn_acquisition_deduplicates_identical_features(tmp_path: Path) -> None:
    result = acquire_nhpn(
        FakeArcGis(duplicate=3),
        "https://example.gov/query",
        {"where": "1=1"},
        tmp_path,
        page_size=2,
        sleep=lambda _: None,
    )
    assert len(result.features) == 5


def test_nhpn_acquisition_fails_count_reconciliation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="complete locked ID slice"):
        acquire_nhpn(
            FakeArcGis(missing=3),
            "https://example.gov/query",
            {"where": "1=1"},
            tmp_path,
            page_size=2,
            sleep=lambda _: None,
        )

    recovered = acquire_nhpn(
        FakeArcGis(),
        "https://example.gov/query",
        {"where": "1=1"},
        tmp_path,
        page_size=2,
        sleep=lambda _: None,
    )
    assert len(recovered.features) == 5
