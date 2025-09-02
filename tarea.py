import tkinter as tk
from tkinter import *
from tkinter import ttk
from PIL import Image
from PIL import ImageTk
import imutils
import cv2
import numpy as np

#crea ventana, define tamaño y titulo
ventana = tk.Tk()
ventana.geometry("1200x400")
ventana.resizable(0,0)
ventana.title("Procesamiento de imagen con Webcam - 3 Recuadros")

#variable globales
global Captura, CapturaG

# Variables para el sistema de 2 clics
click_count = 0
primer_click = None
segundo_click = None

# Variable para guardar la imagen base capturada (no cambia al modificar coordenadas)
imagen_base_capturada = None

# Función para actualizar recorte cuando se modifican las coordenadas
def actualizar_recorte_en_tiempo_real(*args):
    """Función que se ejecuta cuando se modifican los campos de coordenadas"""
    # Solo actualizar si tenemos una imagen base capturada y todos los campos tienen valores
    if imagen_base_capturada is not None:
        try:
            x1_val = x1_entry.get()
            y1_val = y1_entry.get()
            x2_val = x2_entry.get()
            y2_val = y2_entry.get()
            
            # Solo proceder si todos los campos tienen valores
            if x1_val and y1_val and x2_val and y2_val:
                # Usar la función de recorte dinámico (no cambia la imagen base)
                recortar_dinamico()
        except:
            pass  # Ignorar errores durante la escritura

def camara():
    global capture, click_count, primer_click, segundo_click, imagen_base_capturada
    capture = cv2.VideoCapture(0)
    # Restaurar el segundo recuadro a su tamaño original cuando se inicia la cámara
    GImagenROI.place(x=390, y=50, width=300, height=240)
    GImagenROI.configure(image="")
    GImagenROI.image = ""
    click_count = 0
    primer_click = None
    segundo_click = None
    imagen_base_capturada = None  # Limpiar imagen base guardada
    coordenadas['text'] = "Haz 2 clics en la imagen para recortar"
    iniciar()

def iniciar():
    global capture
    if capture is not None:
        ret, frame = capture.read()
        if ret == True:
            frame = imutils.resize(frame, width=311)
            frame = imutils.resize(frame, height=241)
            ImagenCamara = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            im = Image.fromarray(ImagenCamara)
            img = ImageTk.PhotoImage(image= im)
            LImagen.configure(image = img)
            LImagen.image = img
            
            # Capturar automáticamente para tener imagen disponible para recortar
            Capturar()
            
            LImagen.after(10,iniciar)
        else:
            LImagen.image = ""
            capture.release()

#funcion para tomar foto
def Capturar():
    global valor, Captura, CapturaG
    camara = capture
    return_value, image = camara.read()
    frame = imutils.resize(image, width=301)
    frame = imutils.resize(frame, height=221)
    CapturaG = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    Captura = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    # NO mostramos nada en el segundo recuadro hasta hacer recorte

def rgb():
    # Función simplificada - usa valores fijos para umbralización RGB
    global img_mask, img_aux, bin_imagen
    Minimos = (0, 0, 0)    # Valores mínimos RGB
    Maximos = (100, 100, 100)  # Valores máximos RGB
    img_mask = cv2.inRange(Captura, Minimos, Maximos)
    img_aux = img_mask
    img_mask = Image.fromarray(img_mask)
    img_mask = ImageTk.PhotoImage(image= img_mask)
    UImagen.configure(image=img_mask)
    UImagen.image = img_mask
    _, bin_imagen = cv2.threshold(img_aux, 0, 255, cv2.THRESH_BINARY_INV)

def manchas():
    num_pixels_con_manchas = cv2.countNonZero(bin_imagen)
    porcentaje_manchas = 100 - (num_pixels_con_manchas / bin_imagen.size) * 100

    contornos = cv2.findContours(img_aux, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0]
    num_formas = len(contornos)
    Cadena = f"Cantidad de manchas blancas: {num_formas}\nPorcentaje area con manchas: {round(porcentaje_manchas,2)}%"
    print(Cadena)  # Mostramos resultado en consola

def umbralizacion():
    global thresh1, mask
    try:
        # Verificar que existe un recorte
        if 'ImgRec' not in globals() or ImgRec is None:
            print("Error: Primero haz un recorte con 2 clics para poder umbralizar")
            coordenadas['text'] = "Haz recorte primero"
            return
            
        valor = int(numeroUmbra.get())
        
        # Convertir el recorte a escala de grises para umbralización
        ImgRecGray = cv2.cvtColor(ImgRec, cv2.COLOR_RGB2GRAY)
        
        # Aplicar umbralización al recorte
        ret, thresh1 = cv2.threshold(ImgRecGray, valor, 255, cv2.THRESH_BINARY)
        
        # Mostrar resultado umbralizado
        Umbral = Image.fromarray(thresh1)
        Umbral = ImageTk.PhotoImage(image=Umbral)
        UImagen.configure(image = Umbral)
        UImagen.image = Umbral

        # Crear máscara para análisis usando el recorte original
        min_val = (valor, valor, valor)
        max_val = (255, 255, 255)
        mask = cv2.inRange(ImgRec, min_val, max_val)
        
        print(f"Umbralización aplicada al recorte con valor: {valor}")
        
    except Exception as e:
        print(f"Error en umbralización: {e}")
        coordenadas['text'] = "Error en umbralización"

def manchasG():
    try:
        # Verificar que existe umbralización
        if 'thresh1' not in globals() or thresh1 is None:
            print("Error: Primero aplica umbralización")
            return
            
        num_pixels_con_manchas = cv2.countNonZero(thresh1)
        porcentaje_manchas = 100 - (num_pixels_con_manchas / thresh1.size) * 100

        contornos = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0]
        manchas = len(contornos)
        Cadena = f'Cantidad de manchas blancas: {manchas}\nPorcentaje area con manchas: {round(porcentaje_manchas,2)}%'
        print(Cadena)  # Mostramos resultado en consola
        
    except Exception as e:
        print(f"Error al analizar manchas: {e}")


def mostrar_coordenadas(event):
    global click_count, primer_click, segundo_click
    
    # Incrementar contador de clics
    click_count += 1
    
    if click_count == 1:
        # Primer clic - guardar coordenadas y actualizar campos
        primer_click = (event.x, event.y)
        x1_entry.delete(0, tk.END)
        x1_entry.insert(0, str(event.x))
        y1_entry.delete(0, tk.END)
        y1_entry.insert(0, str(event.y))
        coordenadas['text'] = f'Primer clic: x={event.x} y={event.y}'
        print(f"Primer clic registrado: x={event.x}, y={event.y}")
        
    elif click_count == 2:
        # Segundo clic - guardar coordenadas, actualizar campos y recortar automáticamente
        segundo_click = (event.x, event.y)
        x2_entry.delete(0, tk.END)
        x2_entry.insert(0, str(event.x))
        y2_entry.delete(0, tk.END)
        y2_entry.insert(0, str(event.y))
        coordenadas['text'] = f'Segundo clic: x={event.x} y={event.y} - Recortando...'
        print(f"Segundo clic registrado: x={event.x}, y={event.y}")
        
        # Recortar automáticamente
        recortar_automatico()
        
        # Reiniciar contador para permitir nuevos recortes
        click_count = 0
        primer_click = None
        segundo_click = None

def recortar_automatico():
    """Función que se ejecuta automáticamente después del segundo clic"""
    global ImgRec, imagen_base_capturada
    try:
        # Obtener coordenadas de los campos (que ya fueron llenados por los clics)
        x1 = int(x1_entry.get())
        y1 = int(y1_entry.get())
        x2 = int(x2_entry.get())
        y2 = int(y2_entry.get())
        
        # Asegurar que x1,y1 sea la esquina superior izquierda y x2,y2 la inferior derecha
        x_min, x_max = min(x1, x2), max(x1, x2)
        y_min, y_max = min(y1, y2), max(y1, y2)
        
        # Verificar que las coordenadas sean válidas
        if x_min >= x_max or y_min >= y_max:
            print("Error: Las coordenadas no son válidas")
            return
        
        # GUARDAR LA IMAGEN BASE CAPTURADA (esta no cambiará)
        imagen_base_capturada = Captura.copy()
            
        # Realizar el recorte
        ImgRec = imagen_base_capturada[y_min:y_max, x_min:x_max]
        
        # Convertir a escala de grises para mostrar en el segundo recuadro
        ImgRecGray = cv2.cvtColor(ImgRec, cv2.COLOR_RGB2GRAY)
        
        # Obtener dimensiones originales del recorte
        altura_original, ancho_original = ImgRecGray.shape
        
        # Redimensionar el recuadro para que coincida exactamente con el recorte
        GImagenROI.place(x=390, y=50, width=ancho_original, height=altura_original)
        
        # Mostrar imagen sin redimensionar (tamaño original)
        im = Image.fromarray(ImgRecGray)
        img = ImageTk.PhotoImage(image=im)
        GImagenROI.configure(image=img)
        GImagenROI.image = img
        
        # Actualizar mensaje de coordenadas
        coordenadas['text'] = f'Recorte: ({x_min},{y_min}) a ({x_max},{y_max})'
        print(f"Recorte automático exitoso: x1={x_min}, y1={y_min}, x2={x_max}, y2={y_max}")
        print(f"Tamaño del recorte: {ancho_original}x{altura_original}")
        print("Imagen base guardada. Ahora puedes ajustar coordenadas sin perder el recorte original.")
        
    except ValueError:
        print("Error: Coordenadas inválidas")
        coordenadas['text'] = "Error en las coordenadas"
    except Exception as e:
        print(f"Error al recortar automáticamente: {e}")
        coordenadas['text'] = "Error al recortar"
        # En caso de error, limpiar el segundo recuadro
        GImagenROI.configure(image="")
        GImagenROI.image = ""

def recortar_dinamico():
    """Función para mostrar diferentes recortes de la imagen base SIN cambiar ImgRec original"""
    try:
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
    global ImgRec
    try:
        # Solo funciona si hay imagen base capturada
        if imagen_base_capturada is None:
            print("Error: Primero haz un recorte con 2 clics para capturar la imagen base")
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
            print("Error: Las coordenadas no son válidas. x2 > x1 y y2 > y1")
            return
            
        # AHORA SÍ cambiar ImgRec (solo cuando presionas botón recortar)
        ImgRec = imagen_base_capturada[y_min:y_max, x_min:x_max]
        
        # Convertir a escala de grises para mostrar en el segundo recuadro
        ImgRecGray = cv2.cvtColor(ImgRec, cv2.COLOR_RGB2GRAY)
        
        # Obtener dimensiones originales del recorte
        altura_original, ancho_original = ImgRecGray.shape
        
        # Redimensionar el recuadro para que coincida exactamente con el recorte
        GImagenROI.place(x=390, y=50, width=ancho_original, height=altura_original)
        
        # Mostrar imagen sin redimensionar (tamaño original)
        im = Image.fromarray(ImgRecGray)
        img = ImageTk.PhotoImage(image=im)
        GImagenROI.configure(image=img)
        GImagenROI.image = img
        
        print(f"RECORTE CONFIRMADO: x1={x_min}, y1={y_min}, x2={x_max}, y2={y_max}")
        print(f"Tamaño del recorte: {ancho_original}x{altura_original}")
        print("ImgRec ha sido actualizada con el nuevo recorte")
        
    except ValueError:
        print("Error: Ingrese valores numéricos válidos para las coordenadas")
    except Exception as e:
        print(f"Error al recortar: {e}")
        # En caso de error, limpiar el segundo recuadro
        GImagenROI.configure(image="")
        GImagenROI.image = ""

def rgb_recorte():
    # Función simplificada - usa valores fijos para umbralización RGB
    global img_mask_rec, img_aux_rec, bin_imagen_rec
    Minimos = (0, 0, 0)    # Valores mínimos RGB
    Maximos = (100, 100, 100)  # Valores máximos RGB
    img_mask_rec = cv2.inRange(ImgRec, Minimos, Maximos)
    img_aux_rec = img_mask_rec
    img_mask_rec = Image.fromarray(img_mask_rec)
    img_mask_rec = ImageTk.PhotoImage(image=img_mask_rec)
    UImagen.configure(image=img_mask_rec)
    UImagen.image = img_mask_rec
    _, bin_imagen_rec = cv2.threshold(img_aux_rec, 0, 255, cv2.THRESH_BINARY_INV)

def manchas_recorte():
    num_pixels_con_manchas = cv2.countNonZero(bin_imagen_rec)
    porcentaje_manchas = 100 - (num_pixels_con_manchas / bin_imagen_rec.size) * 100
    contornos = cv2.findContours(img_aux_rec, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0]
    num_formas = len(contornos)
    Cadena = f"Cantidad de manchas blancas: {num_formas}\nPorcentaje area con manchas: {round(porcentaje_manchas,2)}%"
    print(Cadena)  # Mostramos resultado en consola

#botones - Simplificados para 3 recuadros
BCamara = tk.Button(ventana, text="Iniciar camara", command=camara)
BCamara.place(x=150,y=300,width=90,height=23)
BBinary= tk.Button(ventana, text="Umbralizacion", command=umbralizacion)
BBinary.place(x=800,y=300,width=90,height=23)
BManchas = tk.Button(ventana, text="Analizar manchas", command=manchasG)
BManchas.place(x=950,y=300,width=100,height=23)

# Mantenemos solo el SpinBox para umbralización
numeroUmbra = tk.Spinbox(ventana, from_=0,to=255)
numeroUmbra.place(x=900, y=300, width=42, height=22)

# Campos para coordenadas de recorte con callbacks para actualización automática
tk.Label(ventana, text="x1:").place(x=450, y=330)
x1_entry = tk.Entry(ventana, width=6)
x1_entry.place(x=470, y=330)
x1_entry.bind('<KeyRelease>', actualizar_recorte_en_tiempo_real)  # Actualizar al escribir

tk.Label(ventana, text="y1:").place(x=520, y=330)
y1_entry = tk.Entry(ventana, width=6)
y1_entry.place(x=540, y=330)
y1_entry.bind('<KeyRelease>', actualizar_recorte_en_tiempo_real)  # Actualizar al escribir

tk.Label(ventana, text="x2:").place(x=450, y=350)
x2_entry = tk.Entry(ventana, width=5)
x2_entry.place(x=470, y=350)
x2_entry.bind('<KeyRelease>', actualizar_recorte_en_tiempo_real)  # Actualizar al escribir

tk.Label(ventana, text="y2:").place(x=520, y=350)
y2_entry = tk.Entry(ventana, width=5)
y2_entry.place(x=540, y=350)
y2_entry.bind('<KeyRelease>', actualizar_recorte_en_tiempo_real)  # Actualizar al escribir

#label para coordenadas
coordenadasTitulo = tk.Label(ventana, text="Coordenadas")
coordenadasTitulo.place(x=500,y=305)
coordenadas = tk.Label(ventana, text="")
coordenadas.place(x=300, y=330)

# Cuadros de Imagen - Solo 3 recuadros principales
LImagen = tk.Label(ventana, background="gray")
LImagen.place(x=50, y=50, width=300, height=240)
LImagen.bind('<Button-1>', mostrar_coordenadas)  # Agregar evento de clic

GImagenROI = tk.Label(ventana, background="gray")
GImagenROI.place(x=390, y=50, width=300, height=240)

UImagen = tk.Label(ventana, background="gray")
UImagen.place(x=730, y=50, width=301, height=240)

# Pasos
paso1 = tk.Label(ventana, text="Paso 1. Cámara en vivo (2 clics para recortar)")
paso1.place(x=70, y=20)

paso2 = tk.Label(ventana, text="Paso 2. Imagen recortada en gris")
paso2.place(x=400, y=20)

paso3 = tk.Label(ventana, text="Paso 3. Imagen umbralizada")
paso3.place(x=730, y=20)


ventana.mainloop()


