from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

import detector as detector_module
import generate_cards as cards
from detector import QRDetector


TOKEN = "token-prueba-seguro"


def test_qr_has_physical_size_of_12_cm():
    codigo = cards.generate_qr(TOKEN)

    assert codigo.shape == (
        cards.QR_SIZE_PX,
        cards.QR_SIZE_PX,
    )

    assert cards.QR_SIZE_PX == round(12 / 2.54 * 300)


def test_card_has_white_margin():
    card = cards.generate_card(TOKEN, labels=False)

    margin = (
        cards.CARD_SIZE_PX - cards.QR_SIZE_PX
    ) // 2

    assert card.shape == (
        cards.CARD_SIZE_PX,
        cards.CARD_SIZE_PX,
    )

    assert np.all(card[:margin, :] == 255)
    assert np.all(card[:, :margin] == 255)


def test_empty_token_is_rejected():
    with pytest.raises(ValueError, match="no puede estar vacío"):
        cards.generate_qr("   ")


def test_duplicate_tokens_are_rejected():
    students = [
        cards.StudentCard(TOKEN),
        cards.StudentCard(TOKEN),
    ]

    with pytest.raises(ValueError, match="está repetido"):
        cards.validate_students(students)


def test_generated_qr_is_decoded_by_detector():
    card = cards.generate_card(TOKEN)
    detector = QRDetector()

    detections = detector.detect_qr_codes(card)

    assert TOKEN in {item["token"] for item in detections}


def test_csv_students_are_read(tmp_path: Path):
    csv_path = tmp_path / "estudiantes.csv"

    csv_path.write_text(
        "name,qr_token,aruco_id\n"
        "Ana Pérez,token-ana,1\n"
        "Luis,token-luis,2\n",
        encoding="utf-8",
    )

    students = cards.read_students_csv(csv_path)

    assert len(students) == 2
    assert students[0].qr_token == "token-ana"
    assert students[0].name == "Ana Pérez"
    assert students[1].qr_token == "token-luis"


def test_csv_falls_back_to_aruco_id(tmp_path: Path):
    csv_path = tmp_path / "estudiantes.csv"

    csv_path.write_text(
        "name,aruco_id\nAna,7\n",
        encoding="utf-8",
    )

    students = cards.read_students_csv(csv_path)

    assert students[0].qr_token == "7"


def test_four_rotated_test_assets_are_created(tmp_path: Path):
    paths = cards.generate_test_assets(TOKEN, tmp_path)

    assert len(paths) == 4
    assert all(path.is_file() for path in paths)

    expected = {
        "qr_rotacion_0.png",
        "qr_rotacion_90.png",
        "qr_rotacion_180.png",
        "qr_rotacion_270.png",
    }

    assert {path.name for path in paths} == expected


def test_rotations_map_to_abc_like_web(tmp_path: Path):
    """Las cuatro imágenes de prueba producen A, B, C y D."""

    paths = cards.generate_test_assets(TOKEN, tmp_path)

    reloj = {"hora": 100.0}

    def monotonic():
        reloj["hora"] += 0.1
        return reloj["hora"]

    detector_module.time = SimpleNamespace(
        monotonic=monotonic
    )

    esperado = {
        "qr_rotacion_0.png": "A",
        "qr_rotacion_90.png": "B",
        "qr_rotacion_180.png": "C",
        "qr_rotacion_270.png": "D",
    }

    try:
        for path in paths:
            detector = QRDetector()
            frame = cv2.imread(str(path))

            votos = []
            for _ in range(12):
                votos += detector.detect_votes(frame)

            assert votos == [(TOKEN, esperado[path.name])]
    finally:
        import time

        detector_module.time = time


def test_print_pages_have_correct_dimensions():
    card = cards.generate_card(TOKEN)

    a4 = cards.make_print_page(card, "A4")
    a5 = cards.make_print_page(card, "A5")

    assert a4.size == (
        cards.cm_to_pixels(21),
        cards.cm_to_pixels(29.7),
    )

    assert a5.size == (
        cards.cm_to_pixels(14.8),
        cards.cm_to_pixels(21),
    )


def test_pdf_contains_all_student_cards(tmp_path: Path):
    students = [
        cards.StudentCard("token-ana", "Ana"),
        cards.StudentCard("token-luis", "Luis"),
    ]

    pages, paths = cards.save_student_cards(
        students,
        tmp_path,
        "A4",
    )

    pdf_path = tmp_path / "tarjetas.pdf"

    cards.save_multipage_pdf(
        pages,
        pdf_path,
    )

    assert len(paths) == 2
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
