from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import generate_cards as cards


def test_marker_has_physical_size_of_12_cm():
    dictionary, _ = cards.get_aruco_dictionary("DICT_4X4_50")
    marker = cards.generate_marker(5, dictionary)

    assert marker.shape == (
        cards.MARKER_SIZE_PX,
        cards.MARKER_SIZE_PX
    )

    assert cards.MARKER_SIZE_PX == round(12 / 2.54 * 300)


def test_card_has_white_margin():
    dictionary, _ = cards.get_aruco_dictionary("DICT_4X4_50")

    card = cards.generate_card(
        5,
        dictionary,
        labels=False
    )

    margin = (
        cards.CARD_SIZE_PX - cards.MARKER_SIZE_PX
    ) // 2

    assert card.shape == (
        cards.CARD_SIZE_PX,
        cards.CARD_SIZE_PX
    )

    assert np.all(card[:margin, :] == 255)
    assert np.all(card[:, :margin] == 255)


def test_invalid_marker_id_is_rejected():
    dictionary, _ = cards.get_aruco_dictionary("DICT_4X4_50")

    with pytest.raises(ValueError, match="ID ArUco inválido"):
        cards.generate_marker(50, dictionary)


def test_duplicate_ids_are_rejected():
    dictionary, _ = cards.get_aruco_dictionary("DICT_4X4_50")

    students = [
        cards.StudentCard(5),
        cards.StudentCard(5)
    ]

    with pytest.raises(ValueError, match="está repetido"):
        cards.validate_students(students, dictionary)


def test_csv_students_are_read(tmp_path: Path):
    csv_path = tmp_path / "estudiantes.csv"

    csv_path.write_text(
        "name,aruco_id\nAna Pérez,1\nLuis,2\n",
        encoding="utf-8"
    )

    students = cards.read_students_csv(csv_path)

    assert len(students) == 2
    assert students[0].aruco_id == 1
    assert students[0].name == "Ana Pérez"
    assert students[1].aruco_id == 2


def test_four_rotated_test_assets_are_created(tmp_path: Path):
    dictionary, _ = cards.get_aruco_dictionary("DICT_4X4_50")

    paths = cards.generate_test_assets(
        5,
        dictionary,
        tmp_path
    )

    assert len(paths) == 4
    assert all(path.is_file() for path in paths)

    expected = {
        "aruco_id_5_rotacion_0.png",
        "aruco_id_5_rotacion_90.png",
        "aruco_id_5_rotacion_180.png",
        "aruco_id_5_rotacion_270.png"
    }

    assert {path.name for path in paths} == expected


def test_print_pages_have_correct_dimensions():
    dictionary, _ = cards.get_aruco_dictionary("DICT_4X4_50")

    card = cards.generate_card(5, dictionary)

    a4 = cards.make_print_page(card, "A4")
    a5 = cards.make_print_page(card, "A5")

    assert a4.size == (
        cards.cm_to_pixels(21),
        cards.cm_to_pixels(29.7)
    )

    assert a5.size == (
        cards.cm_to_pixels(14.8),
        cards.cm_to_pixels(21)
    )


def test_pdf_contains_all_student_cards(tmp_path: Path):
    dictionary, _ = cards.get_aruco_dictionary("DICT_4X4_50")

    students = [
        cards.StudentCard(1, "Ana"),
        cards.StudentCard(2, "Luis")
    ]

    pages, paths = cards.save_student_cards(
        students,
        dictionary,
        tmp_path,
        "A4"
    )

    pdf_path = tmp_path / "tarjetas.pdf"

    cards.save_multipage_pdf(
        pages,
        pdf_path
    )

    assert len(paths) == 2
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
    