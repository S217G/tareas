
# =============================================================================
# IMPORTACIONES
# =============================================================================

import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk, ImageOps
import time
import os

# Importar funcionalidades del láser
try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None

# =============================================================================
# FUNCIONES DEL LÁSER - COMUNICACIÓN SERIAL
# =============================================================================

WAKE_DELAY = 2.0  # s

def open_serial(port: str, baud: int = 115200, timeout: float = 1.0):
    """Abre conexión serial para el láser"""
    if serial is None:
        raise RuntimeError("pyserial no está instalado. Instala con: pip install pyserial")
    ser = serial.Serial(port, baudrate=baud, timeout=timeout)
    ser.write(b"\r\n\r\n")
    time.sleep(WAKE_DELAY)
    ser.reset_input_buffer()
    return ser

def _readline(ser):
    """Lee una línea del puerto serial"""
    raw = ser.readline()
    return raw.decode(errors="ignore").strip() if raw else ""

def send_cmd(ser, cmd: str) -> str:
    """Envía una línea y espera 'ok' / 'error' / 'ALARM'."""
    cmd = cmd.strip()
    if not cmd:
        return "ok"
    ser.write((cmd + "\n").encode())
    while True:
        line = _readline(ser)
        if not line:
            continue
        L = line.lower()
        if line == "ok" or L.startswith("error") or line.upper().startswith("ALARM"):
            return line

def mm_per_pixel(ppmm: float) -> float:
    """Convierte píxeles por mm a mm por píxel"""
    return 1.0 / float(ppmm)

def to_grayscale(img: Image.Image, invert: bool) -> Image.Image:
    """Convierte imagen a escala de grises"""
    g = ImageOps.grayscale(img)
    if invert:
        g = ImageOps.invert(g)
    return g

# =============================================================================
# FUNCIONES DEL LÁSER - PROCESAMIENTO DE IMÁGENES
# =============================================================================

def prepare_image(path: str, size_mm, ppmm: float, invert: bool, mode: str) -> Image.Image:
    """Prepara imagen para grabado láser"""
    w_mm, h_mm = size_mm
    target_px = (int(round(w_mm * ppmm)), int(round(h_mm * ppmm)))

    img = Image.open(path).convert("L")
    img = img.resize(target_px, Image.Resampling.LANCZOS)

    if mode == "threshold":
        if invert:
            img = ImageOps.invert(img)
        bw = img.point(lambda p: 0 if p < 128 else 255, "1")
        return bw

    if mode == "dither":
        g = to_grayscale(img.convert("RGB"), invert)
        return g.convert("1")

    return to_grayscale(img.convert("RGB"), invert)

def gamma_correct(v: float, gamma: float) -> float:
    """Aplica corrección gamma"""
    return pow(max(0.0, min(1.0, v)), gamma)

# =============================================================================
# FUNCIONES DEL LÁSER - GENERACIÓN DE GCODE
# =============================================================================

def raster_to_gcode(img: Image.Image, *, ppmm: float, origin, f_engrave: float, 
                   f_travel: float, s_max: int, mode: str, gamma_val: float):
    """Convierte imagen raster a G-code"""
    px_w, px_h = img.size
    step = mm_per_pixel(ppmm)
    ox, oy = origin

    OVERSCAN_MM = 0.6
    S_FIXED = s_max

    yield ";; --- BEGIN ---"
    yield "G21"
    yield "G90"
    yield "M5"
    yield f"F{f_travel:.4f}"

    for row in range(px_h):
        y_mm = oy + (px_h - 1 - row) * step

        if row % 2 == 0:
            x_range = range(0, px_w)
        else:
            x_range = range(px_w - 1, -1, -1)

        first_x = x_range.start if isinstance(x_range, range) else x_range[0]
        x0_mm = ox + first_x * step
        yield f"G0 X{(x0_mm - OVERSCAN_MM):.4f} Y{y_mm:.4f}"
        yield f"F{f_engrave:.4f}"

        def pixel_intensity(col: int) -> float:
            if img.mode == "1":
                return 1.0 if img.getpixel((col, row)) == 0 else 0.0
            else:
                return (255 - img.getpixel((col, row))) / 255.0

        seg_start = None
        seg_power = None

        for x in x_range:
            inten = pixel_intensity(x)

            if mode == "grayscale":
                p = gamma_correct(inten, gamma_val)
                s_val = int(round(p * s_max))
                if s_val > 0 and s_val < 50:
                    s_val = 50

                if s_val > 0:
                    if seg_start is None:
                        seg_start = x
                        seg_power = None
                    if seg_power != s_val:
                        yield f"M4 S{s_val}"
                        seg_power = s_val
                    x_mm = ox + x * step
                    yield f"G1 X{x_mm:.4f} Y{y_mm:.4f}"
                else:
                    if seg_start is not None:
                        x_mm = ox + x * step
                        yield f"G1 X{(x_mm + OVERSCAN_MM):.4f} Y{y_mm:.4f}"
                        yield "M5"
                        seg_start = None
                        seg_power = None
            else:
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

        yield f"F{f_travel:.4f}"

    yield "M5"
    yield ";; --- END ---"

def stream_to_grbl(ser, gcode_text: str) -> int:
    """Envía G-code a GRBL"""
    send_cmd(ser, "$X")
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
            send_cmd(ser, "M5")
            break

    send_cmd(ser, "M5")
    return 0 if errors == 0 else 2

def move_to_offset_and_set_origin(ser, dx: float = 0.0, dy: float = 0.0, feed: int = 1000):
    """Mueve a offset y establece origen"""
    send_cmd(ser, "G90")
    send_cmd(ser, "G91")
    parts = []
    if abs(dx) > 0: parts.append(f"X{dx}")
    if abs(dy) > 0: parts.append(f"Y{dy}")
    if parts:
        send_cmd(ser, f"G1 {' '.join(parts)} F{int(feed)}")
    send_cmd(ser, "G90")
    send_cmd(ser, "G92 X0 Y0")

def move_back_to_machine_origin(ser):
    """Retorna al origen de máquina"""
    send_cmd(ser, "G92.1")
    send_cmd(ser, "G90")
    send_cmd(ser, "G53 G0 X0 Y0")

def generate_gcode_text(*, image_path: str, size_mm, ppmm: float, mode: str, 
                       invert: bool, gamma_val: float, origin_xy, f_engrave: float, 
                       f_travel: float, s_max: int) -> str:
    """Genera G-code completo para una imagen"""
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

# =============================================================================
# VENTANA PRINCIPAL DEL LÁSER
# =============================================================================

class VentanaLaser:
    def __init__(self, parent=None):
        if parent:
            self.ventana = tk.Toplevel(parent)
        else:
            self.ventana = tk.Tk()
        
        self.ventana.title("Control del Láser CNC")
        self.ventana.geometry("520x700")
        self.ventana.resizable(True, True)
        
        # Variables del láser
        self.ser_laser = None
        self.laser_port = tk.StringVar(value="COM1")
        self.laser_baud = tk.StringVar(value="115200")
        self.selected_image = tk.StringVar(value="No hay imagen seleccionada")
        self.image_path = None
        self.laser_inicializado = False
        
        # Parámetros de grabado
        self.size_mm_x = tk.DoubleVar(value=20.0)
        self.size_mm_y = tk.DoubleVar(value=20.0)
        self.ppmm = tk.DoubleVar(value=5.0)
        self.f_engrave = tk.DoubleVar(value=1000.0)
        self.f_travel = tk.DoubleVar(value=1000.0)
        self.s_max = tk.IntVar(value=480)
        self.gamma_val = tk.DoubleVar(value=0.6)
        self.offset_x = tk.DoubleVar(value=0.0)
        self.offset_y = tk.DoubleVar(value=0.0)
        self.mode = tk.StringVar(value="grayscale")
        self.invert = tk.BooleanVar(value=False)
        
        self.crear_interfaz_laser()
        
    def crear_interfaz_laser(self):
        # Frame principal
        main_frame = ttk.Frame(self.ventana, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Conexión del láser
        conn_frame = ttk.LabelFrame(main_frame, text="Conexión del Láser", padding="5")
        conn_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(conn_frame, text="Puerto:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        puerto_combo = ttk.Combobox(conn_frame, textvariable=self.laser_port, 
                                   values=self.obtener_puertos_disponibles(), width=10)
        puerto_combo.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(conn_frame, text="Baudrate:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        baud_combo = ttk.Combobox(conn_frame, textvariable=self.laser_baud,
                                 values=["9600", "19200", "38400", "57600", "115200"], width=10)
        baud_combo.grid(row=0, column=3, padx=5, pady=5)
        
        ttk.Button(conn_frame, text="Conectar", command=self.conectar_laser).grid(row=0, column=4, padx=5, pady=5)
      #  ttk.Button(conn_frame, text="Desconectar", command=self.desconectar_laser).grid(row=0, column=5, padx=5, pady=5)
        ttk.Button(conn_frame, text="Actualizar Puertos", command=self.actualizar_puertos).grid(row=0, column=6, padx=5, pady=5)
        
        # Selección de imagen
        img_frame = ttk.LabelFrame(main_frame, text="Selección de Imagen", padding="5")
        img_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(img_frame, textvariable=self.selected_image).pack(side=tk.LEFT, padx=5)
        ttk.Button(img_frame, text="Seleccionar Imagen", command=self.seleccionar_imagen).pack(side=tk.RIGHT, padx=5)
        ttk.Button(img_frame, text="Inicializar Láser", command=self.inicializar_laser).pack(side=tk.RIGHT, padx=(5, 10))
        
        # Parámetros de grabado
        params_frame = ttk.LabelFrame(main_frame, text="Parámetros de Grabado", padding="5")
        params_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Tamaño
        size_frame = ttk.Frame(params_frame)
        size_frame.pack(fill=tk.X, pady=2)
        ttk.Label(size_frame, text="Tamaño (mm):").pack(side=tk.LEFT)
        ttk.Label(size_frame, text="X:").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Entry(size_frame, textvariable=self.size_mm_x, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Label(size_frame, text="Y:").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Entry(size_frame, textvariable=self.size_mm_y, width=8).pack(side=tk.LEFT, padx=2)
        
        # Resolución
        res_frame = ttk.Frame(params_frame)
        res_frame.pack(fill=tk.X, pady=2)
        ttk.Label(res_frame, text="Píxeles por mm:").pack(side=tk.LEFT)
        ttk.Entry(res_frame, textvariable=self.ppmm, width=8).pack(side=tk.LEFT, padx=(10, 0))
        
        # Velocidades
        vel_frame = ttk.Frame(params_frame)
        vel_frame.pack(fill=tk.X, pady=2)
        ttk.Label(vel_frame, text="Vel. grabado:").pack(side=tk.LEFT)
        ttk.Entry(vel_frame, textvariable=self.f_engrave, width=8).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Label(vel_frame, text="Vel. viaje:").pack(side=tk.LEFT, padx=(15, 0))
        ttk.Entry(vel_frame, textvariable=self.f_travel, width=8).pack(side=tk.LEFT, padx=(5, 0))
        
        # Potencia y gamma
        power_frame = ttk.Frame(params_frame)
        power_frame.pack(fill=tk.X, pady=2)
        ttk.Label(power_frame, text="Potencia máx:").pack(side=tk.LEFT)
        ttk.Entry(power_frame, textvariable=self.s_max, width=8).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Label(power_frame, text="Gamma:").pack(side=tk.LEFT, padx=(15, 0))
        ttk.Entry(power_frame, textvariable=self.gamma_val, width=8).pack(side=tk.LEFT, padx=(5, 0))
        
        # Offset
        offset_frame = ttk.Frame(params_frame)
        offset_frame.pack(fill=tk.X, pady=2)
        ttk.Label(offset_frame, text="Offset (mm):").pack(side=tk.LEFT)
        ttk.Label(offset_frame, text="X:").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Entry(offset_frame, textvariable=self.offset_x, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Label(offset_frame, text="Y:").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Entry(offset_frame, textvariable=self.offset_y, width=8).pack(side=tk.LEFT, padx=2)
        
        # Modo y opciones
        mode_frame = ttk.Frame(params_frame)
        mode_frame.pack(fill=tk.X, pady=2)
        ttk.Label(mode_frame, text="Modo:").pack(side=tk.LEFT)
        mode_combo = ttk.Combobox(mode_frame, textvariable=self.mode,
                                 values=["grayscale", "threshold", "dither"], width=12)
        mode_combo.pack(side=tk.LEFT, padx=(5, 0))
        ttk.Checkbutton(mode_frame, text="Invertir", variable=self.invert).pack(side=tk.LEFT, padx=(15, 0))
        
        # Log del láser
        log_frame = ttk.LabelFrame(main_frame, text="Log del Láser", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Crear frame para el text widget y scrollbar
        text_frame = ttk.Frame(log_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        self.laser_log = tk.Text(text_frame, height=12, state=tk.DISABLED, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.laser_log.yview)
        self.laser_log.configure(yscrollcommand=scrollbar.set)
        
        self.laser_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Botones de control
        control_frame = ttk.LabelFrame(main_frame, text="Controles", padding="10")
        control_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Primera fila de botones
        control_row1 = ttk.Frame(control_frame)
        control_row1.pack(fill=tk.X, pady=(0, 5))
        
      #  ttk.Button(control_row1, text="Generar G-Code", command=self.generar_gcode, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_row1, text="Iniciar Grabado", command=self.iniciar_grabado, width=15).pack(side=tk.LEFT, padx=5)
        # ttk.Button(control_row1, text="Parar Láser", command=self.parar_laser, width=15).pack(side=tk.LEFT, padx=5)
        
        # Segunda fila de botones
        control_row2 = ttk.Frame(control_frame)
        control_row2.pack(fill=tk.X)
        
        ttk.Button(control_row2, text="Mover al Origen", command=self.mover_origen, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_row2, text="Limpiar Log", command=self.limpiar_log, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_row2, text="Cerrar", command=self.cerrar_ventana, width=15).pack(side=tk.LEFT, padx=5)
    
    def obtener_puertos_disponibles(self):
        """Obtiene lista de puertos COM disponibles"""
        if serial is None:
            return ["COM1", "COM2", "COM3", "COM4", "COM5"]
        
        puertos = []
        for puerto in serial.tools.list_ports.comports():
            puertos.append(puerto.device)
        
        return puertos if puertos else ["COM1", "COM2", "COM3", "COM4", "COM5"]
    
    def actualizar_puertos(self):
        """Actualiza la lista de puertos disponibles"""
        puerto_combo = None
        for widget in self.ventana.winfo_children():
            if isinstance(widget, ttk.Frame):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.LabelFrame) and child.cget("text") == "Conexión del Láser":
                        for grandchild in child.winfo_children():
                            if isinstance(grandchild, ttk.Combobox) and grandchild.cget("textvariable") == str(self.laser_port):
                                puerto_combo = grandchild
                                break
        
        if puerto_combo:
            puerto_combo['values'] = self.obtener_puertos_disponibles()
            self.log_laser("🔄 Lista de puertos actualizada")
    
    def log_laser(self, mensaje):
        """Añade mensaje al log del láser"""
        self.laser_log.config(state=tk.NORMAL)
        self.laser_log.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {mensaje}\n")
        self.laser_log.see(tk.END)
        self.laser_log.config(state=tk.DISABLED)
        
    def conectar_laser(self):
        """Conecta al láser"""
        try:
            if self.ser_laser and getattr(self.ser_laser, "is_open", False):
                self.log_laser("Ya conectado al láser")
                return
                
            port = self.laser_port.get()
            baud = int(self.laser_baud.get())
            self.ser_laser = open_serial(port, baud)
            self.log_laser(f"✅ Conectado al láser en {port} @ {baud}")
            
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo conectar al láser:\n{e}")
            self.log_laser(f"❌ Error de conexión: {e}")
            
    def desconectar_laser(self):
        """Desconecta del láser"""
        try:
            if self.ser_laser and getattr(self.ser_laser, "is_open", False):
                send_cmd(self.ser_laser, "M5")  # Apagar láser
                self.ser_laser.close()
                self.log_laser("🔌 Láser desconectado")
            self.laser_inicializado = False
        except Exception as e:
            self.log_laser(f"Error al desconectar: {e}")
            self.laser_inicializado = False
            
    def seleccionar_imagen(self):
        """Selecciona archivo de imagen"""
        archivo = filedialog.askopenfilename(
            title="Seleccionar imagen",
            filetypes=[
                ("Imágenes", "*.png *.jpg *.jpeg *.bmp *.gif"),
                ("Todos los archivos", "*.*")
            ]
        )
        if archivo:
            self.image_path = archivo
            nombre = os.path.basename(archivo)
            self.selected_image.set(f"Imagen: {nombre}")
            self.log_laser(f"📁 Imagen seleccionada: {nombre}")
            
    def inicializar_laser(self):
        """Inicializa el láser después de seleccionar imagen"""
        if not self.image_path:
            messagebox.showwarning("Advertencia", "Selecciona una imagen primero")
            return
            
        if not self.ser_laser or not getattr(self.ser_laser, "is_open", False):
            messagebox.showwarning("Advertencia", "Conecta al láser primero")
            return
            
        try:
            self.log_laser("🔧 Inicializando láser...")
            
            # Comandos de inicialización del láser
            send_cmd(self.ser_laser, "$X")  # Desbloquear alarmas
            send_cmd(self.ser_laser, "G21")  # Unidades en milímetros
            send_cmd(self.ser_laser, "G90")  # Coordenadas absolutas
            send_cmd(self.ser_laser, "M5")   # Láser apagado
            
            # Mover a posición de offset si está configurado
            if abs(self.offset_x.get()) > 0 or abs(self.offset_y.get()) > 0:
                self.log_laser("📍 Moviendo a posición de trabajo...")
                move_to_offset_and_set_origin(
                    self.ser_laser, 
                    dx=self.offset_x.get(), 
                    dy=self.offset_y.get(), 
                    feed=1000
                )
                self.log_laser(f"✅ Posicionado en offset X:{self.offset_x.get()}, Y:{self.offset_y.get()}")
            else:
                self.log_laser("✅ Láser inicializado en origen (0,0)")
                
            # Marcar como inicializado
            self.laser_inicializado = True
            self.log_laser("🎯 Láser listo para grabar - Presiona 'Iniciar Grabado' cuando estés listo")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error inicializando láser:\n{e}")
            self.log_laser(f"❌ Error en inicialización: {e}")
            self.laser_inicializado = False
            
    def generar_gcode(self):
        """Genera G-code para la imagen seleccionada"""
        if not self.image_path:
            messagebox.showwarning("Advertencia", "Selecciona una imagen primero")
            return
            
        try:
            self.log_laser("⚙️ Generando G-code...")
            size_mm = (self.size_mm_x.get(), self.size_mm_y.get())
            
            gcode = generate_gcode_text(
                image_path=self.image_path,
                size_mm=size_mm,
                ppmm=self.ppmm.get(),
                mode=self.mode.get(),
                invert=self.invert.get(),
                gamma_val=self.gamma_val.get(),
                origin_xy=(0.0, 0.0),
                f_engrave=self.f_engrave.get(),
                f_travel=self.f_travel.get(),
                s_max=self.s_max.get()
            )
            
            # Guardar G-code en archivo
            gcode_file = filedialog.asksaveasfilename(
                title="Guardar G-code",
                defaultextension=".gcode",
                filetypes=[("G-code", "*.gcode"), ("Texto", "*.txt")]
            )
            
            if gcode_file:
                with open(gcode_file, 'w') as f:
                    f.write(gcode)
                self.log_laser(f"✅ G-code guardado en: {os.path.basename(gcode_file)}")
                self.log_laser(f"📊 Líneas de código: {len(gcode.splitlines())}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error generando G-code:\n{e}")
            self.log_laser(f"❌ Error generando G-code: {e}")
            
    def iniciar_grabado(self):
        """Inicia el proceso de grabado después de la inicialización"""
        if not self.image_path:
            messagebox.showwarning("Advertencia", "Selecciona una imagen primero")
            return
            
        if not self.ser_laser or not getattr(self.ser_laser, "is_open", False):
            messagebox.showwarning("Advertencia", "Conecta al láser primero")
            return
            
        if not self.laser_inicializado:
            messagebox.showwarning("Advertencia", "Inicializa el láser primero con el botón 'Inicializar Láser'")
            return
            
        # Verificar que el láser esté en posición correcta
        respuesta = messagebox.askyesno("Confirmar Grabado", 
                                       "¿El láser está en la posición correcta para comenzar?\n\n" +
                                       "⚠️ ADVERTENCIA: El grabado comenzará inmediatamente.\n\n" +
                                       "Presiona 'Sí' para iniciar el grabado.")
        if not respuesta:
            self.log_laser("⏸️ Grabado cancelado por el usuario")
            return
            
        try:
            self.log_laser("🚀 INICIANDO GRABADO...")
            
            # Generar G-code
            size_mm = (self.size_mm_x.get(), self.size_mm_y.get())
            gcode = generate_gcode_text(
                image_path=self.image_path,
                size_mm=size_mm,
                ppmm=self.ppmm.get(),
                mode=self.mode.get(),
                invert=self.invert.get(),
                gamma_val=self.gamma_val.get(),
                origin_xy=(0.0, 0.0),
                f_engrave=self.f_engrave.get(),
                f_travel=self.f_travel.get(),
                s_max=self.s_max.get()
            )
            
            # Enviar G-code al láser
            self.log_laser("📤 Enviando comandos de grabado al láser...")
            resultado = stream_to_grbl(self.ser_laser, gcode)
            
            if resultado == 0:
                self.log_laser("✅ GRABADO COMPLETADO EXITOSAMENTE")
                self.log_laser("🏠 El láser ha regresado a su posición inicial")
                # Resetear estado de inicialización para próximo grabado
                self.laser_inicializado = False
            else:
                self.log_laser("❌ ERROR DURANTE EL GRABADO")
                self.laser_inicializado = False
                
        except Exception as e:
            messagebox.showerror("Error", f"Error durante el grabado:\n{e}")
            self.log_laser(f"❌ Error durante el grabado: {e}")
            self.laser_inicializado = False
    
    def parar_laser(self):
        """Detiene el láser inmediatamente"""
        try:
            if self.ser_laser and getattr(self.ser_laser, "is_open", False):
                send_cmd(self.ser_laser, "M5")  # Apagar láser inmediatamente
                send_cmd(self.ser_laser, "!")   # Parada de emergencia
                self.log_laser("🛑 LÁSER DETENIDO - Parada de emergencia activada")
                self.laser_inicializado = False
            else:
                self.log_laser("⚠️ No hay conexión con el láser")
        except Exception as e:
            self.log_laser(f"❌ Error deteniendo láser: {e}")
    
    def mover_origen(self):
        """Mueve el láser al origen de coordenadas"""
        try:
            if not self.ser_laser or not getattr(self.ser_laser, "is_open", False):
                messagebox.showwarning("Advertencia", "Conecta al láser primero")
                return
            
            self.log_laser("🏠 Moviendo al origen...")
            send_cmd(self.ser_laser, "G90")  # Coordenadas absolutas
            send_cmd(self.ser_laser, "G0 X0 Y0")  # Mover a origen
            self.log_laser("✅ Láser movido al origen (0,0)")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error moviendo al origen:\n{e}")
            self.log_laser(f"❌ Error moviendo al origen: {e}")
    
    def limpiar_log(self):
        """Limpia el log del láser"""
        self.laser_log.config(state=tk.NORMAL)
        self.laser_log.delete(1.0, tk.END)
        self.laser_log.config(state=tk.DISABLED)
        self.log_laser("🧹 Log limpiado")
        
    def cerrar_ventana(self):
        """Cierra la ventana del láser"""
        self.desconectar_laser()
        self.ventana.destroy()

# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================

def main():
    """Función principal - ejecuta la aplicación de control del láser"""
    try:
        # Verificar dependencias
        if serial is None:
            messagebox.showerror("Error", 
                               "La librería 'pyserial' no está instalada.\n\n" +
                               "Para instalarla, ejecuta en tu terminal:\n" +
                               "pip install pyserial")
            return
        
        # Crear ventana principal
        ventana_laser = VentanaLaser()
        ventana_laser.log_laser("🎯 Sistema de Control de Láser CNC inicializado")
        ventana_laser.log_laser("📋 Instrucciones:")
        ventana_laser.log_laser("   1. Conecta al puerto serial del láser")
        ventana_laser.log_laser("   2. Selecciona una imagen para grabar")
        ventana_laser.log_laser("   3. Ajusta los parámetros de grabado")
        ventana_laser.log_laser("   4. Inicializa el láser")
        ventana_laser.log_laser("   5. Inicia el grabado")
        
        # Ejecutar aplicación
        ventana_laser.ventana.mainloop()
        
    except Exception as e:
        messagebox.showerror("Error Crítico", f"Error iniciando la aplicación:\n{e}")

# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

if __name__ == "__main__":
    main()