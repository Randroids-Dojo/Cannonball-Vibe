from __future__ import annotations

import pytest

from .test_camera_handling import _assert_completed_chase_cast


def _completed_cast_fixture() -> dict:
    return {
        "spring_cast_ready": True,
        "spring_observation_epoch": 2,
        "spring_cast_epoch": 2,
        "spring_cast_generation": 5,
        "spring_cast_physics_frame": 8,
        "spring_observation_physics_frame": 9,
        "spring_arm_instance_id": "42",
        "spring_cast_arm_instance_id": "42",
        "spring_cast_request_m": 7.50184917449951,
        "spring_cast_hit_m": 7.50184917449951,
        "spring_cast_compression_m": 0.0,
        "spring_length_m": 7.50158739089966,
        "spring_hit_length_m": 7.50184917449951,
    }


def test_completed_cast_accepts_the_pair_after_request_shrink() -> None:
    state = _completed_cast_fixture()
    assert state["spring_hit_length_m"] > state["spring_length_m"]
    _assert_completed_chase_cast(state)


def test_completed_cast_accepts_real_compression_and_explicit_paused_age() -> None:
    state = _completed_cast_fixture()
    state.update(
        spring_cast_request_m=7.5,
        spring_cast_hit_m=2.5,
        spring_cast_compression_m=5.0,
        spring_observation_physics_frame=100,
    )
    _assert_completed_chase_cast(state)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("spring_cast_ready", False),
        ("spring_cast_ready", 1),
        ("spring_cast_epoch", 1),
        ("spring_cast_generation", 0),
        ("spring_cast_generation", True),
        ("spring_cast_physics_frame", 10),
        ("spring_cast_physics_frame", -1),
        ("spring_cast_physics_frame", True),
        ("spring_observation_epoch", -1),
        ("spring_cast_arm_instance_id", "43"),
        ("spring_cast_arm_instance_id", ""),
        ("spring_cast_arm_instance_id", 42),
        ("spring_cast_request_m", float("nan")),
        ("spring_cast_hit_m", float("nan")),
        ("spring_cast_compression_m", float("inf")),
        ("spring_cast_hit_m", -0.001),
        ("spring_cast_hit_m", 7.50185),
        ("spring_cast_compression_m", 0.001),
        ("spring_cast_request_m", True),
    ],
)
def test_completed_cast_rejects_stale_or_invalid_observations(field: str, value) -> None:
    state = _completed_cast_fixture()
    state[field] = value
    with pytest.raises(AssertionError):
        _assert_completed_chase_cast(state)


@pytest.mark.parametrize(
    "field",
    [
        field
        for field in _completed_cast_fixture()
        if field not in ("spring_length_m", "spring_hit_length_m")
    ],
)
def test_completed_cast_requires_every_pair_and_generation_field(field: str) -> None:
    state = _completed_cast_fixture()
    del state[field]
    with pytest.raises(KeyError):
        _assert_completed_chase_cast(state)


def test_completed_cast_rejects_a_never_entered_zero_epoch() -> None:
    state = _completed_cast_fixture()
    state.update(spring_cast_epoch=0, spring_observation_epoch=0)
    with pytest.raises(AssertionError):
        _assert_completed_chase_cast(state)
