import numpy as np
import cv2
import cv2.aruco as aruco
import tkinter as tk
from tkinter import ttk, Scale, messagebox, filedialog
from PIL import Image, ImageTk, ImageOps
import threading
import random
import time
import os



class VentanaCrearAruco:
    def __init__(self, parent):
        self.parent = parent
        self.ventana = tk.Toplevel(parent)
        self.ventana.title("Crear ArUco")
        self.ventana.geometry("400x250")
        self.ventana.resizable(False, False)

        # Variables
        self.var_diccionario = tk.StringVar(value="DICT_4X4_100")
        self.var_tamano = tk.IntVar(value=200)
        self.var_id = tk.IntVar(value=0)

        self.resultado = None  # Para almacenar los datos

        self.crear_interfaz()

    # =========================================================================
    # MÉTODOS DE CREACIÓN DE INTERFAZ - VENTANA CREAR ARUCO
    # =========================================================================

    def crear_interfaz(self):
        frame = ttk.Frame(self.ventana, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Diccionario:").grid(row=0, column=0, sticky=tk.W)
        dicc_combo = ttk.Combobox(frame, textvariable=self.var_diccionario,
            values=["DICT_ARUCO_ORIGINAL", "DICT_4X4_100", "DICT_5X5_100", "DICT_6X6_100", "DICT_7X7_100"], width=20)
        dicc_combo.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frame, text="Tamaño (px):").grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(frame, textvariable=self.var_tamano, width=10).grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(frame, text="ID del marcador:").grid(row=2, column=0, sticky=tk.W)
        ttk.Entry(frame, textvariable=self.var_id, width=10).grid(row=2, column=1, padx=5, pady=5)

        ttk.Button(frame, text="Generar", command=self.generar_aruco).grid(row=3, column=0, columnspan=2, pady=10)
        ttk.Button(frame, text="Cancelar", command=self.cancelar).grid(row=4, column=0, columnspan=2, pady=5)

    # =========================================================================
    # MÉTODOS DE FUNCIONALIDAD - VENTANA CREAR ARUCO
    # =========================================================================

    def generar_aruco(self):
        try:
            # Obtener parámetros
            dicc_nombre = self.var_diccionario.get()
            tamano = self.var_tamano.get()
            id_aruco = self.var_id.get()
            
            # Crear diccionario ArUco
            diccionario = getattr(aruco, 'getPredefinedDictionary')(getattr(aruco, dicc_nombre))
            
            # Generar imagen del marcador
            marcador = aruco.generateImageMarker(diccionario, id_aruco, tamano)
            
            # Crear nombre de archivo único
            nombre_archivo = f"aruco_{dicc_nombre}_{id_aruco}_{tamano}px.png"
            ruta_archivo = os.path.join(os.path.dirname(os.path.abspath(__file__)), nombre_archivo)
            
            # Guardar imagen
            cv2.imwrite(ruta_archivo, marcador)
            
            # Almacena los datos incluyendo la ruta de la imagen
            self.resultado = {
                "diccionario": dicc_nombre,
                "tamano": tamano,
                "id": id_aruco,
                "imagen_path": ruta_archivo,
                "nombre_archivo": nombre_archivo
            }
            
            messagebox.showinfo("Éxito", f"ArUco generado y guardado como:\n{nombre_archivo}")
            self.ventana.destroy()
            
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo generar el ArUco:\n{str(e)}")
            return

    def cancelar(self):
        self.resultado = None
        self.ventana.destroy()

def crear_aruco(root):
    ventana = VentanaCrearAruco(root)
    root.wait_window(ventana.ventana)
    return ventana.resultado  # Devuelve diccionario, tamaño y id
    