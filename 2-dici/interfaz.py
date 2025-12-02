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
        self.root.title("Sistema de Estaciones")
        self.root.geometry("1000x600")
        self.root.configure(bg="lightgray")
        
        
        # Estado serial y tracking
        self.ser = None
        self.is_serial_open = False
        self.read_interval_ms = 200
        self.tracked_pallet = ""  # texto a buscar en mensajes serial
        self.station_ovals = {}  # mapping estacion -> canvas oval id
        # Solo estaciones habilitadas: 1, 3, 5
        self.station_states = {1: False, 3: False, 5: False}
        
        # Configuración serial de la cinta
        self.BAUDRATE = 9600
        self.BYTESIZE = serial.SEVENBITS if serial else None
        self.PARITY = serial.PARITY_EVEN if serial else None
        self.STOPBITS = serial.STOPBITS_TWO if serial else None

    # Controles superiores (puerto serial y pallet a seguir)
        control_frame = ttk.Frame(self.root)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=6)

        ttk.Label(control_frame, text="Puerto:").pack(side=tk.LEFT)
        self.combo_puertos = ttk.Combobox(control_frame, values=["COM1","COM2","COM3","COM4","COM5","COM6","COM7"], state="readonly", width=8)
        self.combo_puertos.set("COM3")
        self.combo_puertos.pack(side=tk.LEFT, padx=6)

        self.btn_refresh = ttk.Button(control_frame, text="🔄", command=self.refresh_ports, width=3)
        self.btn_refresh.pack(side=tk.LEFT, padx=2)

        self.btn_connect = ttk.Button(control_frame, text="Conectar", command=self.connect_serial)
        self.btn_connect.pack(side=tk.LEFT, padx=6)

        self.btn_disconnect = ttk.Button(control_frame, text="Desconectar", command=self.disconnect_serial)
        self.btn_disconnect.pack(side=tk.LEFT, padx=6)

        self.serial_status = ttk.Label(control_frame, text="Desconectado", background="red")
        self.serial_status.pack(side=tk.LEFT, padx=8)

        ttk.Label(control_frame, text="Pallet a seguir:").pack(side=tk.LEFT, padx=(20,4))
        self.entry_pallet = ttk.Entry(control_frame, width=12)
        self.entry_pallet.pack(side=tk.LEFT)
        self.btn_start_track = ttk.Button(control_frame, text="Seguir", command=self.start_tracking)
        self.btn_start_track.pack(side=tk.LEFT, padx=6)
        self.btn_stop_track = ttk.Button(control_frame, text="Detener", command=self.stop_tracking)
        self.btn_stop_track.pack(side=tk.LEFT, padx=6)

    # Caja de estado último mensaje

        self.last_message = ttk.Label(control_frame, text="")
        self.last_message.pack(side=tk.RIGHT, padx=10)

        # --- Zona central: Panel de Serial/IDs a la izquierda + Canvas a la derecha ---
        middle = ttk.Frame(self.root)
        middle.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        # Panel izquierdo: Logs seriales e IDs detectadas
        self.sidebar = ttk.LabelFrame(middle, text="Serial y Pallets")
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        self.sidebar.pack_propagate(False)
        self.sidebar.configure(width=320)

        # Área de logs
        self.text_log = tk.Text(self.sidebar, state="disabled", width=42, height=16)
        self.text_log.grid(row=0, column=0, columnspan=2, padx=6, pady=(6, 2), sticky="nwe")
        self.scroll_log = ttk.Scrollbar(self.sidebar, orient="vertical", command=self.text_log.yview)
        self.scroll_log.grid(row=0, column=2, rowspan=1, sticky="nsw", pady=(6, 2))
        self.text_log.configure(yscrollcommand=self.scroll_log.set)

        # Lista de IDs detectadas
        ttk.Label(self.sidebar, text="IDs detectadas:").grid(row=1, column=0, columnspan=3, sticky="w", padx=6)
        self.ids_list = tk.Listbox(self.sidebar, height=8)
        self.ids_list.grid(row=2, column=0, columnspan=2, padx=6, pady=2, sticky="we")
        self.ids_list.bind("<Double-Button-1>", self.on_choose_id)
        btn_follow = ttk.Button(self.sidebar, text="Seguir seleccionado", command=self.follow_selected_id)
        btn_follow.grid(row=3, column=0, padx=6, pady=(2,6), sticky="we")
        btn_clear = ttk.Button(self.sidebar, text="Limpiar IDs", command=self.clear_ids)
        btn_clear.grid(row=3, column=1, padx=6, pady=(2,6), sticky="we")

        # Crear canvas para dibujar (a la derecha)
        self.canvas = Canvas(middle, bg="lightgray", highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Estructuras para tracking de IDs
        self.detected_ids = set()
        
        # Dimensiones de las estaciones
        self.estacion_width = 100
        self.estacion_height = 100
        self.boton_radius = 30
        
        # Posiciones de las estaciones (fila superior e inferior)
        self.estaciones = {
            1: {"x": 143, "y": 120, "color": "red"},
            2: {"x": 390, "y": 120, "color": "red"},
            3: {"x": 637, "y": 120, "color": "red"},
            4: {"x": 884, "y": 120, "color": "red"},
            5: {"x": 390, "y": 370, "color": "red"},
            6: {"x": 637, "y": 370, "color": "red"},
        }
        
        self.dibujar_interface()
        self.crear_botones()
        
        # Detectar puertos disponibles al inicio
        self.root.after(100, self.refresh_ports)
    
    def dibujar_interface(self):
        """Dibuja la interfaz con estaciones y conexiones"""
        
        # Dibujar líneas de conexión (antes que los cuadrados)
        # Línea horizontal superior
        self.canvas.create_line(173, 120, 360, 120, width=5, fill="black")
        self.canvas.create_line(420, 120, 607, 120, width=5, fill="black")
        self.canvas.create_line(667, 120, 854, 120, width=5, fill="black")
        
        # Línea vertical de Est. 1
        self.canvas.create_line(143, 170, 143, 250, width=5, fill="black")
        
        # Línea horizontal hacia Est. 5
        self.canvas.create_line(143, 250, 360, 250, width=5, fill="black")
        
        # Línea vertical hacia Est. 5
        self.canvas.create_line(360, 250, 390, 340, width=5, fill="black")
        
        # Línea horizontal inferior
        self.canvas.create_line(420, 370, 607, 370, width=5, fill="black")
        
        # Dibujar las estaciones
        for estacion_id, pos in self.estaciones.items():
            if estacion_id <= 4:  # Fila superior (1-4)
                self.dibujar_estacion(pos["x"], pos["y"], pos["color"], estacion_id)
            else:  # Fila inferior (5-6)
                self.dibujar_estacion(pos["x"], pos["y"], pos["color"], estacion_id)
    
    def dibujar_estacion(self, x, y, color, numero):
        """Dibuja una estación con cuadrado gris y botón circular"""
        
        # Cuadrado gris
        self.canvas.create_rectangle(
            x - self.estacion_width//2, y - self.estacion_height//2,
            x + self.estacion_width//2, y + self.estacion_height//2,
            fill="gray", outline="darkgray", width=3
        )
        
        # Círculo (botón) - guardar id para poder cambiar color luego
        oval_id = self.canvas.create_oval(
            x - self.boton_radius, y - self.boton_radius,
            x + self.boton_radius, y + self.boton_radius,
            fill=color, outline="black", width=2
        )
        self.station_ovals[numero] = oval_id
        
        # Etiqueta con número de estación
        self.canvas.create_text(
            x, y + 65, text=f"Est. {numero}", font=("Arial", 12, "bold")
        )
    
    def crear_botones(self):
        """Crea frame con botones de control"""
        
        frame_botones = ttk.Frame(self.root)
        frame_botones.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        # Botones de acción
        btn_deliver = ttk.Button(frame_botones, text="Deliver", command=self.deliver)
        btn_deliver.pack(side=tk.LEFT, padx=15, pady=10, fill=tk.X, expand=True)
        
        btn_free = ttk.Button(frame_botones, text="Free", command=self.free)
        btn_free.pack(side=tk.LEFT, padx=15, pady=10, fill=tk.X, expand=True)
        
        btn_reset = ttk.Button(frame_botones, text="Reset", command=self.reset)
        btn_reset.pack(side=tk.LEFT, padx=15, pady=10, fill=tk.X, expand=True)
        
        btn_salir = ttk.Button(frame_botones, text="Salir", command=self.root.quit)
        btn_salir.pack(side=tk.LEFT, padx=15, pady=10, fill=tk.X, expand=True)
        
        # Mostrar estado de tracking en la parte inferior
        self.tracking_label = ttk.Label(frame_botones, text="No siguiendo pallet")
        self.tracking_label.pack(side=tk.RIGHT, padx=10)

    # --- Serial y Tracking ---
    def refresh_ports(self):
        """Actualiza la lista de puertos COM disponibles"""
        if serial is None:
            return
        ports = serial.tools.list_ports.comports()
        port_list = []
        for port in ports:
            port_list.append(port.device)
        
        if not port_list:
            port_list = ["COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7"]
        
        self.combo_puertos['values'] = port_list
        if port_list:
            self.combo_puertos.set(port_list[0])
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
            self.serial_status.config(text="Conectado", background="lightgreen")
            # iniciar loop de lectura
            self.root.after(self.read_interval_ms, self.read_serial_loop)
            
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
            self.serial_status.config(text="Error", background="red")
        except Exception as e:
            messagebox.showerror("Error", f"Error inesperado: {e}")
            self.ser = None
            self.is_serial_open = False
            self.serial_status.config(text="Error", background="red")

    def disconnect_serial(self):
        try:
            if self.ser is not None:
                self.ser.close()
        except Exception:
            pass
        self.ser = None
        self.is_serial_open = False
        self.serial_status.config(text="Desconectado", background="red")

    def start_tracking(self):
        text = self.entry_pallet.get().strip()
        if not text:
            self.tracking_label.config(text="Ingrese pallet a seguir")
            return
        self.tracked_pallet = text
        self.tracking_label.config(text=f"Siguiendo: {text}")

    def stop_tracking(self):
        self.tracked_pallet = ""
        self.tracking_label.config(text="No siguiendo pallet")
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
                        # actualizar label de último mensaje
                        self.last_message.config(text=line)
                        # registrar en log y extraer posibles IDs
                        self.append_log("<-- " + line)
                        self.register_ids_from_line(line)
                        self.process_serial_line(line)
            except Exception as e:
                self.last_message.config(text=f"Error lectura: {e}")
        self.root.after(self.read_interval_ms, self.read_serial_loop)

    def process_serial_line(self, line: str):
        """Detecta si la línea contiene el pallet seguido y extrae estación si es posible."""
        if not self.tracked_pallet:
            return
        # Si la línea contiene la ID seguida
        if self._line_contains_tracked_id(line):
            # buscar número de estación (solo 1,3,5) con varios patrones comunes
            m = re.search(r"(?:est\.?|st\.?|station|e)\s*[:#\-\s]*([135])", line, re.I)
            if m:
                est = int(m.group(1))
                if est in self.station_states:
                    for s in self.station_states.keys():
                        self.set_station_state(s, s == est)
                    return
            # fallback: si solo llega un ARRIVED pero sin estación, no cambiar a verde; apagar todas
            if re.search(r"ARRIVED|LLEGADO|ARRIBA", line, re.I):
                for s in self.station_states.keys():
                    self.set_station_state(s, False)

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

    # --- Utilidades de log e IDs ---
    def append_log(self, text: str):
        try:
            self.text_log.configure(state="normal")
            self.text_log.insert(tk.END, text + "\n")
            self.text_log.see(tk.END)
        finally:
            self.text_log.configure(state="disabled")

    def register_ids_from_line(self, line: str):
        # Buscar patrones comunes y conservar un posible asterisco final (ej. "A123*")
        ids = []
        for pat in [
            r"P\s*[:#-]?\s*([A-Za-z0-9]+\*?)",
            r"PALLET\s*[:#-]?\s*([A-Za-z0-9]+\*?)",
            r"ID\s*[:#-]?\s*([A-Za-z0-9]+\*?)",
        ]:
            for m in re.finditer(pat, line, re.I):
                ids.append(m.group(1))
        for _id in ids:
            if _id and _id not in self.detected_ids:
                self.detected_ids.add(_id)
                self.ids_list.insert(tk.END, _id)

    def _line_contains_tracked_id(self, line: str) -> bool:
        if not self.tracked_pallet:
            return False
        tp = self.tracked_pallet.strip()
        if not tp:
            return False
        # Coincidir con o sin asterisco final
        variants = {tp}
        if tp.endswith("*"):
            variants.add(tp[:-1])
        else:
            variants.add(tp + "*")
        return any(v and v in line for v in variants)

    def follow_selected_id(self):
        try:
            idx = self.ids_list.curselection()
            if not idx:
                return
            value = self.ids_list.get(idx[0])
            self.entry_pallet.delete(0, tk.END)
            self.entry_pallet.insert(0, value)
            self.start_tracking()
        except Exception:
            pass

    def on_choose_id(self, event=None):
        self.follow_selected_id()

    def clear_ids(self):
        self.detected_ids.clear()
        self.ids_list.delete(0, tk.END)
    
    def deliver(self):
        """Envía comando Deliver a la estación y pallet configurados"""
        if not self.is_serial_open or self.ser is None:
            messagebox.showerror("Error", "Puerto serial no conectado")
            return
        
        # Diálogo simple para pedir estación y pallet
        dialog = tk.Toplevel(self.root)
        dialog.title("Enviar Deliver")
        dialog.geometry("300x150")
        
        ttk.Label(dialog, text="Estación:").pack(pady=5)
        combo_est = ttk.Combobox(dialog, values=[1,3,5], state="readonly", width=10)
        combo_est.set(1)
        combo_est.pack()
        
        ttk.Label(dialog, text="Pallet:").pack(pady=5)
        combo_pal = ttk.Combobox(dialog, values=[1,2,3,5,6], state="readonly", width=10)
        combo_pal.set(1)
        combo_pal.pack()
        
        def enviar():
            estacion = int(combo_est.get())
            pallet = int(combo_pal.get())
            self.send_deliver(estacion, pallet)
            dialog.destroy()
        
        ttk.Button(dialog, text="Enviar", command=enviar).pack(pady=10)
    
    def send_deliver(self, estacion, pallet):
        """Envía el comando Deliver según estación y pallet"""
        if not self.is_serial_open or self.ser is None:
            messagebox.showerror("Error", "Puerto serial no conectado")
            return
        
        # Comandos de la cinta (igual que en cinta.py; estaciones 1,3,5 y pallets 1,2,3,5,6)
        comandos = {
            (1, 1): "@00WD000900015B*",
            (1, 2): "@00WD0010000153*",
            (1, 3): "@00WD0011000152*",
            (1, 5): "@00WD0013000150*",
            (1, 6): "@00WD0014000157*",
            (3, 1): "@00WD0009000359*",
            (3, 2): "@00WD0010000351*",
            (3, 3): "@00WD0011000350*",
            (3, 5): "@00WD0013000352*",
            (3, 6): "@00WD0014000355*",
            (5, 1): "@00WD000900055F*",
            (5, 2): "@00WD0010000557*",
            (5, 3): "@00WD0011000556*",
            (5, 5): "@00WD0013000554*",
            (5, 6): "@00WD0014000553*",
        }
        
        cmd = comandos.get((estacion, pallet))
        if not cmd:
            messagebox.showwarning("Atención", "Combinación estación/pallet no válida")
            return
        
        try:
            self.append_log("--> " + cmd)
            self.ser.write((cmd + "\r\n\r\n").encode())
            self.last_message.config(text=f"Deliver enviado: Est {estacion}, Pallet {pallet}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo enviar deliver: {e}")
    
    def free(self):
        """Envía comando Free a la estación y pallet configurados"""
        if not self.is_serial_open or self.ser is None:
            messagebox.showerror("Error", "Puerto serial no conectado")
            return
        
        # Diálogo simple para pedir estación y pallet
        dialog = tk.Toplevel(self.root)
        dialog.title("Enviar Free")
        dialog.geometry("300x150")
        
        ttk.Label(dialog, text="Estación:").pack(pady=5)
        combo_est = ttk.Combobox(dialog, values=[1,3,5], state="readonly", width=10)
        combo_est.set(1)
        combo_est.pack()
        
        ttk.Label(dialog, text="Pallet:").pack(pady=5)
        combo_pal = ttk.Combobox(dialog, values=[1,2,3,5,6], state="readonly", width=10)
        combo_pal.set(1)
        combo_pal.pack()
        
        def enviar():
            estacion = int(combo_est.get())
            pallet = int(combo_pal.get())
            self.send_free(estacion, pallet)
            dialog.destroy()
        
        ttk.Button(dialog, text="Enviar", command=enviar).pack(pady=10)
    
    def send_free(self, estacion, pallet):
        """Envía secuencia Free: liberar estación y confirmar salida pallet"""
        if not self.is_serial_open or self.ser is None:
            messagebox.showerror("Error", "Puerto serial no conectado")
            return
        
        # Comandos para liberar estación (1,3,5)
        cmd_estacion = {
            1: "@00WD004800015E*",
            3: "@00WD0050000157*",
            5: "@00WD0052000155*",
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
            messagebox.showwarning("Atención", "Estación no válida")
            return
        if not cmd2:
            messagebox.showwarning("Atención", "Pallet no válido")
            return
        
        try:
            self.append_log("--> " + cmd1)
            self.ser.write((cmd1 + "\r\n\r\n").encode())
            time.sleep(0.5)
            self.append_log("--> " + cmd2)
            self.ser.write((cmd2 + "\r\n\r\n").encode())
            self.last_message.config(text=f"Free enviado: Est {estacion}, Pallet {pallet}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo enviar free: {e}")
    
    def reset(self):
        """Resetea el sistema: detiene tracking y pone todas las estaciones en rojo"""
        self.stop_tracking()
        self.last_message.config(text="Sistema reseteado")
        print("Sistema reseteado")

if __name__ == "__main__":
    root = tk.Tk()
    app = InterfazEstaciones(root)
    root.mainloop()