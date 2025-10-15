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
        self.ventana.geometry("450x300")
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

        # Información sobre el grabado láser
        info_frame = ttk.LabelFrame(frame, text="Información del Láser", padding="5")
        info_frame.grid(row=3, column=0, columnspan=2, pady=10, sticky=(tk.W, tk.E))
        
        info_text = ("💡 Para grabado láser:\n" +
                    "• El láser graba las áreas NEGRAS\n" +
                    "• Se generará una versión invertida automáticamente\n" +
                    "• Usa la versión '_invertido.png' para el láser")
        ttk.Label(info_frame, text=info_text, font=("Arial", 8), justify=tk.LEFT).pack(anchor=tk.W)

        ttk.Button(frame, text="Generar ArUco", command=self.generar_aruco).grid(row=4, column=0, columnspan=2, pady=10)
        ttk.Button(frame, text="Cancelar", command=self.cancelar).grid(row=5, column=0, columnspan=2, pady=5)

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
            
            # Generar imagen del marcador (versión normal - fondo blanco, patrón negro)
            marcador_normal = aruco.generateImageMarker(diccionario, id_aruco, tamano)
            
            # Crear versión invertida para grabado láser (fondo negro, patrón blanco)
            marcador_invertido = cv2.bitwise_not(marcador_normal)
            
            # Crear nombres de archivo únicos
            nombre_normal = f"aruco_{dicc_nombre}_{id_aruco}_{tamano}px.png"
            nombre_invertido = f"aruco_{dicc_nombre}_{id_aruco}_{tamano}px_invertido.png"
            
            ruta_normal = os.path.join(os.path.dirname(os.path.abspath(__file__)), nombre_normal)
            ruta_invertido = os.path.join(os.path.dirname(os.path.abspath(__file__)), nombre_invertido)
            
            # Guardar ambas imágenes
            cv2.imwrite(ruta_normal, marcador_normal)
            cv2.imwrite(ruta_invertido, marcador_invertido)
            
            # Mostrar vista previa
            self.mostrar_vista_previa(marcador_normal, marcador_invertido)
            
            # Almacena los datos incluyendo ambas rutas
            self.resultado = {
                "diccionario": dicc_nombre,
                "tamano": tamano,
                "id": id_aruco,
                "imagen_path": ruta_invertido,  # Por defecto usar la invertida para láser
                "imagen_path_normal": ruta_normal,
                "imagen_path_invertido": ruta_invertido,
                "nombre_archivo": nombre_invertido,
                "nombre_archivo_normal": nombre_normal,
                "nombre_archivo_invertido": nombre_invertido
            }
            
            messagebox.showinfo("Éxito", 
                f"ArUco generado y guardado:\n\n" +
                f"• Versión normal: {nombre_normal}\n" +
                f"• Versión para láser: {nombre_invertido}\n\n" +
                f"💡 Usa la versión invertida para grabado láser")
            self.ventana.destroy()
            
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo generar el ArUco:\n{str(e)}")
            return

    def cancelar(self):
        self.resultado = None
        self.ventana.destroy()

    def mostrar_vista_previa(self, imagen_normal, imagen_invertida):
        """Muestra una vista previa de ambas versiones del ArUco"""
        try:
            # Crear ventana de vista previa
            preview_window = tk.Toplevel(self.ventana)
            preview_window.title("Vista Previa - ArUco")
            preview_window.geometry("600x300")
            
            # Frame principal
            main_frame = ttk.Frame(preview_window, padding="10")
            main_frame.pack(fill=tk.BOTH, expand=True)
            
            # Frame para imagen normal
            normal_frame = ttk.LabelFrame(main_frame, text="Versión Normal (Detección)", padding="5")
            normal_frame.pack(side=tk.LEFT, padx=5, pady=5)
            
            # Frame para imagen invertida
            invertida_frame = ttk.LabelFrame(main_frame, text="Versión para Láser (Grabado)", padding="5")
            invertida_frame.pack(side=tk.RIGHT, padx=5, pady=5)
            
            # Convertir imágenes para mostrar en tkinter
            img_normal_pil = Image.fromarray(imagen_normal)
            img_normal_pil = img_normal_pil.resize((150, 150), Image.Resampling.NEAREST)
            img_normal_tk = ImageTk.PhotoImage(img_normal_pil)
            
            img_invertida_pil = Image.fromarray(imagen_invertida)
            img_invertida_pil = img_invertida_pil.resize((150, 150), Image.Resampling.NEAREST)
            img_invertida_tk = ImageTk.PhotoImage(img_invertida_pil)
            
            # Mostrar imágenes
            label_normal = ttk.Label(normal_frame, image=img_normal_tk)
            label_normal.image = img_normal_tk  # Mantener referencia
            label_normal.pack()
            
            label_invertida = ttk.Label(invertida_frame, image=img_invertida_tk)
            label_invertida.image = img_invertida_tk  # Mantener referencia
            label_invertida.pack()
            
            # Información adicional
            ttk.Label(normal_frame, text="Para detección\ncon cámara", 
                     font=("Arial", 8), justify=tk.CENTER).pack(pady=5)
            ttk.Label(invertida_frame, text="Para grabado\ncon láser", 
                     font=("Arial", 8), justify=tk.CENTER).pack(pady=5)
            
            # Botón cerrar
            ttk.Button(preview_window, text="Cerrar Vista Previa", 
                      command=preview_window.destroy).pack(pady=10)
                      
        except Exception as e:
            print(f"Error mostrando vista previa: {e}")

def crear_aruco(root):
    ventana = VentanaCrearAruco(root)
    root.wait_window(ventana.ventana)
    return ventana.resultado  # Devuelve diccionario, tamaño y id
    