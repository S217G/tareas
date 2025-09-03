import tkinter as tk
from tkinter import *
from tkinter import ttk
from PIL import Image, ImageTk
import imutils
import cv2
import numpy as np

# crea ventana, define tamaño y titulo
ventana = tk.Tk()
ventana.geometry("1200x400")
ventana.title("Procesamiento de imagen con Webcam - 3 Recuadros")

# variable globales
global Captura, CapturaG, bin_imagen_rec, ImgRec, capture
Captura = None
CapturaG = None
bin_imagen_rec = None
ImgRec = None
capture = None
# funcion para tomar foto
def Capturar():
    global Captura, CapturaG, capture
    if capture is None:
        return
    camara_local = capture
    ret, image = camara_local.read()
    if not ret:
        return
    frame = imutils.resize(image, width=301)
    frame = imutils.resize(frame, height=221)
    CapturaG = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    Captura = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    # NO mostramos nada en el segundo recuadro hasta hacer recorte

def rgb():
    # Función simplificada - usa valores fijos para umbralización RGB
    global img_mask, img_aux, bin_imagen
    if Captura is None:
        return
    Minimos = (0, 0, 0) # Valores mínimos RGB
    Maximos = (100, 100, 100) # Valores máximos RGB
    img_mask = cv2.inRange(Captura, Minimos, Maximos)
    img_aux = img_mask
    img_mask = Image.fromarray(img_mask)
    img_mask = ImageTk.PhotoImage(image=img_mask)
    UImagen.configure(image=img_mask)
    UImagen.image = img_mask
    _, bin_imagen = cv2.threshold(img_aux, 0, 255, cv2.THRESH_BINARY_INV)

def manchas():
    if 'bin_imagen' not in globals() or bin_imagen is None:
        return
        # Evitar ejecución si no hay imagen base guardada
        if imagen_base_capturada is None:
            return

        # Obtener coordenadas de los campos de entrada
        x1 = int(x1_entry.get()) if x1_entry.get() else 0
        y1 = int(y1_entry.get()) if y1_entry.get() else 0
        x2 = int(x2_entry.get()) if x2_entry.get() else 200
        y2 = int(y2_entry.get()) if y2_entry.get() else 150

        # Asegurar que x1,y1 sea la esquina superior izquierda y x2,y2 la inferior derecha
        x_min, x_max = min(x1, x2), max(x1, x2)
        y_min, y_max = min(y1, y2), max(y1, y2)

        # Verificar que las coordenadas sean válidas
        if x_min >= x_max or y_min >= y_max:
            print("Error: Las coordenadas no son válidas para vista dinámica")
            return

        # Usar la imagen base guardada (NO cambiar ImgRec original)
        img_temporal = imagen_base_capturada[y_min:y_max, x_min:x_max]

        # Convertir a escala de grises para mostrar en el segundo recuadro
        ImgTempGray = cv2.cvtColor(img_temporal, cv2.COLOR_RGB2GRAY)

        # Obtener dimensiones del recorte temporal
        altura_temp, ancho_temp = ImgTempGray.shape

        # Redimensionar el recuadro para que coincida exactamente con el recorte temporal
        GImagenROI.place(x=390, y=50, width=ancho_temp, height=altura_temp)

        # Mostrar imagen temporal sin redimensionar
        im = Image.fromarray(ImgTempGray)
        img = ImageTk.PhotoImage(image=im)
        GImagenROI.configure(image=img)
        GImagenROI.image = img

        print(f"Vista dinámica: x1={x_min}, y1={y_min}, x2={x_max}, y2={y_max}")
        print(f"Tamaño de vista: {ancho_temp}x{altura_temp}")

    except ValueError:
        print("Error: Valores no válidos para vista dinámica")
    except Exception as e:
        print(f"Error en vista dinámica: {e}")

def recortar():
    """Función para recortar manualmente (cambia ImgRec cuando presionas el botón)"""
    global ImgRec, imagen_base_capturada
    if 'ImgRec' not in globals() or ImgRec is None:
        return
    Minimos = (0, 0, 0) # Valores mínimos RGB
    Maximos = (100, 100, 100) # Valores máximos RGB
    img_mask_rec = cv2.inRange(ImgRec, Minimos, Maximos)
    img_aux_rec = img_mask_rec
    img_mask_rec_disp = Image.fromarray(img_mask_rec)
    img_mask_rec_disp = ImageTk.PhotoImage(image=img_mask_rec_disp)
    UImagen.configure(image=img_mask_rec_disp)
    UImagen.image = img_mask_rec_disp
    _, bin_imagen_rec = cv2.threshold(img_aux_rec, 0, 255, cv2.THRESH_BINARY_INV)

def manchas_recorte():
    # Verificar que existe un recorte
    if 'ImgRec' not in globals() or ImgRec is None:
        print("Error: Primero haz un recorte con 2 clics")
        CajaTexto2.configure(state='normal')
        CajaTexto2.delete(1.0, tk.END)
        CajaTexto2.insert(1.0, "Error: Primero haz un recorte")
        CajaTexto2.configure(state='disabled')
        return

    # Primero aplicar umbralización RGB al recorte (genera img_aux_rec)
    rgb_recorte()

    # Verificar máscara creada
    if 'img_aux_rec' not in globals() or img_aux_rec is None:
        print("Error: No se pudo crear la máscara del recorte")
        return

    # Calculamos: pixeles blancos y negros en la máscara (área)
    total_pixels = img_aux_rec.size # ancho*alto
    white_pixels = cv2.countNonZero(img_aux_rec) # blancos en la máscara (dentro del rango)
    black_pixels = total_pixels - white_pixels

    percent_white = (white_pixels / total_pixels) * 100 if total_pixels > 0 else 0.0
    percent_black = 100.0 - percent_white

    # Contornos blancos (cada mancha blanca en la máscara)
    contours_white = cv2.findContours(img_aux_rec, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0]
    num_white = len(contours_white)

    # Contornos negros: invertimos máscara y contamos
    inv_mask = cv2.bitwise_not(img_aux_rec)
    contours_black = cv2.findContours(inv_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0]
    num_black = len(contours_black)

    # Construir cadena clara y mostrarla en la CajaTexto2
    Cadena = (
        f"Manchas BLANCAS (en máscara): {num_white}\n"
        f"Área blanca: {percent_white:.2f}% (pix={white_pixels})\n\n"
        f"Manchas NEGRAS (en máscara invertida): {num_black}\n"
        f"Área negra: {percent_black:.2f}% (pix={black_pixels})"
    )

    CajaTexto2.configure(state='normal')
    CajaTexto2.delete(1.0, tk.END)
    CajaTexto2.insert(1.0, Cadena)
    CajaTexto2.configure(state='disabled')

# botones - Simplificados para 3 recuadros
BCamara = tk.Button(ventana, text="Iniciar camara", command=camara)
BCamara.place(x=150, y=300, width=90, height=23)
BBinary = tk.Button(ventana, text="Umbralizacion", command=umbralizacion)
BBinary.place(x=800, y=300, width=90, height=23)
BManchas = tk.Button(ventana, text="Analizar manchas", command=manchasG)
BManchas.place(x=950, y=300, width=100, height=23)

# Mantenemos solo el SpinBox para umbralización
numeroUmbra = tk.Spinbox(ventana, from_=81, to=255)
numeroUmbra.place(x=900, y=300, width=42, height=22)

# Campos para coordenadas de recorte con callbacks para actualización automática
tk.Label(ventana, text="x1:").place(x=450, y=330)
x1_entry = tk.Entry(ventana, width=6)
x1_entry.place(x=470, y=330)
x1_entry.bind('<KeyRelease>', actualizar_recorte_en_tiempo_real) # Actualizar al escribir
tk.Label(ventana, text="y1:").place(x=520, y=330)
y1_entry = tk.Entry(ventana, width=6)
y1_entry.place(x=540, y=330)
y1_entry.bind('<KeyRelease>', actualizar_recorte_en_tiempo_real) # Actualizar al escribir
tk.Label(ventana, text="x2:").place(x=450, y=350)
x2_entry = tk.Entry(ventana, width=5)
x2_entry.place(x=470, y=350)
x2_entry.bind('<KeyRelease>', actualizar_recorte_en_tiempo_real) # Actualizar al escribir
tk.Label(ventana, text="y2:").place(x=520, y=350)
y2_entry = tk.Entry(ventana, width=5)
y2_entry.place(x=540, y=350)
y2_entry.bind('<KeyRelease>', actualizar_recorte_en_tiempo_real) # Actualizar al escribir

# label para coordenadas
coordenadasTitulo = tk.Label(ventana, text="Coordenadas")
coordenadasTitulo.place(x=500, y=305)
coordenadas = tk.Label(ventana, text="")
coordenadas.place(x=300, y=330)

# Cuadros de Imagen - Solo 3 recuadros principales
LImagen = tk.Label(ventana, background="gray")
LImagen.place(x=50, y=50, width=300, height=240)
LImagen.bind('<Button-1>', mostrar_coordenadas) # Agregar evento de clic
GImagenROI = tk.Label(ventana, background="gray")
GImagenROI.place(x=390, y=50)
UImagen = tk.Label(ventana, background="gray")
UImagen.place(x=730, y=50)

# Pasos
paso1 = tk.Label(ventana, text="Paso 1. Cámara en vivo (2 clics para recortar)")
paso1.place(x=70, y=20)
paso2 = tk.Label(ventana, text="Paso 2. Imagen recortada en gris")
paso2.place(x=400, y=20)
paso3 = tk.Label(ventana, text="Paso 3. Imagen umbralizada")
paso3.place(x=730, y=20)

# Caja de texto donde mostramos manchas del recorte
CajaTexto2 = tk.Text(ventana, state='disabled')
CajaTexto2.place(x=900, y=330, width=250, height=60)

# Agrega este botón junto a los otros botones (después de BManchas)
BManchasRecorte = tk.Button(ventana, text="Analizar recorte", command=manchas_recorte)
BManchasRecorte.place(x=800, y=330, width=100, height=23)

ventana.mainloop()
