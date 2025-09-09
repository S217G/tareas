# -*- coding: utf-8 -*-
"""
laser_nuevo.py — Genera G-code a partir de imagen y lo envía a GRBL.
Incluye modos dither/grayscale/threshold, M4 dinámico y overscan.
"""

import time
from typing import Iterable, Tuple

from PIL import Image, ImageOps
import serial

# ===================== Utilidades serie/GRBL =====================

WAKE_DELAY = 2.0  # s


def open_serial(port: str, baud: int = 115200, timeout: float = 1.0) -> serial.Serial:
    ser = serial.Serial(port, baudrate=baud, timeout=timeout)
    ser.write(b"\r\n\r\n")
    time.sleep(WAKE_DELAY)
    ser.reset_input_buffer()
    return ser


def _readline(ser: serial.Serial) -> str:
    raw = ser.readline()
    return raw.decode(errors="ignore").strip() if raw else ""


def send_cmd(ser: serial.Serial, cmd: str) -> str:
    """Envía una línea y espera 'ok' / 'error' / 'ALARM'."""
    cmd = cmd.strip()
    if not cmd:
        return "ok"
    ser.write((cmd + "\n").encode())
    while True:
        line = _readline(ser)
        if not line:
            continue
        # print(f"<< {line}")  # descomenta para depurar
        L = line.lower()
        if line == "ok" or L.startswith("error") or line.upper().startswith("ALARM"):
            return line


# ===================== Procesado de imagen =====================

def mm_per_pixel(ppmm: float) -> float:
    return 1.0 / float(ppmm)


def to_grayscale(img: Image.Image, invert: bool) -> Image.Image:
    g = ImageOps.grayscale(img)
    if invert:
        g = ImageOps.invert(g)
    return g


def floyd_dither(img: Image.Image, invert: bool) -> Image.Image:
    g = to_grayscale(img, invert)
    return g.convert("1")  # FS dithering


def prepare_image(path: str,
                  size_mm: Tuple[float, float],
                  ppmm: float,
                  invert: bool,
                  mode: str) -> Image.Image:
    """
    Abre y redimensiona EXACTAMENTE al tamaño objetivo (mm * ppmm), sin letterbox.
    Soporta:
      - 'threshold': umbral fijo (B/N puro) — ideal para ArUco
      - 'dither'   : B/N con dithering FS
      - 'grayscale': escala de grises
    """
    w_mm, h_mm = size_mm
    target_px = (int(round(w_mm * ppmm)), int(round(h_mm * ppmm)))

    # Cargar en L (grises) para poder umbralizar si hace falta
    img = Image.open(path).convert("L")
    img = img.resize(target_px, Image.Resampling.LANCZOS)

    if mode == "threshold":
        # Si invert=True, invierte antes del umbral
        if invert:
            img = ImageOps.invert(img)
        # Umbral fijo a 128 (ajústalo si lo necesitas)
        bw = img.point(lambda p: 0 if p < 128 else 255, "1")
        return bw

    if mode == "dither":
        return floyd_dither(img.convert("RGB"), invert)

    # grayscale
    return to_grayscale(img.convert("RGB"), invert)


def gamma_correct(v: float, gamma: float) -> float:
    return pow(max(0.0, min(1.0, v)), gamma)


def raster_to_gcode(
    img: Image.Image,
    *,
    ppmm: float,
    origin: Tuple[float, float],
    f_engrave: float,
    f_travel: float,
    s_max: int,
    mode: str,
    gamma_val: float,
) -> Iterable[str]:
    """
    Raster serpenteado (bidireccional) en G90.
    - Usa M4 (dinámico) para evitar oscurecer en aceleraciones.
    - Overscan en cada línea con láser apagado para bordes limpios.
    - En 'threshold' y 'dither' se tratan como binario (S fijo para negro).
    """
    px_w, px_h = img.size
    step = mm_per_pixel(ppmm)
    ox, oy = origin

    OVERSCAN_MM = 0.6           # <== ajusta 0.4–1.0 según inercias
    S_FIXED = s_max             # potencia para negro en binario (threshold/dither)

    # Cabecera
    yield ";; --- BEGIN ---"
    yield "G21"
    yield "G90"
    yield "M5"
    yield f"F{f_travel:.4f}"

    for row in range(px_h):
        y_mm = oy + (px_h - 1 - row) * step

        # Dirección serpenteada
        if row % 2 == 0:
            x_range = range(0, px_w)
        else:
            x_range = range(px_w - 1, -1, -1)

        # Inicio de fila con overscan (láser off)
        first_x = x_range.start if isinstance(x_range, range) else x_range[0]
        x0_mm = ox + first_x * step
        yield f"G0 X{(x0_mm - OVERSCAN_MM):.4f} Y{y_mm:.4f}"
        yield f"F{f_engrave:.4f}"

        def pixel_intensity(col: int) -> float:
            if img.mode == "1":
                return 1.0 if img.getpixel((col, row)) == 0 else 0.0  # 0=negro
            else:
                return (255 - img.getpixel((col, row))) / 255.0

        seg_start = None
        seg_power = None

        
        for x in x_range:
            inten = pixel_intensity(x)

            if mode == "grayscale":
                # Potencia por píxel con gamma y S mínimo
                p = gamma_correct(inten, gamma_val)
                s_val = int(round(p * s_max))
                if s_val > 0 and s_val < 50:
                    s_val = 50

                if s_val > 0:
                    # Si veníamos apagados, iniciamos tramo
                    if seg_start is None:
                        seg_start = x
                        seg_power = None  # fuerza actualización la primera vez
                    # Actualiza potencia solo cuando cambia
                    if seg_power != s_val:
                        yield f"M4 S{s_val}"
                        seg_power = s_val
                    # Avanza hasta este píxel
                    x_mm = ox + x * step
                    yield f"G1 X{x_mm:.4f} Y{y_mm:.4f}"
                else:
                    # Cierre de tramo si veníamos encendidos
                    if seg_start is not None:
                        x_mm = ox + x * step
                        # remate + overscan de salida con láser en el último S
                        yield f"G1 X{(x_mm + OVERSCAN_MM):.4f} Y{y_mm:.4f}"
                        yield "M5"
                        seg_start = None
                        seg_power = None

            else:  # threshold/dither (binario)
                if inten > 0.5:
                    if seg_start is None:
                        seg_start = x
                else:
                    if seg_start is not None:
                        x_mm = ox + x * step
                        yield f"M4 S{S_FIXED}"
                        yield f"G1 X{x_mm:.4f} Y{y_mm:.4f}"
                        yield f"G1 X{(x_mm + OVERSCAN_MM):.4f} Y{y_mm:.4f}"
                        yield "M5"
                        seg_start = None



        # Cerrar segmento al final de la fila
        last_x = x_range[-1] if hasattr(x_range, "__getitem__") else (
            x_range.stop - 1 if x_range.step > 0 else x_range.stop + 1
        )
        end_x_mm = ox + last_x * step
        if seg_start is not None:
            if mode == "grayscale":
                yield f"M4 S{seg_power if seg_power is not None else s_max}"
            else:
                yield f"M4 S{S_FIXED}"
            yield f"G1 X{end_x_mm:.4f} Y{y_mm:.4f}"
            yield f"G1 X{(end_x_mm + OVERSCAN_MM):.4f} Y{y_mm:.4f}"
            yield "M5"

        # Feed de viaje para salto a la siguiente fila
        yield f"F{f_travel:.4f}"

    yield "M5"
    yield ";; --- END ---"


# ===================== Envío del G-code =====================

def stream_to_grbl(ser: serial.Serial, gcode_text: str) -> int:
    # Preparación básica
    send_cmd(ser, "$X")   # desbloquear si hay alarma
    send_cmd(ser, "G21")
    send_cmd(ser, "G90")

    errors = 0
    for raw in gcode_text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        resp = send_cmd(ser, line)
        if resp != "ok":
            errors += 1
            # print(f"[ABORT] {line} -> {resp}")
            send_cmd(ser, "M5")
            break

    send_cmd(ser, "M5")
    return 0 if errors == 0 else 2


# ===================== Movimientos previos / retorno =====================

def move_to_offset_and_set_origin(ser: serial.Serial, dx: float = 0.0, dy: float = 0.0, feed: int = 1000):
    """
    Mueve en RELATIVO (G91) hasta (dx,dy) a F=<feed> y fija ese punto
    como origen temporal (G92 X0 Y0). Evita usar $J para no entrar a Jog.
    """
    send_cmd(ser, "G90")
    send_cmd(ser, "G91")
    parts = []
    if abs(dx) > 0: parts.append(f"X{dx}")
    if abs(dy) > 0: parts.append(f"Y{dy}")
    if parts:
        send_cmd(ser, f"G1 {' '.join(parts)} F{int(feed)}")
    send_cmd(ser, "G90")
    send_cmd(ser, "G92 X0 Y0")


def move_back_to_machine_origin(ser: serial.Serial):
    """
    Limpia offsets G92 y retorna al origen de MÁQUINA (G53 G0 X0 Y0).
    Requiere $22=1 y haber hecho homing ($H).
    """
    send_cmd(ser, "G92.1")
    send_cmd(ser, "G90")
    send_cmd(ser, "G53 G0 X0 Y0")


# ===================== Orquestación (generación) =====================

def generate_gcode_text(*,
                        image_path: str,
                        size_mm: Tuple[float, float],
                        ppmm: float,
                        mode: str,
                        invert: bool,
                        gamma_val: float,
                        origin_xy: Tuple[float, float],
                        f_engrave: float,
                        f_travel: float,
                        s_max: int) -> str:
    img = prepare_image(image_path, size_mm, ppmm, invert, mode)
    lines = list(
        raster_to_gcode(
            img,
            ppmm=ppmm,
            origin=origin_xy,
            f_engrave=f_engrave,
            f_travel=f_travel,
            s_max=s_max,
            mode=mode,
            gamma_val=gamma_val,
        )
    )
    return "\n".join(lines) + "\n"
