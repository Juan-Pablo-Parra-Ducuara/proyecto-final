import numpy as np

from detector import QRDetector


def create_detector():
    """Crea un detector sin necesidad de conectar la cámara."""

    return QRDetector()


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


def test_each_qr_has_independent_state():
    detector = create_detector()

    first_time = 100.0

    detector._update_qr_state("token-1", "A", first_time)
    detector._update_qr_state("token-2", "C", first_time + 0.5)

    state_1 = detector.states_by_token["token-1"]
    state_2 = detector.states_by_token["token-2"]

    assert state_1["candidate"] == "A"
    assert state_2["candidate"] == "C"

    assert state_1["candidate_since"] == first_time
    assert state_2["candidate_since"] == first_time + 0.5


def test_vote_is_emitted_after_stability():
    detector = create_detector()

    first_time = 100.0

    vote, _ = detector._update_qr_state(
        "token-1", "A", first_time
    )

    assert vote is None

    vote, _ = detector._update_qr_state(
        "token-1", "A", first_time + 0.4
    )

    assert vote is None

    vote, _ = detector._update_qr_state(
        "token-1", "A", first_time + 0.6
    )

    assert vote == "A"


def test_same_vote_is_not_emitted_twice():
    detector = create_detector()

    first_time = 100.0

    detector._update_qr_state("token-1", "A", first_time)

    vote, _ = detector._update_qr_state(
        "token-1", "A", first_time + 0.6
    )

    assert vote == "A"

    vote, _ = detector._update_qr_state(
        "token-1", "A", first_time + 2.0
    )

    assert vote is None


def test_changed_vote_is_emitted_after_stability():
    detector = create_detector()

    first_time = 100.0

    detector._update_qr_state("token-1", "A", first_time)

    vote, _ = detector._update_qr_state(
        "token-1", "A", first_time + 0.6
    )

    assert vote == "A"

    detector._update_qr_state(
        "token-1", "B", first_time + 1.0
    )

    vote, _ = detector._update_qr_state(
        "token-1", "B", first_time + 1.6
    )

    assert vote == "B"


def test_invalid_orientation_resets_stability():
    detector = create_detector()

    first_time = 100.0

    detector._update_qr_state("token-1", "A", first_time)
    detector._update_qr_state(
        "token-1", None, first_time + 0.4
    )

    state = detector.states_by_token["token-1"]

    assert state["candidate"] is None
    assert state["candidate_since"] is None


def test_inactive_qr_is_cleaned():
    detector = create_detector()

    detector._update_qr_state("token-1", "A", 100.0)
    detector._clean_inactive_states(set(), 111.0)

    assert "token-1" not in detector.states_by_token


def test_reset_allows_sending_again_in_new_session():
    detector = create_detector()

    detector._update_qr_state("token-1", "A", 100.0)
    detector._update_qr_state("token-1", "A", 100.6)

    detector.reset_emitted_votes()

    vote, _ = detector._update_qr_state(
        "token-1", "A", 101.2
    )

    assert vote == "A"


def test_two_qr_are_detected_in_one_frame():
    detector = create_detector()

    token_1 = cv2_qr("token-1")
    token_2 = cv2_qr("token-2")

    frame = np.full((500, 900, 3), 255, dtype=np.uint8)
    frame[100:400, 50:350] = token_1
    frame[100:400, 500:800] = token_2

    detections = detector.detect_qr_codes(frame)

    assert {item["token"] for item in detections} == {
        "token-1",
        "token-2",
    }


def cv2_qr(token):
    """Genera un QR pequeño para armar un fotograma sintético."""

    import cv2

    codigo = cv2.QRCodeEncoder_create().encode(token)
    codigo = cv2.resize(
        codigo,
        (300, 300),
        interpolation=cv2.INTER_NEAREST,
    )

    return cv2.cvtColor(codigo, cv2.COLOR_GRAY2BGR)
