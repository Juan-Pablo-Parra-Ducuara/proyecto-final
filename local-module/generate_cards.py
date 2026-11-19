"""
Generador de tarjetas QR para el proyecto Clicker por cámara.

Genera PNG individuales, PDF multipágina y recursos de prueba con los mismos
tokens QR que muestra el microfrontend del estudiante. La rotación de la
tarjeta determina la opción: 0°→A, 90°→B, 180°→C, 270°→D, igual que en el
escáner web y en `detector.py`.
"""

from __future__ import annotations

import argparse
import csv
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

QR_SIZE_CM = 12.0
WHITE_MARGIN_CM = 2.0
CARD_SIZE_CM = QR_SIZE_CM + (WHITE_MARGIN_CM * 2)

QR_SIZE_PX = round(QR_SIZE_CM / 2.54 * DPI)
MARGIN_PX = round(WHITE_MARGIN_CM / 2.54 * DPI)
# La tarjeta se calcula desde el QR para que el margen sea simétrico.
# Un píxel de diferencia rompe la lectura de algunos QR girados 90°.
CARD_SIZE_PX = QR_SIZE_PX + (MARGIN_PX * 2)

PAPER_SIZES_CM = {
    "A4": (21.0, 29.7),
    "A5": (14.8, 21.0),
}

ROTACIONES = {
    0: None,
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


@dataclass(frozen=True)
class StudentCard:
    """Estudiante con el token QR que se imprimirá en su tarjeta."""

    qr_token: str
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
# VALIDACIÓN
# ==========================================

def cm_to_pixels(cm):
    """Convierte centímetros a píxeles."""

    return round((cm / 2.54) * DPI)


def validate_token(token):
    """Comprueba que el token QR no esté vacío."""

    token = str(token or "").strip()

    if not token:
        raise ValueError("El token QR no puede estar vacío.")

    return token


# ==========================================
# GENERACIÓN DEL QR
# ==========================================

def generate_qr(token, rotation=0):
    """Genera un QR de 12 x 12 cm con el token del estudiante."""

    token = validate_token(token)

    if rotation not in ROTACIONES:
        raise ValueError(f"Rotación no válida: {rotation}.")

    encoder = cv2.QRCodeEncoder_create()
    codigo = encoder.encode(token)

    if codigo is None or codigo.size == 0:
        raise ValueError(f"No se pudo generar el QR para '{token}'.")

    if codigo.ndim == 3:
        codigo = cv2.cvtColor(codigo, cv2.COLOR_BGR2GRAY)

    # Se gira antes de escalar: rotar después introduce alias en los módulos.
    if ROTACIONES[rotation] is not None:
        codigo = cv2.rotate(codigo, ROTACIONES[rotation])

    return cv2.resize(
        codigo,
        (QR_SIZE_PX, QR_SIZE_PX),
        interpolation=cv2.INTER_NEAREST,
    )


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
            cv2.LINE_AA,
        )

    return result


def generate_card(token, labels=True, rotation=0):
    """Genera una tarjeta de 16 x 16 cm."""

    codigo = generate_qr(token, rotation=rotation)

    card = np.full(
        (CARD_SIZE_PX, CARD_SIZE_PX),
        255,
        dtype=np.uint8,
    )

    card[
        MARGIN_PX:MARGIN_PX + QR_SIZE_PX,
        MARGIN_PX:MARGIN_PX + QR_SIZE_PX,
    ] = codigo

    if labels:
        return add_orientation_labels(card)

    return card


# ==========================================
# LECTURA DE ESTUDIANTES
# ==========================================

def read_students_csv(csv_path):
    """Lee estudiantes desde un CSV con `qr_token` o `aruco_id`."""

    if not csv_path.is_file():
        raise ValueError(
            f"No existe el archivo CSV: {csv_path}"
        )

    students = []

    with csv_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        reader = csv.DictReader(file)

        headers = {
            header.strip()
            for header in (reader.fieldnames or [])
        }

        if (
            "name" not in headers
            or not {"qr_token", "aruco_id"} & headers
        ):
            raise ValueError(
                "El CSV debe incluir 'name' y 'qr_token' "
                "(o 'aruco_id' como compatibilidad)."
            )

        for row_number, row in enumerate(reader, start=2):

            token = (
                (row.get("qr_token") or "")
                or (row.get("aruco_id") or "")
            ).strip()

            try:
                token = validate_token(token)
            except ValueError as exc:
                raise ValueError(
                    f"Token QR vacío en la fila {row_number}."
                ) from exc

            name = (row.get("name") or "").strip()

            if not name:
                raise ValueError(
                    f"Falta el nombre en la fila {row_number}."
                )

            students.append(
                StudentCard(token, name)
            )

    return students


def validate_students(students):
    """Valida estudiantes e impide tokens repetidos."""

    if not students:
        raise ValueError(
            "No se recibieron estudiantes ni tokens para generar."
        )

    seen = set()

    for student in students:

        token = validate_token(student.qr_token)

        if token in seen:
            raise ValueError(
                f"El token QR {token} está repetido."
            )

        seen.add(token)


def safe_filename(value):
    """Convierte nombres en nombres de archivo seguros."""

    normalized = unicodedata.normalize(
        "NFKD",
        value.strip(),
    )

    ascii_name = normalized.encode(
        "ascii",
        "ignore",
    ).decode("ascii")

    slug = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        ascii_name,
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
        1.0,
    )

    if scale < 1.0:

        new_size = (
            round(card_image.width * scale),
            round(card_image.height * scale),
        )

        card_image = card_image.resize(
            new_size,
            Image.Resampling.LANCZOS,
        )

    page = Image.new(
        "L",
        (page_width, page_height),
        255,
    )

    x = (page_width - card_image.width) // 2
    y = (page_height - card_image.height) // 2

    page.paste(card_image, (x, y))

    return page


# ==========================================
# GUARDAR TARJETAS
# ==========================================

def save_student_cards(students, output_dir, paper):
    """Genera PNG individuales y páginas para el PDF."""

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    pages = []
    png_paths = []

    for student in students:

        card = generate_card(student.qr_token)

        nombre = safe_filename(
            student.name or student.qr_token[:10]
        )
        prefijo = safe_filename(student.qr_token[:8])

        png_path = output_dir / (
            f"tarjeta_{nombre}_{prefijo}.png"
        )

        Image.fromarray(card).save(
            png_path,
            dpi=(DPI, DPI),
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
        exist_ok=True,
    )

    pages[0].save(
        pdf_path,
        "PDF",
        resolution=DPI,
        save_all=True,
        append_images=pages[1:],
    )


# ==========================================
# IMÁGENES DE PRUEBA
# ==========================================

def generate_test_assets(token, test_dir):
    """Genera cuatro imágenes rotadas en el orden A/B/C/D."""

    # Mismo orden que el microfrontend del estudiante y el detector.
    rotations = {
        angulo: generate_card(
            token,
            labels=False,
            rotation=angulo,
        )
        for angulo in ROTACIONES
    }

    test_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    paths = []

    for angle, image in rotations.items():

        path = test_dir / (
            f"qr_rotacion_{angle}.png"
        )

        Image.fromarray(image).save(
            path,
            dpi=(DPI, DPI),
        )

        paths.append(path)

    return paths


# ==========================================
# ARGUMENTOS DE CONSOLA
# ==========================================

def build_parser():

    parser = argparse.ArgumentParser(
        description=(
            "Genera tarjetas QR individuales "
            "y un PDF para imprimir."
        )
    )

    source = parser.add_mutually_exclusive_group()

    source.add_argument(
        "--ids",
        nargs="+",
        type=int,
        help=(
            "Tokens numéricos a generar. "
            "Ejemplo: --ids 1 2 3 4"
        ),
    )

    source.add_argument(
        "--students-csv",
        type=Path,
        help=(
            "CSV con columnas name y qr_token "
            "(o aruco_id)."
        ),
    )

    parser.add_argument(
        "--paper",
        choices=tuple(PAPER_SIZES_CM),
        default="A4",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("generated_cards"),
    )

    parser.add_argument(
        "--test-assets",
        action="store_true",
        help="Genera cuatro imágenes rotadas para pruebas.",
    )

    parser.add_argument(
        "--test-id",
        type=int,
        default=0,
    )

    parser.add_argument(
        "--test-token",
        help="Token QR usado por --test-assets.",
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

        students = []

        if args.ids is not None:

            students = [
                StudentCard(str(marker_id))
                for marker_id in args.ids
            ]

        elif args.students_csv is not None:

            students = read_students_csv(
                args.students_csv
            )

        # Generar tarjetas de estudiantes
        if students:

            validate_students(students)

            pages, png_paths = save_student_cards(
                students,
                args.output_dir,
                args.paper,
            )

            pdf_path = (
                args.output_dir /
                f"tarjetas_qr_{args.paper}.pdf"
            )

            save_multipage_pdf(
                pages,
                pdf_path,
            )

            print("\n================================")
            print("   GENERACIÓN DE TARJETAS QR")
            print("================================")

            print(
                f"Tarjetas generadas: {len(png_paths)}"
            )

            print(
                f"PDF de impresión: {pdf_path.resolve()}"
            )

            print(
                "PNGs individuales: "
                f"{args.output_dir.resolve()}"
            )

            print(
                "Gira la tarjeta 0°/90°/180°/270° "
                "para votar A/B/C/D."
            )

            if args.paper == "A5":

                print(
                    "Aviso: en A5 la tarjeta se reduce "
                    "para caber en la hoja; el QR "
                    "queda de aproximadamente 10,7 cm."
                )

        # Generar recursos de prueba
        if args.test_assets:

            token = args.test_token or str(args.test_id)
            validate_token(token)

            test_dir = (
                Path(__file__).resolve().parent /
                "test_assets"
            )

            paths = generate_test_assets(
                token,
                test_dir,
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
            file=sys.stderr,
        )

        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
