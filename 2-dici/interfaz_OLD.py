import tkinter as tk
from tkinter import Canvas
import tkinter.ttk as ttk
from tkinter import messagebox
import threading
import time
import re
try:
    import serial
    import serial.tools.list_ports
except Exception:
    serial = None

class InterfazEstaciones:
    def __init__(self, root):
        self.root = root
        self.root.title("Sistema de Control - Estaciones 1, 3, 5")
        self.root.geometry("900x600")
        self.root.configure(bg="lightgray")
        
        # Estado serial y tracking
        self.ser = None
        self.is_serial_open = False
        self.read_interval_ms = 200
        self.tracked_pallet = ""  # ID del pallet a seguir (1, 2, 3, 5, 6)
        self.station_ovals = {}  # mapping estacion -> canvas oval id
        self.station_states = {1: False, 3: False, 5: False}  # Solo estaciones 1, 3, 5
        self.current_location = None  # Ubicación actual del pallet seguido
        
        # Configuración serial de la cinta
        self.BAUDRATE = 9600
        self.BYTESIZE = serial.SEVENBITS if serial else None
        self.PARITY = serial.PARITY_EVEN if serial else None
        self.STOPBITS = serial.STOPBITS_TWO if serial else None

        # Controles superiores (puerto serial y tracking)
        control_frame = ttk.Frame(self.root)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=8)

        # Puerto serial
        ttk.Label(control_frame, text="Puerto COM:").pack(side=tk.LEFT, padx=5)
        self.combo_puertos = ttk.Combobox(control_frame, values=[], state="readonly", width=10)
        self.combo_puertos.pack(side=tk.LEFT, padx=5)

        self.btn_refresh = ttk.Button(control_frame, text="🔄 Actualizar", command=self.refresh_ports, width=12)
        self.btn_refresh.pack(side=tk.LEFT, padx=5)

        self.btn_connect = ttk.Button(control_frame, text="Conectar", command=self.connect_serial, width=10)
        self.btn_connect.pack(side=tk.LEFT, padx=5)

        self.btn_disconnect = ttk.Button(control_frame, text="Desconectar", command=self.disconnect_serial, width=10)
        self.btn_disconnect.pack(side=tk.LEFT, padx=5)

        self.serial_status = ttk.Label(control_frame, text="● Desconectado", foreground="red", font=("Arial", 10, "bold"))
        self.serial_status.pack(side=tk.LEFT, padx=10)

        # Separador visual
        ttk.Separator(control_frame, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=10)

        # Tracking de pallet
        ttk.Label(control_frame, text="ID Pallet a seguir:").pack(side=tk.LEFT, padx=5)
        self.combo_pallet = ttk.Combobox(control_frame, values=[1, 2, 3, 5, 6], state="readonly", width=5)
        self.combo_pallet.set(1)
        self.combo_pallet.pack(side=tk.LEFT, padx=5)
        
        self.btn_start_track = ttk.Button(control_frame, text="▶ Seguir", command=self.start_tracking, width=8)
        self.btn_start_track.pack(side=tk.LEFT, padx=5)
        
        self.btn_stop_track = ttk.Button(control_frame, text="■ Detener", command=self.stop_tracking, width=8)
        self.btn_stop_track.pack(side=tk.LEFT, padx=5)
        
        self.tracking_label = ttk.Label(control_frame, text="Sin tracking activo", font=("Arial", 9, "italic"))
        self.tracking_label.pack(side=tk.LEFT, padx=10)

        # Crear canvas para dibujar
        self.canvas = Canvas(root, bg="lightgray", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Dimensiones de las estaciones - DISEÑO OVALADO
        self.estacion_width = 140
        self.estacion_height = 100
        self.boton_radius = 40
        
        # Posiciones de las estaciones - SOLO 1, 3, 5 (distribuidas horizontalmente)
        self.estaciones = {
            1: {"x": 200, "y": 250, "color": "red", "nombre": "Estación 1"},
            3: {"x": 450, "y": 250, "color": "red", "nombre": "Estación 3"},
            5: {"x": 700, "y": 250, "color": "red", "nombre": "Estación 5"},
        }
        
        self.dibujar_interface()
        self.crear_botones()
        
        # Detectar puertos disponibles al inicio
        self.root.after(100, self.refresh_ports)
    
    def dibujar_interface(self):
        """Dibuja la interfaz con estaciones y conexiones"""
        
        # Título superior
        self.canvas.create_text(
            450, 50, 
            text="SISTEMA DE CONTROL - CINTA TRANSPORTADORA",
            font=("Arial", 16, "bold"),
            fill="#1976D2"
        )
        
        # Línea de conexión entre estaciones (flujo horizontal)
        self.canvas.create_line(260, 250, 390, 250, width=8, fill="#424242", smooth=True, arrow=tk.LAST)
        self.canvas.create_line(510, 250, 640, 250, width=8, fill="#424242", smooth=True, arrow=tk.LAST)
        
        # Dibujar las estaciones
        for estacion_id, pos in self.estaciones.items():
            self.dibujar_estacion(pos["x"], pos["y"], pos["color"], estacion_id, pos["nombre"])
    
    def dibujar_estacion(self, x, y, color, numero, nombre):
        """Dibuja una estación con forma OVALADA elegante y botón circular grande"""
        
        # Óvalo exterior (cuerpo de la estación)
        self.canvas.create_oval(
            x - self.estacion_width//2, y - self.estacion_height//2,
            x + self.estacion_width//2, y + self.estacion_height//2,
            fill="#E0E0E0", outline="#757575", width=4
        )
        
        # Óvalo interior (decorativo) - Efecto 3D
        self.canvas.create_oval(
            x - self.estacion_width//2 + 10, y - self.estacion_height//2 + 8,
            x + self.estacion_width//2 - 10, y + self.estacion_height//2 - 8,
            fill="#F5F5F5", outline="#BDBDBD", width=2
        )
        
        # Círculo indicador (botón) - guardar id para poder cambiar color luego
        oval_id = self.canvas.create_oval(
            x - self.boton_radius, y - self.boton_radius,
            x + self.boton_radius, y + self.boton_radius,
            fill=color, outline="#424242", width=4
        )
        self.station_ovals[numero] = oval_id
        
        # Pequeño círculo blanco para efecto de brillo en el botón
        self.canvas.create_oval(
            x - 15, y - 15,
            x + 10, y + 10,
            fill="white", outline="", stipple="gray25"
        )
        
        # Etiqueta con nombre de estación
        self.canvas.create_text(
            x, y + self.estacion_height//2 + 25, 
            text=nombre, 
            font=("Arial", 14, "bold"),
            fill="#212121"
        )
        
        # Indicador de ID en la parte superior
        self.canvas.create_text(
            x, y - self.estacion_height//2 - 20,
            text=f"EST {numero}",
            font=("Arial", 12, "bold"),
            fill="#1976D2"
        )
    
    def crear_botones(self):
        """Crea frame con botones de control"""
        
        frame_botones = ttk.Frame(self.root)
        frame_botones.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        # Frame izquierdo - Información
        info_frame = ttk.LabelFrame(frame_botones, text="Estado del Sistema", padding=10)
        info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        self.lbl_status = ttk.Label(info_frame, text="Sistema listo", font=("Arial", 10))
        self.lbl_status.pack()
        
        # Frame central - Control Deliver/Free
        control_frame = ttk.LabelFrame(frame_botones, text="Control de Comandos", padding=10)
        control_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        btn_deliver = ttk.Button(control_frame, text="📦 DELIVER", command=self.deliver, width=15)
        btn_deliver.pack(side=tk.LEFT, padx=10, pady=5)
        
        btn_free = ttk.Button(control_frame, text="🚀 FREE", command=self.free, width=15)
        btn_free.pack(side=tk.LEFT, padx=10, pady=5)
        
        # Frame derecho - Acciones
        action_frame = ttk.LabelFrame(frame_botones, text="Acciones", padding=10)
        action_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        btn_reset = ttk.Button(action_frame, text="🔄 Reset", command=self.reset, width=12)
        btn_reset.pack(side=tk.LEFT, padx=5, pady=5)
        
        btn_salir = ttk.Button(action_frame, text="❌ Salir", command=self.root.quit, width=12)
        btn_salir.pack(side=tk.LEFT, padx=5, pady=5)

    # --- Serial y Tracking ---
    def refresh_ports(self):
        """Actualiza la lista de puertos COM disponibles"""
        if serial is None:
            messagebox.showwarning("Advertencia", "Módulo pyserial no disponible")
            return
        
        ports = serial.tools.list_ports.comports()
        port_list = [port.device for port in ports]
        
        if not port_list:
            port_list = ["COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7"]
            messagebox.showinfo("Info", "No se detectaron puertos COM. Mostrando lista predeterminada.")
        
        self.combo_puertos['values'] = port_list
        if port_list:
            self.combo_puertos.set(port_list[0])
        
        self.lbl_status.config(text=f"{len(port_list)} puerto(s) COM detectado(s)")
        return port_list
    
    def connect_serial(self):
        if serial is None:
            messagebox.showerror("Error", "pyserial no está instalado")
            return
        
        if self.is_serial_open:
            messagebox.showinfo("Info", "El puerto ya está conectado")
            return
        
        port = self.combo_puertos.get()
        if not port:
            messagebox.showerror("Error", "Por favor seleccione un puerto")
            return
        
        try:
            # Intenta cerrar cualquier conexión previa
            if self.ser is not None:
                try:
                    self.ser.close()
                except:
                    pass
            
            # Crea la conexión serial con todos los parámetros de la cinta
            self.ser = serial.Serial(
                port=port,
                baudrate=self.BAUDRATE,
                bytesize=self.BYTESIZE,
                parity=self.PARITY,
                stopbits=self.STOPBITS,
                timeout=0.2,
                write_timeout=2,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False
            )
            
            # Espera un momento para que el puerto se establezca
            time.sleep(0.5)
            
            # Limpia los buffers
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            
            self.is_serial_open = True
            self.serial_status.config(text="● Conectado", foreground="green")
            self.lbl_status.config(text=f"Conectado a {port} correctamente")
            # iniciar loop de lectura
            self.root.after(self.read_interval_ms, self.read_serial_loop)
            messagebox.showinfo("Éxito", f"Conectado a {port}")
            
        except serial.SerialException as e:
            error_msg = str(e)
            if "PermissionError" in error_msg or "13" in error_msg:
                messagebox.showerror("Error de Permisos", 
                    f"No se pudo abrir {port}\n\n"
                    "Posibles soluciones:\n"
                    "1. Cierre cualquier otra aplicación usando este puerto\n"
                    "2. Desconecte y reconecte el dispositivo USB\n"
                    "3. Verifique que el driver esté instalado correctamente\n"
                    "4. Pruebe ejecutar como Administrador\n"
                    "5. Reinicie el equipo\n\n"
                    f"Error técnico: {e}")
            else:
                messagebox.showerror("Error", f"No se pudo abrir {port}: {e}")
            self.ser = None
            self.is_serial_open = False
            self.serial_status.config(text="● Error", foreground="red")
            self.lbl_status.config(text="Error de conexión")
        except Exception as e:
            messagebox.showerror("Error", f"Error inesperado: {e}")
            self.ser = None
            self.is_serial_open = False
            self.serial_status.config(text="● Error", foreground="red")
            self.lbl_status.config(text="Error inesperado")

    def disconnect_serial(self):
        try:
            if self.ser is not None:
                self.ser.close()
        except Exception:
            pass
        self.ser = None
        self.is_serial_open = False
        self.serial_status.config(text="● Desconectado", foreground="red")
        self.lbl_status.config(text="Puerto serial desconectado")

    def start_tracking(self):
        """Inicia el tracking del pallet seleccionado"""
        pallet_id = self.combo_pallet.get().strip()
        if not pallet_id:
            messagebox.showwarning("Atención", "Seleccione un ID de pallet")
            return
        
        # El ID del pallet es directamente el número (1, 2, 3, 5, 6)
        self.tracked_pallet = str(pallet_id)
        self.tracking_label.config(text=f"📍 Siguiendo Pallet {pallet_id}")
        self.lbl_status.config(text=f"Tracking activo: Pallet {pallet_id}")
        
        # Resetear estados
        for s in self.station_states.keys():
            self.set_station_state(s, False)

    def stop_tracking(self):
        """Detiene el tracking del pallet"""
        self.tracked_pallet = ""
        self.current_location = None
        self.tracking_label.config(text="Sin tracking activo")
        self.lbl_status.config(text="Tracking detenido")
        
        # Poner todas las estaciones en rojo (no detectadas)
        for s in self.station_states.keys():
            self.set_station_state(s, False)

    def read_serial_loop(self):
        if self.is_serial_open and self.ser is not None:
            try:
                n = self.ser.in_waiting
                if n and n > 0:
                    data = self.ser.read(n)
                    try:
                        texto = data.decode('utf-8', errors='ignore')
                    except Exception:
                        texto = repr(data)
                    # procesar por líneas
                    for line in texto.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        # Procesar línea recibida
                        self.process_serial_line(line)
            except Exception as e:
                self.lbl_status.config(text=f"Error lectura: {e}")
        self.root.after(self.read_interval_ms, self.read_serial_loop)

    def process_serial_line(self, line: str):
        """Detecta si la línea contiene el pallet seguido y extrae estación"""
        if not self.tracked_pallet:
            return
        
        # El pallet a buscar es simplemente el número: 1, 2, 3, 5, 6
        line_upper = line.upper()
        pallet_id = self.tracked_pallet
        
        # Buscar si el mensaje contiene referencia al pallet seguido
        # Patrones: "P1", "PALLET 1", "P:1", etc.
        pallet_patterns = [
            rf"\bP[\s:.-]*{pallet_id}\b",  # P1, P:1, P 1
            rf"\bPALLET[\s:.-]*{pallet_id}\b",  # PALLET 1, PALLET:1
        ]
        
        pallet_found = False
        for pattern in pallet_patterns:
            if re.search(pattern, line_upper):
                pallet_found = True
                break
        
        if not pallet_found:
            return
        
        # Buscar número de estación (1, 3, 5)
        station_patterns = [
            r"(?:ST|STATION|EST|E)[\s:.-]*([135])\b",  # ST1, STATION:3, E5
            r"(?:ARRIVED|LLEGADO).*?(?:ST|EST|E)[\s:.-]*([135])",  # ARRIVED ST1
        ]
        
        estacion_detectada = None
        for pattern in station_patterns:
            m = re.search(pattern, line_upper)
            if m:
                est_num = int(m.group(1))
                if est_num in self.station_states:  # Solo 1, 3, 5
                    estacion_detectada = est_num
                    break
        
        # Actualizar ubicación visual
        if estacion_detectada:
            self.update_location(estacion_detectada)
            self.lbl_status.config(text=f"Pallet {pallet_id} detectado en Estación {estacion_detectada}")
        elif re.search(r"(?:LEFT|SALIDA|FREE|DEPARTED)", line_upper):
            # Pallet salió de la estación
            self.update_location(None)
            self.lbl_status.config(text=f"Pallet {pallet_id} en tránsito")
    
    def update_location(self, estacion):
        """Actualiza la ubicación visual del pallet"""
        if self.current_location != estacion:
            # Resetear todas las estaciones a rojo
            for s in self.station_states.keys():
                self.set_station_state(s, False)
            
            # Si hay una estación actual, ponerla en verde
            if estacion is not None:
                self.set_station_state(estacion, True)
                self.tracking_label.config(text=f"📍 Pallet {self.tracked_pallet} en Estación {estacion}")
            else:
                self.tracking_label.config(text=f"📍 Pallet {self.tracked_pallet} en tránsito")
            
            self.current_location = estacion

    def set_station_state(self, estacion: int, ok: bool):
        """Pone el botón de la estación en verde si ok True, rojo si False"""
        color = "green" if ok else "red"
        self.station_states[estacion] = ok
        oid = self.station_ovals.get(estacion)
        if oid:
            try:
                self.canvas.itemconfig(oid, fill=color)
            except Exception:
                pass
    
    def deliver(self):
        """Envía comando Deliver a la estación y pallet configurados"""
        if not self.is_serial_open or self.ser is None:
            messagebox.showerror("Error", "Puerto serial no conectado")
            return
        
        # Diálogo para seleccionar estación y pallet
        dialog = tk.Toplevel(self.root)
        dialog.title("Enviar Comando DELIVER")
        dialog.geometry("350x200")
        dialog.resizable(False, False)
        
        # Frame principal
        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main_frame, text="Seleccione Estación:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        combo_est = ttk.Combobox(main_frame, values=[1, 3, 5], state="readonly", width=15)
        combo_est.set(1)
        combo_est.grid(row=0, column=1, pady=5, padx=10)
        
        ttk.Label(main_frame, text="Seleccione Pallet:", font=("Arial", 10, "bold")).grid(row=1, column=0, sticky="w", pady=5)
        combo_pal = ttk.Combobox(main_frame, values=[1, 2, 3, 5, 6], state="readonly", width=15)
        combo_pal.set(1)
        combo_pal.grid(row=1, column=1, pady=5, padx=10)
        
        def enviar():
            estacion = int(combo_est.get())
            pallet = int(combo_pal.get())
            self.send_deliver(estacion, pallet)
            dialog.destroy()
        
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=20)
        
        ttk.Button(btn_frame, text="📦 Enviar DELIVER", command=enviar, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancelar", command=dialog.destroy, width=15).pack(side=tk.LEFT, padx=5)
    
    def send_deliver(self, estacion, pallet):
        """Envía el comando Deliver según estación y pallet (solo 1, 3, 5)"""
        if not self.is_serial_open or self.ser is None:
            messagebox.showerror("Error", "Puerto serial no conectado")
            return
        
        # Comandos DELIVER - Solo estaciones 1, 3, 5 con pallets 1, 2, 3, 5, 6
        comandos = {
            (1, 1): "@00WD000900015B*", (1, 2): "@00WD0010000153*", (1, 3): "@00WD0011000152*",
            (1, 5): "@00WD0013000150*", (1, 6): "@00WD0014000157*",
            (3, 1): "@00WD0009000359*", (3, 2): "@00WD0010000351*", (3, 3): "@00WD0011000350*",
            (3, 5): "@00WD0013000352*", (3, 6): "@00WD0014000355*",
            (5, 1): "@00WD000900055F*", (5, 2): "@00WD0010000557*", (5, 3): "@00WD0011000556*",
            (5, 5): "@00WD0013000554*", (5, 6): "@00WD0014000553*"
        }
        
        cmd = comandos.get((estacion, pallet))
        if not cmd:
            messagebox.showwarning("Atención", 
                f"Combinación no válida: Estación {estacion}, Pallet {pallet}\n"
                "Estaciones disponibles: 1, 3, 5\n"
                "Pallets disponibles: 1, 2, 3, 5, 6")
            return
        
        try:
            self.ser.write((cmd + "\r\n\r\n").encode())
            self.lbl_status.config(text=f"✓ DELIVER enviado: Est.{estacion} → Pallet {pallet}")
            messagebox.showinfo("Éxito", f"Comando DELIVER enviado\nEstación: {estacion}\nPallet: {pallet}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo enviar DELIVER: {e}")
            self.lbl_status.config(text="Error al enviar comando")
    
    def free(self):
        """Envía comando Free a la estación y pallet configurados"""
        if not self.is_serial_open or self.ser is None:
            messagebox.showerror("Error", "Puerto serial no conectado")
            return
        
            # Diálogo para seleccionar estación y pallet
        dialog = tk.Toplevel(self.root)
            dialog.title("Enviar Comando FREE")
            dialog.geometry("350x200")
            dialog.resizable(False, False)
        
            # Frame principal
            main_frame = ttk.Frame(dialog, padding=20)
            main_frame.pack(fill=tk.BOTH, expand=True)
        
            ttk.Label(main_frame, text="Seleccione Estación:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", pady=5)
            combo_est = ttk.Combobox(main_frame, values=[1, 3, 5], state="readonly", width=15)
        combo_est.set(1)
            combo_est.grid(row=0, column=1, pady=5, padx=10)
        
            ttk.Label(main_frame, text="Seleccione Pallet:", font=("Arial", 10, "bold")).grid(row=1, column=0, sticky="w", pady=5)
            combo_pal = ttk.Combobox(main_frame, values=[1, 2, 3, 5, 6], state="readonly", width=15)
        combo_pal.set(1)
            combo_pal.grid(row=1, column=1, pady=5, padx=10)
        
        def enviar():
            estacion = int(combo_est.get())
            pallet = int(combo_pal.get())
            self.send_free(estacion, pallet)
            dialog.destroy()
        
            btn_frame = ttk.Frame(main_frame)
            btn_frame.grid(row=2, column=0, columnspan=2, pady=20)
        
            ttk.Button(btn_frame, text="🚀 Enviar FREE", command=enviar, width=20).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_frame, text="Cancelar", command=dialog.destroy, width=15).pack(side=tk.LEFT, padx=5)
    
    def send_free(self, estacion, pallet):
            """Envía secuencia Free: liberar estación y confirmar salida pallet (solo 1, 3, 5)"""
        if not self.is_serial_open or self.ser is None:
            messagebox.showerror("Error", "Puerto serial no conectado")
            return
        
            # Comandos FREE - Solo estaciones 1, 3, 5
        cmd_estacion = {
            1: "@00WD004800015E*",
            3: "@00WD0050000157*",
                5: "@00WD0052000155*"
        }
        
        # Comandos para confirmar salida del pallet
        cmd_pallet = {
            1: "@00WD000900995A*",
            2: "@00WD0010009952*",
            3: "@00WD0011009953*",
            5: "@00WD0013009951*",
            6: "@00WD0014009956*"
        }
        
        cmd1 = cmd_estacion.get(estacion)
        cmd2 = cmd_pallet.get(pallet)
        
        if not cmd1:
                messagebox.showwarning("Atención", 
                    f"Estación {estacion} no válida\n"
                    "Estaciones disponibles: 1, 3, 5")
            return
        if not cmd2:
                messagebox.showwarning("Atención", 
                    f"Pallet {pallet} no válido\n"
                    "Pallets disponibles: 1, 2, 3, 5, 6")
            return
        
        try:
            self.ser.write((cmd1 + "\r\n\r\n").encode())
            time.sleep(0.5)
            self.ser.write((cmd2 + "\r\n\r\n").encode())
                self.lbl_status.config(text=f"✓ FREE enviado: Est.{estacion} → Pallet {pallet}")
                messagebox.showinfo("Éxito", f"Comando FREE enviado\nEstación: {estacion}\nPallet: {pallet}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo enviar free: {e}")
                self.lbl_status.config(text="Error al enviar comando")
    
    def reset(self):
        """Resetea el sistema: detiene tracking y pone todas las estaciones en rojo"""
        self.stop_tracking()
            self.lbl_status.config(text="Sistema reseteado correctamente")
            messagebox.showinfo("Reset", "Sistema reseteado correctamente")

if __name__ == "__main__":
    root = tk.Tk()
    app = InterfazEstaciones(root)
    root.mainloop()