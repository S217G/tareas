#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DETECTOR ARUCO - MÓDULO DE DETECCIÓN Y PROCESAMIENTO DE CÁMARA
=============================================================
Este módulo contiene toda la funcionalidad relacionada con:
- Detección de marcadores ArUco
- Procesamiento de imagen de cámara
- Medición de objetos
- Interfaz de control de cámara

Extraído de ArucoProyectoBloqueo.py para modularización.
"""

# =============================================================================
# IMPORTACIONES
# =============================================================================

import numpy as np
import cv2
import cv2.aruco as aruco
import tkinter as tk
from tkinter import ttk, Scale, messagebox
from PIL import Image, ImageTk
import threading
import random
import time
from datetime import datetime

# =============================================================================
# CONFIGURACIÓN DE ARUCO
# =============================================================================

# Diccionario y parámetros del marcador ArUco
diccionario_aruco = aruco.getPredefinedDictionary(aruco.DICT_4X4_100)
parametros_aruco = aruco.DetectorParameters()

# Configurar parámetros optimizados para mejor detección
parametros_aruco.adaptiveThreshWinSizeMin = 3
parametros_aruco.adaptiveThreshWinSizeMax = 35  # Aumentado para detectar a mayor distancia
parametros_aruco.adaptiveThreshWinSizeStep = 4   # Pasos más pequeños para mejor precisión
parametros_aruco.adaptiveThreshConstant = 5      # Reducido para mayor sensibilidad
parametros_aruco.minMarkerPerimeterRate = 0.01   # Más permisivo para marcadores pequeños
parametros_aruco.maxMarkerPerimeterRate = 6.0    # Permitir marcadores más grandes
parametros_aruco.polygonalApproxAccuracyRate = 0.05  # Más tolerante
parametros_aruco.minCornerDistanceRate = 0.03    # Reducido para mejor detección
parametros_aruco.minDistanceToBorder = 1         # Reducido para bordes
parametros_aruco.minMarkerDistanceRate = 0.03    # Reducido para permitir marcadores cercanos
parametros_aruco.cornerRefinementMethod = aruco.CORNER_REFINE_SUBPIX
parametros_aruco.cornerRefinementWinSize = 3     # Reducido para mayor velocidad
parametros_aruco.cornerRefinementMaxIterations = 50  # Aumentado para mejor precisión
parametros_aruco.cornerRefinementMinAccuracy = 0.05  # Reducido para ser menos estricto
parametros_aruco.markerBorderBits = 1
parametros_aruco.perspectiveRemovePixelPerCell = 8   # Aumentado para mejor resolución
parametros_aruco.perspectiveRemoveIgnoredMarginPerCell = 0.1  # Reducido
parametros_aruco.maxErroneousBitsInBorderRate = 0.5  # Más tolerante a errores
parametros_aruco.minOtsuStdDev = 3.0             # Reducido para mayor sensibilidad
parametros_aruco.errorCorrectionRate = 0.8       # Aumentado para mejor corrección

# Detector ArUco global (compatible con OpenCV 4.7+)
detector_aruco = None

def crear_detector_aruco():
    """Crea el detector ArUco con el diccionario y parámetros actuales"""
    global detector_aruco
    try:
        # Intenta usar la nueva API (OpenCV >= 4.7)
        detector_aruco = aruco.ArucoDetector(diccionario_aruco, parametros_aruco)
        return True
    except AttributeError:
        # Fallback para versiones anteriores
        detector_aruco = None
        return False

def optimizar_parametros_deteccion(condiciones="normal"):
    """Optimiza los parámetros según las condiciones de iluminación y calidad"""
    global parametros_aruco, detector_aruco, usar_nueva_api
    
    if condiciones == "baja_luz":
        # Parámetros para condiciones de poca luz
        parametros_aruco.adaptiveThreshConstant = 3
        parametros_aruco.minMarkerPerimeterRate = 0.01
        parametros_aruco.maxMarkerPerimeterRate = 6.0
        parametros_aruco.polygonalApproxAccuracyRate = 0.06
        parametros_aruco.errorCorrectionRate = 0.9
    elif condiciones == "distancia_larga":
        # Parámetros especiales para detección a mayor distancia
        parametros_aruco.adaptiveThreshWinSizeMin = 3
        parametros_aruco.adaptiveThreshWinSizeMax = 45
        parametros_aruco.adaptiveThreshWinSizeStep = 2
        parametros_aruco.adaptiveThreshConstant = 3
        parametros_aruco.minMarkerPerimeterRate = 0.005
        parametros_aruco.maxMarkerPerimeterRate = 8.0
        parametros_aruco.polygonalApproxAccuracyRate = 0.08
        parametros_aruco.minCornerDistanceRate = 0.02
        parametros_aruco.perspectiveRemovePixelPerCell = 12
        parametros_aruco.maxErroneousBitsInBorderRate = 0.7
        parametros_aruco.errorCorrectionRate = 0.9
    elif condiciones == "alta_precision":
        # Parámetros para máxima precisión
        parametros_aruco.adaptiveThreshConstant = 10
        parametros_aruco.minMarkerPerimeterRate = 0.05
        parametros_aruco.polygonalApproxAccuracyRate = 0.02
        parametros_aruco.cornerRefinementWinSize = 3
        parametros_aruco.cornerRefinementMaxIterations = 100
    elif condiciones == "rapido":
        # Parámetros para detección rápida
        parametros_aruco.adaptiveThreshWinSizeMin = 5
        parametros_aruco.adaptiveThreshWinSizeMax = 15
        parametros_aruco.cornerRefinementMethod = aruco.CORNER_REFINE_NONE
        parametros_aruco.errorCorrectionRate = 0.5
    else:
        # Parámetros balanceados (normal)
        parametros_aruco.adaptiveThreshConstant = 5
        parametros_aruco.minMarkerPerimeterRate = 0.01
        parametros_aruco.maxMarkerPerimeterRate = 6.0
    
    # Recrear detector con nuevos parámetros
    usar_nueva_api = crear_detector_aruco()
    print(f"Parámetros optimizados para: {condiciones}")

# Inicializar detector con parámetros de alta precisión por defecto
optimizar_parametros_deteccion("alta_precision")
usar_nueva_api = crear_detector_aruco()

# =============================================================================
# CONFIGURACIÓN DE COLORES Y MEDICIÓN
# =============================================================================

# Rangos de color en HSV para detección
# Rojo
rojo_bajo1 = np.array([0, 100, 100], dtype=np.uint8)
rojo_alto1 = np.array([10, 255, 255], dtype=np.uint8)
rojo_bajo2 = np.array([160, 100, 100], dtype=np.uint8)
rojo_alto2 = np.array([179, 255, 255], dtype=np.uint8)

# Verde
verde_bajo = np.array([40, 100, 100], dtype=np.uint8)
verde_alto = np.array([80, 255, 255], dtype=np.uint8)

# Azul
azul_bajo = np.array([100, 100, 100], dtype=np.uint8)
azul_alto = np.array([140, 255, 255], dtype=np.uint8)

# Tamaño real del marcador ArUco en centímetros
tamano_aruco_cm = 3.0
proporcion_cm_por_pixel = None  # Inicializar la variable global

# =============================================================================
# FUNCIONES DE MEDICIÓN Y DETECCIÓN DE OBJETOS
# =============================================================================

def medir_objeto(contorno, imagen, proporcion_cm_por_pixel):
    """Mide un objeto detectado y retorna información completa"""
    if proporcion_cm_por_pixel is None:
        return None
    
    x, y, ancho, alto = cv2.boundingRect(contorno)
    ancho_cm = ancho * proporcion_cm_por_pixel
    alto_cm = alto * proporcion_cm_por_pixel
    area_cm2 = ancho_cm * alto_cm
    
    # Retornar información del objeto para poder ordenarlo
    return {
        'contorno': contorno,
        'bbox': (x, y, ancho, alto),
        'ancho_cm': ancho_cm,
        'alto_cm': alto_cm,
        'area_cm2': area_cm2,
        'centro': (x + ancho // 2, y + alto // 2)
    }

def dibujar_objeto_medido(objeto_info, imagen, color=(0, 255, 0), numero=None):
    """Dibuja un objeto medido en la imagen"""
    x, y, ancho, alto = objeto_info['bbox']
    ancho_cm = objeto_info['ancho_cm']
    alto_cm = objeto_info['alto_cm']
    area_cm2 = objeto_info['area_cm2']
    centro_x, centro_y = objeto_info['centro']
    
    # Dibujar rectángulo
    cv2.rectangle(imagen, (x, y), (x + ancho, y + alto), color, 2)
    
    # Dibujar centro
    cv2.circle(imagen, (centro_x, centro_y), 3, (0, 0, 255), -1)
    
    # Mostrar número si se proporciona
    if numero is not None:
        cv2.putText(imagen, f"#{numero}", (x, y - 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)
    
    # Mostrar medidas
    texto_ancho = f"Ancho: {ancho_cm:.2f} cm"
    texto_alto = f"Alto: {alto_cm:.2f} cm"
    texto_area = f"Area: {area_cm2:.2f} cm²"
    
    cv2.putText(imagen, texto_ancho, (x, y - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
    cv2.putText(imagen, texto_alto, (x, y - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
    cv2.putText(imagen, texto_area, (x, y - 0), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

def dibujar_aruco_ordenado(esquina, id_aruco, imagen, color=(0, 255, 0), numero_orden=None):
    """Dibuja un ArUco con información de ordenamiento"""
    puntos = esquina[0]
    
    # Calcular centro del ArUco
    centro = np.mean(puntos, axis=0).astype(int)
    
    # Dibujar un círculo en el centro
    cv2.circle(imagen, tuple(centro), 8, color, -1)
    
    # Mostrar número de orden si se proporciona
    if numero_orden is not None:
        cv2.putText(imagen, f"#{numero_orden}", (centro[0] - 15, centro[1] - 25), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 3)
        cv2.putText(imagen, f"#{numero_orden}", (centro[0] - 15, centro[1] - 25), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)
    
    # Mostrar ID del ArUco
    cv2.putText(imagen, f"ID:{id_aruco}", (centro[0] - 20, centro[1] + 35), 
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 3)
    cv2.putText(imagen, f"ID:{id_aruco}", (centro[0] - 20, centro[1] + 35), 
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

def detectar_arucos(imagen):
    """Detecta marcadores ArUco múltiples con alta precisión"""
    global usar_nueva_api, detector_aruco
    
    # Preprocesamiento optimizado para múltiples ArUcos
    imagen_gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    
    # Mejorar contraste para detección precisa
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8,8))
    imagen_gris = clahe.apply(imagen_gris)
    
    # Suavizado suave para eliminar ruido
    imagen_gris = cv2.GaussianBlur(imagen_gris, (3, 3), 0)
    
    # Detectar marcadores ArUco
    if usar_nueva_api and detector_aruco is not None:
        esquinas, ids, rechazados = detector_aruco.detectMarkers(imagen_gris)
    else:
        try:
            esquinas, ids, rechazados = aruco.detectMarkers(imagen_gris, diccionario_aruco, parameters=parametros_aruco)
        except AttributeError:
            esquinas, ids, rechazados = [], None, []
    
    # Solo mostrar información esencial
    if ids is not None and len(ids) > 0:
        info_debug = f"ArUcos detectados: {len(ids)}"
        cv2.putText(imagen, info_debug, (10, imagen.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    
    return esquinas, ids, rechazados

def procesar_arucos(esquinas, ids, imagen, modo_ordenamiento="normal"):
    """Procesa múltiples ArUcos mostrando solo cuadritos verdes y ángulos de inclinación"""
    global proporcion_cm_por_pixel
    
    if ids is not None and len(ids) > 0:
        # Procesar cada ArUco detectado
        for i, (esquina, id_val) in enumerate(zip(esquinas, ids.flatten())):
            pts = esquina[0]
            
            # Dibujar solo los 4 cuadritos verdes en las esquinas
            for punto in pts:
                x, y = int(punto[0]), int(punto[1])
                # Cuadrito verde pequeño en cada esquina
                cv2.rectangle(imagen, (x-5, y-5), (x+5, y+5), (0, 255, 0), -1)
                cv2.rectangle(imagen, (x-6, y-6), (x+6, y+6), (0, 200, 0), 2)
            
            # Calcular centro del ArUco
            centro = np.mean(pts, axis=0).astype(int)
            
            # Calcular ángulo de inclinación
            dx = pts[1][0] - pts[0][0]
            dy = pts[1][1] - pts[0][1]
            angulo_rad = np.arctan2(dy, dx)
            angulo_deg = np.degrees(angulo_rad)
            
            # Mostrar ID y ángulo de inclinación de manera clara
            cv2.putText(imagen, f"ID:{id_val}", 
                       (centro[0] - 25, centro[1] - 15), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(imagen, f"ID:{id_val}", 
                       (centro[0] - 25, centro[1] - 15), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 1)
            
            cv2.putText(imagen, f"{angulo_deg:.1f}°", 
                       (centro[0] - 20, centro[1] + 10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(imagen, f"{angulo_deg:.1f}°", 
                       (centro[0] - 20, centro[1] + 10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
            
            # Línea de orientación del ArUco (opcional)
            punto_inicio = centro
            punto_fin = (int(centro[0] + 30 * np.cos(angulo_rad)), 
                        int(centro[1] + 30 * np.sin(angulo_rad)))
            cv2.arrowedLine(imagen, tuple(punto_inicio), punto_fin, (0, 255, 0), 2, tipLength=0.3)
        
        return len(ids), []
    else:
        # Mensaje simple cuando no hay ArUcos
        cv2.putText(imagen, "Busca ArUcos de madera...", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(imagen, "Busca ArUcos de madera...", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 1)
        
        return 0, []

def detectar_objetos_coloreados(imagen):
    """Función deshabilitada - Solo procesamos ArUcos de madera"""
    return [], None
    
    # Combinar máscaras
    mascara_colores = cv2.bitwise_or(mascara_rojo, mascara_verde)
    mascara_colores = cv2.bitwise_or(mascara_colores, mascara_azul)
    
    # Operaciones morfológicas para limpiar la máscara
    kernel = np.ones((5, 5), np.uint8)
    mascara_colores = cv2.morphologyEx(mascara_colores, cv2.MORPH_CLOSE, kernel)
    mascara_colores = cv2.morphologyEx(mascara_colores, cv2.MORPH_OPEN, kernel)
    
    # Encontrar contornos
    contornos, _ = cv2.findContours(mascara_colores, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Procesar contornos si tenemos referencia de ArUco
    objetos_detectados = []
    if proporcion_cm_por_pixel is not None:
        for contorno in contornos:
            area = cv2.contourArea(contorno)
            if area > 100:  # Filtrar objetos muy pequeños
                objeto_info = medir_objeto(contorno, imagen, proporcion_cm_por_pixel)
                if objeto_info:
                    objetos_detectados.append(objeto_info)
                    
                # Dibujar objeto básico (sin medidas detalladas)
                x, y, ancho, alto = cv2.boundingRect(contorno)
                centro_x, centro_y = x + ancho // 2, y + alto // 2
                cv2.rectangle(imagen, (x, y), (x + ancho, y + alto), (0, 255, 0), 2)
                cv2.circle(imagen, (centro_x, centro_y), 3, (0, 0, 255), -1)
    
    return objetos_detectados, mascara_colores

# =============================================================================
# CLASE PRINCIPAL DEL DETECTOR ARUCO
# =============================================================================

class DetectorAruco:
    """Clase principal para detección y procesamiento de ArUcos"""
    
    def __init__(self):
        self.capturando = False
        self.camara = None
        self.modo_ordenamiento = "normal"
        self.objetos_detectados = []
        
        # Variables para ajustes de imagen
        self.brillo = 100
        self.contraste = 100
        self.zoom = 100
        
        # Información del ArUco actual
        self.aruco_info = None
        
    def cambiar_diccionario(self, nuevo_diccionario):
        """Cambia el diccionario de ArUco"""
        global diccionario_aruco, detector_aruco, usar_nueva_api, proporcion_cm_por_pixel
        
        diccionario_aruco = aruco.getPredefinedDictionary(getattr(aruco, nuevo_diccionario))
        proporcion_cm_por_pixel = None  # Reiniciar proporción
        usar_nueva_api = crear_detector_aruco()
        
        print(f"Diccionario cambiado a: {nuevo_diccionario}")
        
    def aplicar_ajustes_imagen(self, imagen):
        """Aplica ajustes de brillo, contraste y zoom a la imagen"""
        # Aplicar brillo y contraste
        imagen_ajustada = cv2.convertScaleAbs(imagen, alpha=self.contraste/100.0, beta=self.brillo-100)
        
        # Aplicar zoom
        if self.zoom != 100:
            altura, ancho = imagen_ajustada.shape[:2]
            factor_zoom = self.zoom / 100.0
            nueva_altura = int(altura * factor_zoom)
            nuevo_ancho = int(ancho * factor_zoom)
            imagen_ajustada = cv2.resize(imagen_ajustada, (nuevo_ancho, nueva_altura))
            
            # Recortar al tamaño original si el zoom es mayor que 100%
            if factor_zoom > 1.0:
                inicio_y = (nueva_altura - altura) // 2
                inicio_x = (nuevo_ancho - ancho) // 2
                imagen_ajustada = imagen_ajustada[inicio_y:inicio_y+altura, inicio_x:inicio_x+ancho]
        
        return imagen_ajustada
        
    def iniciar_camara(self):
        """Inicia la captura de la cámara"""
        # Probar varios índices de cámara
       # camara_abierta = False
        #for idx in range(3):
        self.camara = cv2.VideoCapture(0)
        #    if self.camara.isOpened():
        #        camara_abierta = True
        #        print(f"Cámara abierta en índice {idx}")
        #        break
        #    else:
         #       self.camara.release()
                
        #if not camara_abierta:
        #    print("No se pudo abrir ninguna cámara (índices 0, 1, 2)")
         #   return False

        # Configurar propiedades de la cámara
        self.camara.set(cv2.CAP_PROP_FRAME_WIDTH, 720)
        self.camara.set(cv2.CAP_PROP_FRAME_HEIGHT, 580)
        self.camara.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        print("Cámara configurada exitosamente")
        return True
    
    def procesar_frame(self):
        """Procesa un frame de la cámara y retorna la imagen procesada"""
        if not self.camara or not self.camara.isOpened():
            return None
            
        exito, imagen = self.camara.read()
        if not exito or imagen is None:
            return None

        # Aplicar ajustes de imagen
        imagen = self.aplicar_ajustes_imagen(imagen)
        
        # Detectar objetos coloreados
        objetos_detectados, mascara_colores = detectar_objetos_coloreados(imagen)
        self.objetos_detectados = objetos_detectados
        
        # Detectar ArUcos
        esquinas, ids, rechazados = detectar_arucos(imagen)
        
        # Procesar ArUcos detectados
        num_arucos, arucos_info = procesar_arucos(esquinas, ids, imagen, self.modo_ordenamiento)
        
        return imagen, mascara_colores, num_arucos, arucos_info
    
    def actualizar_video_continuo(self, callback_actualizar=None):
        """Inicia el bucle de actualización continua de video"""
        self.capturando = True
        
        # Crear ventana de cámara
        cv2.namedWindow("Detector ArUco", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Detector ArUco", 640, 480)
        
        while self.capturando:
            resultado = self.procesar_frame()
            if resultado is None:
                threading.Event().wait(0.01)
                continue
                
            imagen, mascara_colores, num_arucos, arucos_info = resultado
            
            # Redimensionar imagen para visualización
            imagen_display = cv2.resize(imagen, (640, 480))
            
            # Mostrar información en la imagen
            info_texto = f"Modo: {self.modo_ordenamiento.upper()}"
            if num_arucos > 0:
                info_texto += f" - {num_arucos} ArUcos"
            cv2.putText(imagen_display, info_texto, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(imagen_display, info_texto, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 1)
            
            # Mostrar imagen
            cv2.imshow("Detector ArUco", imagen_display)
            
            # Llamar callback si se proporciona
            if callback_actualizar:
                callback_actualizar(imagen, mascara_colores, num_arucos, arucos_info)
            
            # Verificar teclas
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('1'):
                self.cambiar_modo_ordenamiento("normal")
            elif key == ord('2'):
                self.cambiar_modo_ordenamiento("mayor")
            elif key == ord('3'):
                self.cambiar_modo_ordenamiento("menor")
            elif key == ord('4'):
                self.cambiar_modo_ordenamiento("azar")

        self.detener_camara()
    
    def cambiar_modo_ordenamiento(self, nuevo_modo):
        """Cambia el modo de ordenamiento de ArUcos"""
        if nuevo_modo in ["normal", "mayor", "menor", "azar"]:
            self.modo_ordenamiento = nuevo_modo
            print(f"Modo de ordenamiento cambiado a: {nuevo_modo}")
    
    def detener_camara(self):
        """Detiene la captura de la cámara"""
        self.capturando = False
        if self.camara:
            self.camara.release()
        cv2.destroyAllWindows()
        print("Cámara detenida")
    
    def capturar_imagen(self, nombre_archivo=None):
        """Captura una imagen actual y la guarda"""
        resultado = self.procesar_frame()
        if resultado is None:
            return None
            
        imagen, _, _, _ = resultado
        
        if nombre_archivo:
            cv2.imwrite(nombre_archivo, imagen)
            print(f"Imagen guardada como: {nombre_archivo}")
        
        return imagen
    
    def obtener_estado(self):
        """Retorna el estado actual del detector"""
        return {
            'capturando': self.capturando,
            'modo_ordenamiento': self.modo_ordenamiento,
            'num_objetos_detectados': len(self.objetos_detectados),
            'proporcion_cm_por_pixel': proporcion_cm_por_pixel,
            'brillo': self.brillo,
            'contraste': self.contraste,
            'zoom': self.zoom
        }

# =============================================================================
# CLASE DE INTERFAZ GRÁFICA PRINCIPAL MEJORADA
# =============================================================================

class InterfazDetectorAruco:
    """Interfaz gráfica principal para el detector de ArUco"""
    
    def __init__(self, ventana_padre=None):
        # Crear ventana principal si no se proporciona
        if ventana_padre is None:
            self.ventana = tk.Tk()
            self.ventana.title("Detector ArUco - Control Principal")
        else:
            self.ventana = tk.Toplevel(ventana_padre)
            self.ventana.title("Detector ArUco")
        
        self.ventana.geometry("900x700")
        self.ventana.resizable(True, True)
        
        # Crear detector
        self.detector = DetectorAruco()
        
        # Variables de interfaz
        self.hilo_camara = None
        self.camara_activa = False
        
        # Variables para diccionarios ArUco
        self.var_diccionario = tk.StringVar(value="DICT_4X4_100")
        
        # Crear interfaz
        self.crear_interfaz()
        
    def crear_interfaz(self):
        """Crea la interfaz gráfica mejorada"""
        # Frame principal con scroll
        canvas = tk.Canvas(self.ventana)
        scrollbar = ttk.Scrollbar(self.ventana, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Frame principal dentro del scrollable
        frame_principal = ttk.Frame(scrollable_frame, padding="15")
        frame_principal.pack(fill=tk.BOTH, expand=True)
        
        # TÍTULO PRINCIPAL
        titulo = ttk.Label(frame_principal, text="🎯 DETECTOR ARUCO - CONTROL PRINCIPAL", 
                          font=("Arial", 16, "bold"), foreground="blue")
        titulo.pack(pady=(0, 20))
        
        # ==================== SECCIÓN TIPO DE ARUCO ====================
        frame_aruco_tipo = ttk.LabelFrame(frame_principal, text="📐 Tipo de ArUco", padding="10")
        frame_aruco_tipo.pack(fill=tk.X, pady=(0, 15))
        
        # Opciones de diccionario con radiobuttons
        opciones_diccionario = [
            ("🔹 3x3 (Original)", "DICT_ARUCO_ORIGINAL"),
            ("🔸 4x4 (100 marcadores)", "DICT_4X4_100"),
            ("🔹 5x5 (100 marcadores)", "DICT_5X5_100"),
            ("🔸 6x6 (100 marcadores)", "DICT_6X6_100"),
            ("🔹 7x7 (100 marcadores)", "DICT_7X7_100")
        ]
        
        # Crear radiobuttons en dos filas
        fila1 = ttk.Frame(frame_aruco_tipo)
        fila1.pack(fill=tk.X, pady=5)
        fila2 = ttk.Frame(frame_aruco_tipo)
        fila2.pack(fill=tk.X, pady=5)
        
        for i, (texto, valor) in enumerate(opciones_diccionario):
            frame_target = fila1 if i < 3 else fila2
            radio = ttk.Radiobutton(frame_target, text=texto, variable=self.var_diccionario, 
                                   value=valor, command=self.cambiar_diccionario_aruco)
            radio.pack(side=tk.LEFT, padx=10, pady=2)
        
        # ==================== SECCIÓN CONTROL DE CÁMARA ====================
        frame_camara = ttk.LabelFrame(frame_principal, text="📷 Control de Cámara", padding="10")
        frame_camara.pack(fill=tk.X, pady=(0, 15))
        
        # Botones de cámara
        botones_camara = ttk.Frame(frame_camara)
        botones_camara.pack(fill=tk.X)
        
        self.btn_iniciar_camara = ttk.Button(botones_camara, text="▶️ Iniciar Cámara", 
                                           command=self.iniciar_camara, style="Accent.TButton")
        self.btn_iniciar_camara.pack(side=tk.LEFT, padx=5)
        
        self.btn_detener_camara = ttk.Button(botones_camara, text="⏹️ Detener Cámara", 
                                           command=self.detener_camara, state=tk.DISABLED)
        self.btn_detener_camara.pack(side=tk.LEFT, padx=5)
        
        self.btn_capturar = ttk.Button(botones_camara, text="📸 Capturar Imagen", 
                                     command=self.capturar_imagen, state=tk.DISABLED)
        self.btn_capturar.pack(side=tk.LEFT, padx=5)
        
        # ==================== SECCIÓN OPTIMIZACIÓN DE DETECCIÓN ====================
        frame_optimizacion = ttk.LabelFrame(frame_principal, text="🎯 Detección de Precisión para ArUcos de Madera", padding="15")
        frame_optimizacion.pack(fill=tk.X, pady=(0, 15))
        
        # Descripción
        desc_opt = ttk.Label(frame_optimizacion, text="Optimización automática para detectar múltiples ArUcos de madera con máxima precisión:", 
                            font=("Arial", 10, "bold"))
        desc_opt.pack(pady=(0, 15))
        
        # Botones de optimización
        botones_opt = ttk.Frame(frame_optimizacion)
        botones_opt.pack(fill=tk.X)
        
        # Opciones de optimización - Solo precisión
        opciones_opt = [
            ("🎯 Precisión", "alta_precision", "Detección precisa multi-ArUco")
        ]
        
        for i, (texto, modo, descripcion) in enumerate(opciones_opt):
            frame_opt = ttk.Frame(botones_opt)
            frame_opt.pack(side=tk.LEFT, padx=8, pady=5)
            
            btn = ttk.Button(frame_opt, text=texto, 
                           command=lambda m=modo: self.optimizar_deteccion(m))
            btn.pack()
            
            desc = ttk.Label(frame_opt, text=descripcion, font=("Arial", 7), foreground="gray")
            desc.pack()
        

        
        # ==================== SECCIÓN VISTA DE CÁMARA ====================
        frame_video = ttk.LabelFrame(frame_principal, text="📹 Vista de Cámara", padding="10")
        frame_video.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # Frame contenedor para el video
        video_container = ttk.Frame(frame_video)
        video_container.pack(expand=True, fill=tk.BOTH)
        
        # Canvas para mostrar el video
        self.canvas_video = tk.Canvas(video_container, width=640, height=480, bg="black")
        self.canvas_video.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)
        
        # Texto inicial en el canvas
        self.canvas_video.create_text(320, 240, text="📷 Cámara no iniciada\nPresiona 'Iniciar Cámara' para comenzar", 
                                    fill="white", font=("Arial", 14), justify="center", tags="texto_inicial")
        
        # ==================== BOTONES PRINCIPALES ====================
        frame_botones_principales = ttk.Frame(frame_principal)
        frame_botones_principales.pack(fill=tk.X, pady=20)
        
        ttk.Button(frame_botones_principales, text="❌ Cerrar", 
                  command=self.cerrar_aplicacion).pack(side=tk.RIGHT, padx=5)
        
        # Información básica de estado
        self.lbl_estado_simple = ttk.Label(frame_botones_principales, text="Estado: Cámara no iniciada", 
                                         font=("Arial", 10), foreground="gray")
        self.lbl_estado_simple.pack(side=tk.LEFT, padx=10)
        
        # Configurar canvas y scrollbar
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Configurar expansión
        self.ventana.columnconfigure(0, weight=1)
        self.ventana.rowconfigure(0, weight=1)
        
    def cambiar_diccionario_aruco(self):
        """Cambia el diccionario de ArUco seleccionado"""
        seleccion = self.var_diccionario.get()
        self.detector.cambiar_diccionario(seleccion)
        
        # Actualizar label de información
        nombres_diccionarios = {
            "DICT_ARUCO_ORIGINAL": "3x3 (Original)",
            "DICT_4X4_100": "4x4 (100 marcadores)",
            "DICT_5X5_100": "5x5 (100 marcadores)",
            "DICT_6X6_100": "6x6 (100 marcadores)",
            "DICT_7X7_100": "7x7 (100 marcadores)"
        }
        nombre = nombres_diccionarios.get(seleccion, seleccion)
        self.lbl_diccionario_actual.config(text=f"📐 ArUco: {nombre}")
        print(f"Diccionario cambiado a: {nombre}")
    
    def iniciar_camara(self):
        """Inicia la cámara y el procesamiento con interfaz simplificada"""
        if self.detector.iniciar_camara():
            self.camara_activa = True
            
            # Limpiar texto inicial del canvas
            self.canvas_video.delete("texto_inicial")
            
            # Iniciar procesamiento de video
            self.actualizar_frame_tkinter()
            
            # Actualizar botones y estado
            self.btn_iniciar_camara.config(state=tk.DISABLED)
            self.btn_detener_camara.config(state=tk.NORMAL)
            self.btn_capturar.config(state=tk.NORMAL)
            self.lbl_estado_simple.config(text="Estado: Cámara ACTIVA", foreground="green")
            print("Cámara iniciada desde interfaz")
        else:
            self.lbl_estado_simple.config(text="Estado: Error al iniciar cámara", foreground="red")
            messagebox.showerror("Error", "No se pudo iniciar la cámara")
    

    
    def actualizar_frame_tkinter(self):
        """Actualiza el frame de la cámara en la interfaz Tkinter"""
        if not self.camara_activa:
            return
            
        try:
            resultado = self.detector.procesar_frame()
            if resultado is None:
                # Programar la próxima actualización
                self.ventana.after(30, self.actualizar_frame_tkinter)
                return
                
            imagen, mascara_colores, num_arucos, arucos_info = resultado
            
            # Redimensionar imagen para el canvas
            imagen_display = cv2.resize(imagen, (640, 480))
            
            # Solo mostrar información del modo si hay ArUcos detectados
            if num_arucos > 0:
                info_texto = f"PRECISIÓN | ArUcos: {num_arucos}"
                cv2.putText(imagen_display, info_texto, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                cv2.putText(imagen_display, info_texto, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 1)
            
            # Convertir imagen de OpenCV (BGR) a formato que Tkinter puede mostrar (RGB)
            imagen_rgb = cv2.cvtColor(imagen_display, cv2.COLOR_BGR2RGB)
            imagen_pil = Image.fromarray(imagen_rgb)
            imagen_tk = ImageTk.PhotoImage(imagen_pil)
            
            # Actualizar canvas
            self.canvas_video.delete("all")
            self.canvas_video.create_image(320, 240, image=imagen_tk)
            self.canvas_video.image = imagen_tk  # Mantener referencia
            
            # Actualizar estado simple
            estado_texto = f"Activa - Modo: {self.detector.modo_ordenamiento}"
            if num_arucos > 0:
                estado_texto += f" | {num_arucos} ArUcos"
            self.lbl_estado_simple.config(text=estado_texto, foreground="green")
            
            # Programar la próxima actualización
            self.ventana.after(30, self.actualizar_frame_tkinter)
            
        except tk.TclError:
            # La ventana fue cerrada, detener procesamiento
            self.camara_activa = False
        except Exception as e:
            print(f"Error en actualización de frame: {e}")
            # Programar la próxima actualización de todas formas
            self.ventana.after(30, self.actualizar_frame_tkinter)
    

    
    def detener_camara(self):
        """Detiene la cámara con interfaz simplificada"""
        self.camara_activa = False
        self.detector.detener_camara()
        
        # Limpiar canvas y mostrar mensaje
        self.canvas_video.delete("all")
        self.canvas_video.create_text(320, 240, text="📷 Cámara detenida\nPresiona 'Iniciar Cámara' para reanudar", 
                                    fill="white", font=("Arial", 14), justify="center", tags="texto_inicial")
        
        # Actualizar botones y estado
        self.btn_iniciar_camara.config(state=tk.NORMAL)
        self.btn_detener_camara.config(state=tk.DISABLED)
        self.btn_capturar.config(state=tk.DISABLED)
        self.lbl_estado_simple.config(text="Estado: Cámara DETENIDA", foreground="red")
        print("Cámara detenida desde interfaz")
    
    def capturar_imagen(self):
        """Captura una imagen con interfaz mejorada"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        nombre_archivo = f"captura_aruco_{timestamp}.jpg"
        imagen = self.detector.capturar_imagen(nombre_archivo)
        if imagen is not None:
            messagebox.showinfo("📸 Captura Exitosa", f"Imagen guardada como:\n{nombre_archivo}")
        else:
            messagebox.showwarning("⚠️ Error", "No se pudo capturar la imagen")
    
    def cambiar_modo(self, modo):
        """Cambia el modo de ordenamiento con interfaz mejorada"""
        self.detector.cambiar_modo_ordenamiento(modo)
        
        # Actualizar información
        nombres_modos = {
            "normal": "🔵 Normal",
            "mayor": "🔴 Mayor → Menor",
            "menor": "🟢 Menor → Mayor",
            "azar": "🟣 Al Azar"
        }
        nombre = nombres_modos.get(modo, modo.upper())
        self.lbl_modo_actual.config(text=f"🔄 Modo: {nombre}")
        print(f"Modo cambiado a: {nombre}")
    
    def cambiar_modo(self, modo):
        """Cambia el modo de ordenamiento"""
        self.detector.cambiar_modo_ordenamiento(modo)
        print(f"Modo cambiado a: {modo}")
    
    def optimizar_deteccion(self, condiciones):
        """Optimiza los parámetros de detección según las condiciones"""
        optimizar_parametros_deteccion(condiciones)
        
        # Actualizar el diccionario también para aplicar los cambios
        self.detector.cambiar_diccionario(self.var_diccionario.get())
        
        print(f"Detección optimizada para: {condiciones}")
        
        # Mostrar mensaje informativo
        mensajes = {
            "baja_luz": "Optimizado para condiciones de poca luz",
            "normal": "Configuración balanceada activada", 
            "alta_precision": "Modo de alta precisión activado",
            "rapido": "Modo de detección rápida activado"
        }
        
        if hasattr(self, 'lbl_estado_simple'):
            texto_anterior = self.lbl_estado_simple.cget("text")
            self.lbl_estado_simple.config(text=mensajes.get(condiciones, "Detección optimizada"))
            # Restaurar el texto anterior después de 3 segundos
            self.ventana.after(3000, lambda: self.lbl_estado_simple.config(text=texto_anterior))
    
    def cambiar_diccionario_aruco(self):
        """Cambia el diccionario ArUco seleccionado"""
        nuevo_dict = self.var_diccionario.get()
        self.detector.cambiar_diccionario(nuevo_dict)
        print(f"Diccionario cambiado a: {nuevo_dict}")
    
    def capturar_imagen(self):
        """Captura una imagen de la cámara"""
        if self.camara_activa:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            nombre_archivo = f"captura_aruco_{timestamp}.jpg"
            imagen = self.detector.capturar_imagen(nombre_archivo)
            if imagen is not None:
                messagebox.showinfo("📸 Captura", f"Imagen guardada como:\n{nombre_archivo}")
        else:
            messagebox.showwarning("⚠️ Advertencia", "Inicia la cámara primero")
    
    def cerrar_aplicacion(self):
        """Cierra la aplicación de forma segura"""
        if self.camara_activa:
            self.detener_camara()
        
        try:
            self.ventana.quit()
            self.ventana.destroy()
        except:
            pass
        
        print("Aplicación cerrada")
    

# =============================================================================
# FUNCIÓN PRINCIPAL PARA EJECUTAR EL DETECTOR INDEPENDIENTE
# =============================================================================

def main():
    """Función principal - ahora abre la interfaz gráfica por defecto"""
    print("=== DETECTOR ARUCO - INTERFAZ GRÁFICA ===")
    main_gui()

def main_gui():
    """Función principal para ejecutar la interfaz gráfica simplificada"""
    try:
        # Crear aplicación principal
        app = InterfazDetectorAruco()
        
        # Configurar cierre
        def on_closing():
            app.cerrar_aplicacion()
        
        app.ventana.protocol("WM_DELETE_WINDOW", on_closing)
        
        # Mostrar ventana centrada
        app.ventana.update_idletasks()
        width = app.ventana.winfo_width()
        height = app.ventana.winfo_height()
        x = (app.ventana.winfo_screenwidth() // 2) - (width // 2)
        y = (app.ventana.winfo_screenheight() // 2) - (height // 2)
        app.ventana.geometry(f'+{x}+{y}')
        
        print("Interfaz gráfica iniciada correctamente")
        app.ventana.mainloop()
        
    except Exception as e:
        print(f"Error al iniciar interfaz gráfica: {e}")

# =============================================================================
# EJECUCIÓN INDEPENDIENTE
# =============================================================================

if __name__ == "__main__":
    main()