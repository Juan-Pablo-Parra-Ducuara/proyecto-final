
import numpy as np

from detector import ArucoDetector


def create_detector():
    """Crea un detector sin necesidad de conectar la cámara."""
    return ArucoDetector()


def test_orientation_classification():
    detector = create_detector()

    assert detector.classify_orientation(0) == "A"
    assert detector.classify_orientation(90) == "B"
    assert detector.classify_orientation(180) == "C"
    assert detector.classify_orientation(270) == "D"


def test_orientation_tolerance():
    detector = create_detector()

    assert detector.classify_orientation(10) == "A"
    assert detector.classify_orientation(80) == "B"
    assert detector.classify_orientation(190) == "C"
    assert detector.classify_orientation(280) == "D"


def test_invalid_orientation():
    detector = create_detector()

    assert detector.classify_orientation(45) is None
    assert detector.classify_orientation(135) is None


def test_each_marker_has_independent_state():
    detector = create_detector()

    first_time = 100.0

    detector._update_marker_state(1, "A", first_time)
    detector._update_marker_state(2, "C", first_time + 0.5)

    state_1 = detector.states_by_id[1]
    state_2 = detector.states_by_id[2]

    assert state_1["candidate"] == "A"
    assert state_2["candidate"] == "C"

    assert state_1["candidate_since"] == first_time
    assert state_2["candidate_since"] == first_time + 0.5


def test_vote_is_emitted_after_stability():
    detector = create_detector()

    first_time = 100.0

    vote, _ = detector._update_marker_state(
        1, "A", first_time
    )

    assert vote is None

    vote, _ = detector._update_marker_state(
        1, "A", first_time + 1.0
    )

    assert vote is None

    vote, _ = detector._update_marker_state(
        1, "A", first_time + 1.6
    )

    assert vote == "A"


def test_same_vote_is_not_emitted_twice():
    detector = create_detector()

    first_time = 100.0

    detector._update_marker_state(1, "A", first_time)

    vote, _ = detector._update_marker_state(
        1, "A", first_time + 1.6
    )

    assert vote == "A"

    vote, _ = detector._update_marker_state(
        1, "A", first_time + 2.0
    )

    assert vote is None


def test_changed_vote_is_emitted_after_stability():
    detector = create_detector()

    first_time = 100.0

    detector._update_marker_state(1, "A", first_time)

    vote, _ = detector._update_marker_state(
        1, "A", first_time + 1.6
    )

    assert vote == "A"

    detector._update_marker_state(
        1, "B", first_time + 2.0
    )

    vote, _ = detector._update_marker_state(
        1, "B", first_time + 3.6
    )

    assert vote == "B"


def test_invalid_orientation_resets_stability():
    detector = create_detector()

    first_time = 100.0

    detector._update_marker_state(1, "A", first_time)

    detector._update_marker_state(
        1, None, first_time + 1.0
    )

    state = detector.states_by_id[1]

    assert state["candidate"] is None
    assert state["candidate_since"] is None


def test_inactive_marker_is_cleaned():
    detector = create_detector()

    detector._update_marker_state(1, "A", 100.0)

    detector._clean_inactive_states(set(), 111.0)

    assert 1 not in detector.states_by_id
