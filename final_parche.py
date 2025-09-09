# -*- coding: utf-8 -*-
# final_profiled.py — Ejecutable principal con perfiles rápidos

from laser_nuevo_parche import (
    generate_gcode_text,
    open_serial,
    stream_to_grbl,
    move_to_offset_and_set_origin,  # mueve a (dx,dy) y fija G92 en ese punto
    move_back_to_machine_origin,     # vuelve a X0 Y0 de máquina con G53
)

# === Perfiles rápidos ===
PROFILE = "photo"  # "aruco" o "photo"

if PROFILE == "aruco":
    MODE = "threshold"   # binario para bordes nítidos (ideal ArUco)
    PPMM = 5             # 5 px/mm ≈ 0.2 mm por píxel
    GAMMA = 0.7          # no afecta threshold, se deja por coherencia
    S_MAX = 480          # ajusta según $30; si queda claro, sube a 550–600
    F_ENGRAVE = 1500     # feed típico madera
elif PROFILE == "photo":
    MODE = "grayscale"   # tonos continuos (usa el parche por píxel)
    PPMM = 5
    GAMMA = 0.6          # baja a 0.6 si sigue claro
    S_MAX = 600         # sube a 550–600 si queda gris
    F_ENGRAVE = 1000
else:
    raise ValueError("PROFILE debe ser 'aruco' o 'photo'")

# -------------------- CONFIGURACIÓN FIJA --------------------
PORT = "COM3"                      # Puerto serie (ej: COM3 en Windows)
BAUD = 115200                      # Baudrate
SIZE_MM = (20, 20)                 # Tamaño físico del grabado (ancho, alto) en mm
IMAGE_PATH = r"C:\Users\mipil\OneDrive\Escritorio\imagen\aru.png"  # Ruta a la imagen
INVERT = False                     # True para invertir tonos antes de convertir
F_TRAVEL = 1000                    # Velocidad de viaje (mm/min)

# Offset donde quieres empezar a imprimir (en mm) y feed constante de movimiento previo
OFFSET_DX = 270                    # Ajusta a gusto (+X a la derecha)
OFFSET_DY = -170                   # Ajusta a gusto (-Y hacia abajo, según tu máquina)
OFFSET_FEED = 1000                 # SIEMPRE F1000 como pediste
# ------------------------------------------------------------


def main():
    print("[1/4] Generando G-code...")
    # Importante: el G-code se genera con origen (0,0). Luego lo desplazamos con G92 en máquina.
    gcode = generate_gcode_text(
        image_path=IMAGE_PATH,
        size_mm=SIZE_MM,
        ppmm=PPMM,
        mode=MODE,
        invert=INVERT,
        gamma_val=GAMMA,
        origin_xy=(0.0, 0.0),   # mantener 0,0 en el G-code
        f_engrave=F_ENGRAVE,
        f_travel=F_TRAVEL,
        s_max=S_MAX,
    )

    print("[2/4] Conectando a GRBL...")
    ser = open_serial(PORT, BAUD)

    print("[3/4] Posicionando cabezal y fijando origen temporal (G92) en el offset...")
    # Mueve a (dx,dy) en relativo a F1000 y fija ese punto como X0 Y0 de trabajo (G92 X0 Y0)
    move_to_offset_and_set_origin(ser, dx=OFFSET_DX, dy=OFFSET_DY, feed=OFFSET_FEED)

    print("[4/4] Enviando trabajo de grabado...")
    try:
        rc = stream_to_grbl(ser, gcode)
        # Al terminar el grabado, volver a X0 Y0 de máquina y limpiar offset temporal
        move_back_to_machine_origin(ser)

        if rc == 0:
            print("Grabado finalizado con éxito.")
        else:
            print("El grabado terminó con errores.")
    finally:
        try:
            ser.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
