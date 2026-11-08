"""
Generador de tarjetas ArUco para el proyecto Clicker por cámara.
Genera PNG individuales, PDF multipágina y recursos de prueba.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


# ==========================================
# CONFIGURACIÓN
# ==========================================

DPI = 300

MARKER_SIZE_CM = 12.0
WHITE_MARGIN_CM = 2.0
CARD_SIZE_CM = MARKER_SIZE_CM + (WHITE_MARGIN_CM * 2)

MARKER_SIZE_PX = round(MARKER_SIZE_CM / 2.54 * DPI)
CARD_SIZE_PX = round(CARD_SIZE_CM / 2.54 * DPI)

PAPER_SIZES_CM = {
    "A4": (21.0, 29.7),
    "A5": (14.8, 21.0),
}


@dataclass(frozen=True)
class StudentCard:
    """Información de cada estudiante."""

    aruco_id: int
    name: str = ""


# ==========================================
# VARIABLES DE ENTORNO
# ==========================================

def load_project_env():
    """Carga el archivo .env ubicado en la raíz del proyecto."""

    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    project_env = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(project_env, override=False)


# ==========================================
# DICCIONARIO ARUCO
# ==========================================

def get_aruco_dictionary(name=None):
    """Obtiene el diccionario ArUco configurado."""

    dictionary_name = name or os.getenv(
        "ARUCO_DICT",
        "DICT_4X4_50"
    )

    if not hasattr(cv2.aruco, dictionary_name):
        raise ValueError(
            f"Diccionario ArUco no válido: {dictionary_name}. "
            "Ejemplos: DICT_4X4_50, DICT_5X5_100."
        )

    dictionary_constant = getattr(
        cv2.aruco,
        dictionary_name
    )

    dictionary = cv2.aruco.getPredefinedDictionary(
        dictionary_constant
    )

    return dictionary, dictionary_name


def cm_to_pixels(cm):
    """Convierte centímetros a píxeles."""

    return round((cm / 2.54) * DPI)


def validate_marker_id(marker_id, dictionary):
    """Comprueba que el ID exista en el diccionario."""

    capacity = int(dictionary.bytesList.shape[0])

    if (
        not isinstance(marker_id, int)
        or not 0 <= marker_id < capacity
    ):
        raise ValueError(
            f"ID ArUco inválido: {marker_id}. "
            f"El diccionario admite IDs entre 0 y {capacity - 1}."
        )


# ==========================================
# GENERACIÓN DEL MARCADOR
# ==========================================

def generate_marker(marker_id, dictionary):
    """Genera un marcador ArUco de 12 x 12 cm."""

    validate_marker_id(marker_id, dictionary)

    marker = cv2.aruco.generateImageMarker(
        dictionary,
        marker_id,
        MARKER_SIZE_PX
    )

    return marker


# ==========================================
# GENERACIÓN DE LA TARJETA
# ==========================================

def add_orientation_labels(card):
    """Añade las letras A, B, C y D en el margen blanco."""

    result = card.copy()

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 2.2
    thickness = 5
    color = 0

    offset = cm_to_pixels(0.35)
    baseline = cm_to_pixels(1.35)

    right = CARD_SIZE_PX - offset
    bottom = CARD_SIZE_PX - offset

    labels = {
        "A": (offset, baseline),
        "B": (right - cm_to_pixels(0.9), baseline),
        "C": (right - cm_to_pixels(0.9), bottom),
        "D": (offset, bottom),
    }

    for letter, position in labels.items():

        cv2.putText(
            result,
            letter,
            position,
            font,
            font_scale,
            color,
            thickness,
            cv2.LINE_AA
        )

    return result


def generate_card(marker_id, dictionary, labels=True):
    """Genera una tarjeta de 16 x 16 cm."""

    marker = generate_marker(marker_id, dictionary)

    card = np.full(
        (CARD_SIZE_PX, CARD_SIZE_PX),
        255,
        dtype=np.uint8
    )

    start = (CARD_SIZE_PX - MARKER_SIZE_PX) // 2

    card[
        start:start + MARKER_SIZE_PX,
        start:start + MARKER_SIZE_PX
    ] = marker

    if labels:
        return add_orientation_labels(card)

    return card


# ==========================================
# LECTURA DE ESTUDIANTES
# ==========================================

def read_students_csv(csv_path):
    """Lee estudiantes desde un archivo CSV."""

    if not csv_path.is_file():
        raise ValueError(
            f"No existe el archivo CSV: {csv_path}"
        )

    students = []

    with csv_path.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:

        reader = csv.DictReader(file)

        headers = {
            header.strip()
            for header in (reader.fieldnames or [])
        }

        if not {"name", "aruco_id"}.issubset(headers):
            raise ValueError(
                "El CSV debe incluir las columnas "
                "'name' y 'aruco_id'."
            )

        for row_number, row in enumerate(reader, start=2):

            try:
                marker_id = int(
                    (row.get("aruco_id") or "").strip()
                )

            except ValueError as exc:
                raise ValueError(
                    f"ID ArUco inválido en la fila {row_number}."
                ) from exc

            name = (row.get("name") or "").strip()

            if not name:
                raise ValueError(
                    f"Falta el nombre en la fila {row_number}."
                )

            students.append(
                StudentCard(marker_id, name)
            )

    return students


def validate_students(students, dictionary):
    """Valida estudiantes e impide IDs repetidos."""

    if not students:
        raise ValueError(
            "No se recibieron estudiantes ni IDs para generar."
        )

    seen = set()

    for student in students:

        validate_marker_id(
            student.aruco_id,
            dictionary
        )

        if student.aruco_id in seen:
            raise ValueError(
                f"El ID ArUco {student.aruco_id} está repetido."
            )

        seen.add(student.aruco_id)


def safe_filename(value):
    """Convierte nombres en nombres de archivo seguros."""

    normalized = unicodedata.normalize(
        "NFKD",
        value.strip()
    )

    ascii_name = normalized.encode(
        "ascii",
        "ignore"
    ).decode("ascii")

    slug = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        ascii_name
    ).strip("_")

    return slug[:50] or "estudiante"


# ==========================================
# PREPARACIÓN PARA IMPRESIÓN
# ==========================================

def make_print_page(card, paper):
    """Centra la tarjeta en una hoja A4 o A5."""

    page_width_cm, page_height_cm = PAPER_SIZES_CM[paper]

    page_width = cm_to_pixels(page_width_cm)
    page_height = cm_to_pixels(page_height_cm)

    card_image = Image.fromarray(card)

    max_width = page_width - cm_to_pixels(0.5)
    max_height = page_height - cm_to_pixels(0.5)

    scale = min(
        max_width / card_image.width,
        max_height / card_image.height,
        1.0
    )

    if scale < 1.0:

        new_size = (
            round(card_image.width * scale),
            round(card_image.height * scale)
        )

        card_image = card_image.resize(
            new_size,
            Image.Resampling.LANCZOS
        )

    page = Image.new(
        "L",
        (page_width, page_height),
        255
    )

    x = (page_width - card_image.width) // 2
    y = (page_height - card_image.height) // 2

    page.paste(card_image, (x, y))

    return page


# ==========================================
# GUARDAR TARJETAS
# ==========================================

def save_student_cards(
    students,
    dictionary,
    output_dir,
    paper
):
    """Genera PNG individuales y páginas para el PDF."""

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    pages = []
    png_paths = []

    for student in students:

        card = generate_card(
            student.aruco_id,
            dictionary
        )

        suffix = (
            f"_{safe_filename(student.name)}"
            if student.name
            else ""
        )

        png_path = output_dir / (
            f"tarjeta_aruco_id_{student.aruco_id}{suffix}.png"
        )

        Image.fromarray(card).save(
            png_path,
            dpi=(DPI, DPI)
        )

        png_paths.append(png_path)

        pages.append(
            make_print_page(card, paper)
        )

    return pages, png_paths


def save_multipage_pdf(pages, pdf_path):
    """Guarda todas las tarjetas en un PDF multipágina."""

    if not pages:
        raise ValueError(
            "No hay tarjetas para incluir en el PDF."
        )

    pdf_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    pages[0].save(
        pdf_path,
        "PDF",
        resolution=DPI,
        save_all=True,
        append_images=pages[1:]
    )


# ==========================================
# IMÁGENES DE PRUEBA
# ==========================================

def generate_test_assets(marker_id, dictionary, test_dir):
    """Genera cuatro imágenes con diferentes orientaciones."""

    card = generate_card(
        marker_id,
        dictionary,
        labels=False
    )

    rotations = {
        0: card,
        90: cv2.rotate(
            card,
            cv2.ROTATE_90_CLOCKWISE
        ),
        180: cv2.rotate(
            card,
            cv2.ROTATE_180
        ),
        270: cv2.rotate(
            card,
            cv2.ROTATE_90_COUNTERCLOCKWISE
        )
    }

    test_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    paths = []

    for angle, image in rotations.items():

        path = test_dir / (
            f"aruco_id_{marker_id}_rotacion_{angle}.png"
        )

        Image.fromarray(image).save(
            path,
            dpi=(DPI, DPI)
        )

        paths.append(path)

    return paths


# ==========================================
# ARGUMENTOS DE CONSOLA
# ==========================================

def build_parser():

    parser = argparse.ArgumentParser(
        description=(
            "Genera tarjetas ArUco individuales "
            "y un PDF para imprimir."
        )
    )

    source = parser.add_mutually_exclusive_group()

    source.add_argument(
        "--ids",
        nargs="+",
        type=int,
        help="IDs a generar. Ejemplo: --ids 1 2 3 4"
    )

    source.add_argument(
        "--students-csv",
        type=Path,
        help=(
            "CSV con columnas name y aruco_id."
        )
    )

    parser.add_argument(
        "--paper",
        choices=tuple(PAPER_SIZES_CM),
        default="A4"
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("generated_cards")
    )

    parser.add_argument(
        "--test-assets",
        action="store_true",
        help="Genera cuatro imágenes rotadas para pruebas."
    )

    parser.add_argument(
        "--test-id",
        type=int,
        default=0
    )

    parser.add_argument(
        "--dict",
        dest="dictionary_name",
        help="Sobrescribe ARUCO_DICT para esta ejecución."
    )

    return parser


# ==========================================
# PROGRAMA PRINCIPAL
# ==========================================

def main(argv=None):

    load_project_env()

    parser = build_parser()
    args = parser.parse_args(argv)

    try:

        dictionary, dictionary_name = get_aruco_dictionary(
            args.dictionary_name
        )

        students = []

        if args.ids is not None:

            students = [
                StudentCard(marker_id)
                for marker_id in args.ids
            ]

        elif args.students_csv is not None:

            students = read_students_csv(
                args.students_csv
            )

        # Generar tarjetas de estudiantes
        if students:

            validate_students(
                students,
                dictionary
            )

            pages, png_paths = save_student_cards(
                students,
                dictionary,
                args.output_dir,
                args.paper
            )

            pdf_path = (
                args.output_dir /
                f"tarjetas_aruco_{args.paper}.pdf"
            )

            save_multipage_pdf(
                pages,
                pdf_path
            )

            print("\n================================")
            print(" GENERACIÓN DE TARJETAS ARUCO")
            print("================================")

            print(
                f"Diccionario: {dictionary_name}"
            )

            print(
                f"Tarjetas generadas: {len(png_paths)}"
            )

            print(
                f"PDF de impresión: {pdf_path.resolve()}"
            )

            print(
                f"PNGs individuales: {args.output_dir.resolve()}"
            )

            if args.paper == "A5":

                print(
                    "Aviso: en A5 la tarjeta se reduce "
                    "para caber en la hoja; el marcador "
                    "queda de aproximadamente 10,7 cm."
                )

        # Generar recursos de prueba
        if args.test_assets:

            validate_marker_id(
                args.test_id,
                dictionary
            )

            test_dir = (
                Path(__file__).resolve().parent /
                "test_assets"
            )

            paths = generate_test_assets(
                args.test_id,
                dictionary,
                test_dir
            )

            print(
                f"\nRecursos de prueba generados: {len(paths)}"
            )

            for path in paths:
                print(f" - {path}")

        if not students and not args.test_assets:

            parser.error(
                "Indica --ids, --students-csv o --test-assets."
            )

    except (ValueError, OSError) as exc:

        print(
            f"Error: {exc}",
            file=sys.stderr
        )

        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())