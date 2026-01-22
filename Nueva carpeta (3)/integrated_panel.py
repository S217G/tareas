

import threading
import time
import tkinter as tk
import ultralytics
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
from ultralytics import YOLO
import os
import re
import socket
import queue

try:
    import serial
except Exception:
    serial = None

try:
    import ArucoProyectoBloqueo
except Exception:
    ArucoProyectoBloqueo = None

# --- Configuración serial para cinta (PLC) ---
CINTA_BAUDRATE = 9600
CINTA_BYTESIZE = serial.SEVENBITS if serial is not None else None
CINTA_PARITY = serial.PARITY_EVEN if serial is not None else None
CINTA_STOPBITS = serial.STOPBITS_TWO if serial is not None else None
CINTA_READ_INTERVAL_MS = 200

DELIVER_COMMANDS = {
    (1, 1): "@00WD000900015B*",
    (1, 2): "@00WD0010000153*",
    (1, 3): "@00WD0011000152*",
    (1, 5): "@00WD0013000150*",
    (1, 6): "@00WD0014000157*",
    (2, 1): "@00WD0009000258*",
    (2, 2): "@00WD0010000250*",
    (2, 3): "@00WD0011000251*",
    (2, 5): "@00WD0013000253*",
    (2, 6): "@00WD0014000254*",
    (3, 1): "@00WD0009000359*",
    (3, 2): "@00WD0010000351*",
    (3, 3): "@00WD0011000350*",
    (3, 5): "@00WD0013000352*",
    (3, 6): "@00WD0014000355*",
}

class IntegratedApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Panel Integrado - Sistema de Manufactura")
        self.root.geometry("1200x820")
        
        self.model_yolo = YOLO('bestMH.pt')
        self.ser_cinta = None
        self.ser_robot = None
        self.ser_laser = None

        self.is_serial_available = serial is not None

        self.station_states = {1: False, 2: False, 3: False}
        # Estados de paletas: {estación: {'pallet': pallet_id, 'color': 'red'/'green'/'yellow'}}
        self.station_pallet_info = {1: {'pallet': None, 'color': 'red'}, 
                                     2: {'pallet': None, 'color': 'red'}, 
                                     3: {'pallet': None, 'color': 'red'}}

        self.cam_thread = None
        self.cam_running = False
        self.camera_index = 0  # Índice de cámara seleccionada (0 o 1)

        self.laser_positions = {}
        self.robot_positions = {}
        self.aruco_generated_path = None
        
        # Robot command queue and sequence management
        # Queue con límite para evitar uso excesivo de memoria
        self.robot_command_queue = queue.Queue(maxsize=100)  # Max 100 comandos pendientes
        self.robot_queue_thread = None
        self.robot_queue_running = False
        self.robot_sequences = {}  # {name: [list of commands]} - acceso O(1)
        self.robot_executing = False
        
        # Control avanzado de ejes y grabación
        self.axis_sequence_recording = False
        self.axis_recorded_sequence = []
        self.axis_increment = 10  # Incremento por defecto para movimientos

        # Tracking history for deliver/free commands
        self.deliver_history = []  # list of dicts {id, type, station, pallet, status, t_sent, t_confirmed, duration}
        # Map for O(1) access by id
        self.deliver_history_map = {}
        # Map pallet->last sent deliver id (to detect by pallet id in serial responses)
        self.deliver_by_pallet = {}
        # Map station->last sent deliver id
        self.deliver_last_sent_by_station = {}
        self._history_counter = 0
        # Station monitor when user clicks a station: store station id or None
        self.monitor_station = None
        # Optional dedupe of seen (station,pallet) tuples - REMOVED for multiple passes
        # Track pallet current position: pallet_id -> (station, timestamp)
        self.pallet_current_position = {}  # {pallet_id: {'station': int, 'time': float}}
        # Follow pallet feature: pallet id to follow and active flag
        self.follow_pallet_id = None
        self.follow_active = False
        # Separate tracking for pass events only (pallet movement, not commands)
        self.pass_history = []
        self.pass_history_map = {}
        self.pass_counter = 0
        self._last_deliver_entry = None
        self._last_free_entry = None

        # Networking (socket server/cliente)
        self.net_queue = queue.Queue()
        self.server_thread = None
        self.server_running = False
        self.server_socket = None
        self.server_connections = []  # [(conn, addr, name)]
        self.client_socket = None
        self.client_thread = None

        # Robot serial stream visibility
        self.robot_stream_polling = False  # UI-driven polling to display all incoming data
        self.robot_active_read = False     # True while a blocking command read is in progress
        self.robot_ok_event = threading.Event()  # Señal para 'ok' recibido
        self.client_connected = False

        # Flag y control para lectura continua de cinta
        self.cinta_read_thread = None
        self.cinta_reading = False
        
        # Variables para tracking de comandos enviados
        self._last_deliver_station = None
        self._last_deliver_pallet = None
        self._last_free_station = None
        self._last_free_pallet = None

        self._build_ui()
        # Inicia loop de lectura de la cinta
        self.root.after(CINTA_READ_INTERVAL_MS, self._read_cinta_loop)
        self.root.after(200, self._serial_poll_loop)
        self.root.after(300, self._net_ui_pump)

    def _build_ui(self):
        # Layout con barra lateral izquierda y contenido a la derecha
        container = ttk.Frame(self.root)
        container.pack(fill=tk.BOTH, expand=True)
        sidebar = ttk.Frame(container, padding=4)
        sidebar.grid(row=0, column=0, sticky='ns')
        content = ttk.Frame(container)
        content.grid(row=0, column=1, sticky='nsew')

        container.columnconfigure(1, weight=1)
        container.rowconfigure(0, weight=1)

        # Crear frames de cada sección dentro de content
        tab_system = ttk.Frame(content)
        tab_robot_laser = ttk.Frame(content)
        tab_aruco = ttk.Frame(content)
        tab_tracking = ttk.Frame(content)
        tab_network = ttk.Frame(content)
        tab_advanced_robot = ttk.Frame(content)
        tab_robot_qc = ttk.Frame(content)

        self._tabs_frames = [
            ('Sistema', tab_system),
            ('Robot & Laser', tab_robot_laser),
            ('Generador ArUco', tab_aruco),
            ('Tracking (Prototipo)', tab_tracking),
            ('Red', tab_network),
            ('Control Avanzado Robot', tab_advanced_robot),
            ('Robot QC', tab_robot_qc)
        ]

        self._tab_buttons = []
        for i, (name, frame) in enumerate(self._tabs_frames):
            btn = ttk.Button(sidebar, text=name, command=lambda f=frame: self._show_tab(f))
            btn.grid(row=i, column=0, sticky='ew', padx=4, pady=2, ipadx=6, ipady=6)
            self._tab_buttons.append(btn)
            sidebar.rowconfigure(i, weight=1)
        sidebar.columnconfigure(0, weight=1)

        # Mostrar la primera pestaña por defecto
        self._active_tab = None
        self._content_parent = content
        for _, frame in self._tabs_frames:
            frame.grid(row=0, column=0, sticky='nsew')
            frame.grid_remove()
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)
        self._show_tab(tab_system)

        # Build panels into the appropriate tabs
        # System: cinta on top, camera below
        cinta_frame = ttk.Frame(tab_system)
        cinta_frame.pack(fill=tk.BOTH, expand=False, padx=4, pady=4)
        self._build_cinta_panel(cinta_frame)

        # Robot & Laser together
        rl_top = ttk.Frame(tab_robot_laser)
        rl_top.pack(fill=tk.BOTH, expand=True)

        row_robot = ttk.Frame(rl_top)
        row_robot.pack(fill=tk.BOTH, expand=True)
        self._build_robot_panel(row_robot)

        self._build_laser_panel(rl_top)

        # ArUco in its tab
        aru_frame = ttk.Frame(tab_aruco)
        aru_frame.pack(fill=tk.BOTH, expand=True)
        self._build_aruco_panel(aru_frame)

        # Tracking prototype tab
        track_frame = ttk.Frame(tab_tracking)
        track_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self._build_tracking_panel(track_frame)

        net_frame = ttk.Frame(tab_network)
        net_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self._build_network_panel(net_frame)
        
        adv_robot_frame = ttk.Frame(tab_advanced_robot)
        adv_robot_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self._build_advanced_robot_panel(adv_robot_frame)
        
        qc_robot_frame = ttk.Frame(tab_robot_qc)
        qc_robot_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self._build_robot_qc_panel(qc_robot_frame)

    def _show_tab(self, frame_to_show):
        """Muestra el frame solicitado y oculta el resto; centra y uniforma botones."""
        for f in (f for _, f in self._tabs_frames):
            f.grid_remove()
        frame_to_show.grid()
        self._active_tab = frame_to_show
        # Opcional: resaltar botón activo
        for btn, (_, frame) in zip(self._tab_buttons, self._tabs_frames):
            if frame is frame_to_show:
                btn.state(['pressed'])
            else:
                btn.state(['!pressed'])

    def _list_serial_ports(self):
        try:
            if serial is None:
                return []
            # prefer using serial.tools.list_ports if available
            tools = getattr(serial, 'tools', None)
            lp = None
            if tools is not None and hasattr(tools, 'list_ports'):
                lp = tools.list_ports.comports()
            else:
                lp = []
            return [p.device for p in lp]
        except Exception:
            return []

    # ---------------------- Cinta panel ----------------------
    def _build_cinta_panel(self, parent):
        frame = ttk.LabelFrame(parent, text="Cinta Transportadora", padding=8)
        frame.pack(fill=tk.BOTH, expand=False, padx=8, pady=8)

        # Station canvas - ahora con soporte para hacer clic
        self.canvas_cinta = tk.Canvas(frame, height=160, bg="#f0f0f0", cursor="hand2")
        self.canvas_cinta.pack(fill=tk.X, padx=4, pady=4)
        self.canvas_cinta.bind("<Button-1>", self._on_canvas_station_click)

        # Draw track and station ovals
        self._draw_cinta_layout()

        # Controls row - MEJORADO con soporte para múltiples puertos COM
        controls = ttk.Frame(frame)
        controls.pack(fill=tk.X, pady=(6,0))

        # Port selector con opción de escribir puerto personalizado
        ttk.Label(controls, text='Puerto COM:').pack(side=tk.LEFT, padx=(0,4))
        self.combo_cinta_ports = ttk.Combobox(controls, state='normal', width=18)
        self.combo_cinta_ports.pack(side=tk.LEFT, padx=(0,6))
        
        ttk.Button(controls, text='Refrescar', command=self._refresh_cinta_ports).pack(side=tk.LEFT, padx=(0,6))
        ttk.Button(controls, text='Conectar Cinta', command=self._connect_cinta).pack(side=tk.LEFT, padx=6)
        ttk.Button(controls, text='Desconectar Cinta', command=self._disconnect_cinta).pack(side=tk.LEFT, padx=6)
        ttk.Button(controls, text="Reset Cinta", command=self._reset_cinta_ui).pack(side=tk.LEFT, padx=6)

        self.label_cinta_status = ttk.Label(controls, text='Estado: Desconectada')
        self.label_cinta_status.pack(side=tk.LEFT, padx=(12,0))

        # Quick Deliver grid (Est 1/3/5 × Pal 1/2/3/5/6)
        grid_label = ttk.Label(frame, text="Grid Deliver Rápido (Est × Pal):", font=('Arial', 9, 'bold'))
        grid_label.pack(anchor=tk.W, padx=6, pady=(8,4))

        grid = ttk.Frame(frame)
        grid.pack(fill=tk.X, padx=6, pady=4)

        # Estaciones y pallets
        estaciones = [1, 2, 3]
        pallets = [1, 2, 3, 5, 6]

        # Encabezado de columnas (pallets)
        ttk.Label(grid, text="E\\P").grid(row=0, column=0, padx=2, pady=2)
        for j, pal in enumerate(pallets, start=1):
            ttk.Label(grid, text=str(pal), font=('Arial', 8, 'bold')).grid(row=0, column=j, padx=2, pady=2)

        # Botones del grid
        for i, est in enumerate(estaciones, start=1):
            ttk.Label(grid, text=str(est), font=('Arial', 8, 'bold')).grid(row=i, column=0, padx=2, pady=2)
            for j, pal in enumerate(pallets, start=1):
                btn_text = f"{est}→{pal}"
                cmd = lambda e=est, p=pal: self._send_deliver(e, p)
                ttk.Button(grid, text=btn_text, command=cmd).grid(row=i, column=j, padx=2, pady=2)

        # Quick Free grid (same layout) — botones para enviar Free rápido
        free_label = ttk.Label(frame, text="Grid Free Rápido:", font=('Arial', 9, 'bold'))
        free_label.pack(anchor=tk.W, padx=6, pady=(8,4))

        grid_free = ttk.Frame(frame)
        grid_free.pack(fill=tk.X, padx=6, pady=4)

        ttk.Label(grid_free, text="E\\P").grid(row=0, column=0, padx=2, pady=2)
        for j, pal in enumerate(pallets, start=1):
            ttk.Label(grid_free, text=str(pal), font=('Arial', 8, 'bold')).grid(row=0, column=j, padx=2, pady=2)

        for i, est in enumerate(estaciones, start=1):
            ttk.Label(grid_free, text=str(est), font=('Arial', 8, 'bold')).grid(row=i, column=0, padx=2, pady=2)
            for j, pal in enumerate(pallets, start=1):
                btn_text = f"F{est}->{pal}"
                cmdf = lambda e=est, p=pal: self._send_free(e, p)
                ttk.Button(grid_free, text=btn_text, command=cmdf).grid(row=i, column=j, padx=2, pady=2)

        # Log
        self.cinta_log = tk.Text(frame, height=6, state=tk.DISABLED)
        self.cinta_log.pack(fill=tk.BOTH, padx=4, pady=6)
        
        # Ahora sí podemos refrescar puertos (después de crear cinta_log)
        self._refresh_cinta_ports()

    def _draw_cinta_layout(self):
        """Dibuja el layout de la cinta con estaciones interactivas."""
        c = self.canvas_cinta
        c.delete('all')
        positions = {1: 80, 2: 180, 3: 280}
        y = 50
        
        # Track/vía principal
        c.create_line(30, y, 330, y, width=6, fill='black')
        
        self.cinta_ovals = {}
        self.cinta_stations_info = {}  # Información sobre cada estación para clicks
        
        for est, x in positions.items():
            # Rectángulo base de la estación
            c.create_rectangle(x-40, y-40, x+40, y+40, fill='#ddd', outline='#999', width=2)
            
            # Círculo principal (oval) - representa el estado del pallet
            color = self.station_pallet_info[est]['color']
            oval = c.create_oval(x-20, y-20, x+20, y+20, fill=color, outline='black', width=2)
            self.cinta_ovals[est] = oval
            self.cinta_stations_info[est] = {'x': x, 'y': y, 'oval': oval}
            
            # Etiqueta de la estación
            c.create_text(x, y+58, text=f"Est {est}", font=('Arial', 10, 'bold'))
            
            # Si hay pallet, mostrar ID del pallet dentro del círculo
            pallet_info = self.station_pallet_info[est]
            if pallet_info['pallet'] is not None:
                c.create_text(x, y, text=f"P{pallet_info['pallet']}", 
                            font=('Arial', 9, 'bold'), fill='white')

    def _on_canvas_station_click(self, event):
        """Maneja clicks en las estaciones del canvas para activar/desactivar monitor."""
        c = self.canvas_cinta
        # Buscar qué estación fue clickeada
        for est, info in self.cinta_stations_info.items():
            x, y = info['x'], info['y']
            if abs(event.x - x) <= 20 and abs(event.y - y) <= 20:
                # Toggle monitor para esta estación
                if self.monitor_station == est:
                    self.monitor_station = None
                    self._append_cinta_log(f'🖱️ Monitor OFF para estación {est}')
                else:
                    self.monitor_station = est
                    self._append_cinta_log(f'🖱️ Monitor ON para estación {est} (registrará pallets que pasen)')
                break

    def _set_cinta_station(self, station, has_pallet: bool, pallet_id=None):
        """
        Actualiza el estado visual de una estación.
        has_pallet: True si hay pallet (verde), False si está vacía (rojo)
        pallet_id: ID del pallet (opcional, para mostrar en el círculo)
        """
        color = 'green' if has_pallet else 'red'
        oval = self.cinta_ovals.get(station)
        
        if oval:
            self.canvas_cinta.itemconfig(oval, fill=color)
            
            # Actualizar información del pallet
            self.station_pallet_info[station]['color'] = color
            if has_pallet and pallet_id is not None:
                self.station_pallet_info[station]['pallet'] = pallet_id
            elif not has_pallet:
                self.station_pallet_info[station]['pallet'] = None
            
            # Redibujar la estación completa para actualizar el texto del pallet
            self._redraw_station(station)
        
        self.station_states[station] = has_pallet

    def _redraw_station(self, station):
        """Redibuja una estación específica con su información actualizada."""
        c = self.canvas_cinta
        info = self.cinta_stations_info.get(station)
        pallet_info = self.station_pallet_info.get(station)
        
        if not info or not pallet_info:
            return
        
        x, y = info['x'], info['y']
        oval = info['oval']
        
        # Actualizar color del círculo
        color = pallet_info['color']
        c.itemconfig(oval, fill=color)
        
        # Eliminar texto anterior de pallet dentro del círculo
        c.delete(f"pallet_text_{station}")
        
        # Crear nuevo texto si hay pallet
        if pallet_info['pallet'] is not None:
            c.create_text(x, y, text=f"P{pallet_info['pallet']}", 
                        font=('Arial', 9, 'bold'), fill='white',
                        tags=f"pallet_text_{station}")

    def _open_free_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title('Enviar Free')
        dlg.geometry('300x150')
        
        ttk.Label(dlg, text='Free — liberar estación y pallet').pack(padx=10, pady=6)
        
        ttk.Label(dlg, text='Estación:').pack(padx=6, pady=2)
        combo_e = ttk.Combobox(dlg, values=[1,2,3], state='readonly', width=10)
        combo_e.set(1)
        combo_e.pack(padx=6)
        
        ttk.Label(dlg, text='Pallet:').pack(padx=6, pady=2)
        combo_p = ttk.Combobox(dlg, values=[1,2,3,5,6], state='readonly', width=10)
        combo_p.set(1)
        combo_p.pack(padx=6)
        
        def do():
            try:
                e = int(combo_e.get())
                p = int(combo_p.get())
                self._send_free(e, p)
                dlg.destroy()
            except Exception as ex:
                messagebox.showerror('Error', str(ex))
        
        ttk.Button(dlg, text='Enviar Free', command=do).pack(pady=10)

    def _send_deliver(self, estacion, pallet, broadcast=True):
        cmd = DELIVER_COMMANDS.get((estacion, pallet))
        if not cmd:
            self._append_cinta_log('Comando no encontrado')
            return
        
        # SIEMPRE actualizar el color inmediatamente a verde
        self._set_cinta_station(estacion, True, pallet_id=pallet)
        self._append_cinta_log(f'✓ Pallet {pallet} llegó a estación {estacion}')
        # Record tracking entry for this deliver command
        entry_id = self._record_command('deliver', estacion, pallet)
        self._last_deliver_entry = entry_id

        if broadcast:
            self._net_broadcast_plc('deliver', estacion, pallet)
        
        # Enviar comando al PLC si está conectado
        if not self.ser_cinta or not getattr(self.ser_cinta, 'is_open', False):
            self._append_cinta_log(f'(SIM) Deliver no conectado: {cmd}')
            return
        
        try:
            self._last_deliver_station = estacion
            self._last_deliver_pallet = pallet
            self._append_cinta_log(f'--> Enviando comando: {cmd}')
            self.ser_cinta.write((cmd + '\r\n\r\n').encode())
        except Exception as e:
            self._append_cinta_log(f'Error enviando deliver: {e}')

    def _send_free(self, estacion, pallet, broadcast=True):
        # Sequence Free: liberar estación y confirmar salida pallet
        cmd_est = {1: "@00WD004800015E*", 2: "@00WD004900015F*", 3: "@00WD0050000157*"}.get(estacion)
        cmd_pal = {1: "@00WD000900995A*", 2: "@00WD0010009952*", 3: "@00WD0011009953*", 5: "@00WD0013009951*", 6: "@00WD0014009956*"}.get(pallet)
        
        if not cmd_est or not cmd_pal:
            self._append_cinta_log('Comando Free inválido')
            return
        
        # SIEMPRE actualizar el color inmediatamente a rojo (vacío)
        self._set_cinta_station(estacion, False, pallet_id=None)
        self._append_cinta_log(f'✗ Pallet {pallet} liberado de estación {estacion}')
        # Record tracking entry for this free command
        entry_id = self._record_command('free', estacion, pallet)
        self._last_free_entry = entry_id

        if broadcast:
            self._net_broadcast_plc('free', estacion, pallet)
        
        # Enviar comando al PLC si está conectado
        if not self.ser_cinta or not getattr(self.ser_cinta, 'is_open', False):
            self._append_cinta_log(f'(SIM) Free no conectado: Est{estacion} Pal{pallet}')
            return
        
        try:
            self._last_free_station = estacion
            self._last_free_pallet = pallet
            self._append_cinta_log(f'--> Enviando comando Free...')
            self._append_cinta_log(f'--> {cmd_est}')
            self.ser_cinta.write((cmd_est + '\r\n\r\n').encode())
            time.sleep(0.5)
            self._append_cinta_log(f'--> {cmd_pal}')
            self.ser_cinta.write((cmd_pal + '\r\n\r\n').encode())
        except Exception as e:
            self._append_cinta_log(f'Error enviando free: {e}')

    def _reset_cinta_ui(self):
        for s in self.station_states.keys():
            self._set_cinta_station(s, False)
        self._append_cinta_log('Cinta UI reseteada')

    def _append_cinta_log(self, msg):
        ts = time.strftime('%H:%M:%S')
        self.cinta_log.configure(state='normal')
        self.cinta_log.insert('end', f"[{ts}] {msg}\n")
        self.cinta_log.see('end')
        self.cinta_log.configure(state='disabled')

    def _refresh_cinta_ports(self):
        """Actualiza la lista de puertos COM disponibles con opción de agregar puertos personalizados."""
        try:
            ports = self._list_serial_ports()
            
            # Agregar algunos puertos comunes para dispositivos que podrían no estar detectados
            common_ports = ['COM1', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 
                           'COM10', 'COM11', 'COM12']
            
            # Combinar puertos detectados + puertos comunes (sin duplicados)
            all_ports = list(set(ports + common_ports))
            all_ports.sort()
            
            # Agregar el puerto actual si está en uso pero no en la lista
            if self.ser_cinta and getattr(self.ser_cinta, 'port', None):
                current_port = self.ser_cinta.port
                if current_port not in all_ports:
                    all_ports.insert(0, current_port)
            
            self.combo_cinta_ports['values'] = all_ports
            
            # Mantener selección actual si sigue siendo válida
            cur = self.combo_cinta_ports.get()
            if not cur or cur not in all_ports:
                self.combo_cinta_ports.set(ports[0] if ports else 'COM3')
            
            self._append_cinta_log(f'Puertos disponibles: {", ".join(all_ports)}')
        except Exception as e:
            self._append_cinta_log(f'Error actualizando puertos: {e}')

    def _connect_cinta(self):
        if serial is None:
            messagebox.showinfo('Cinta', 'pyserial no instalado - modo simulación')
            return
        
        ports = self._list_serial_ports()
        port = self.combo_cinta_ports.get()
        
        # Validar que hay un puerto seleccionado o personalizado
        if not port:
            messagebox.showwarning('Cinta', 'Por favor selecciona o ingresa un puerto COM')
            return
        
        try:
            # Cerrar conexión previa si existe
            if self.ser_cinta is not None:
                try:
                    self.ser_cinta.close()
                except Exception:
                    pass
            time.sleep(0.2)
            
            # Crear nuevo objeto serial con configuración PLC
            self.ser_cinta = serial.Serial()
            self.ser_cinta.baudrate = CINTA_BAUDRATE
            self.ser_cinta.bytesize = CINTA_BYTESIZE
            self.ser_cinta.parity = CINTA_PARITY
            self.ser_cinta.stopbits = CINTA_STOPBITS
            self.ser_cinta.timeout = 0.2
            self.ser_cinta.port = port
            self.ser_cinta.open()
            
            self._append_cinta_log(f'✓ Cinta conectada en puerto {port} (9600 7E2)')
            try:
                self.label_cinta_status.config(text=f'Estado: Conectada ({port})')
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror('Cinta', f'No se pudo conectar en {port}:\n{e}')
            self.ser_cinta = None
            try:
                self.label_cinta_status.config(text='Estado: Error de conexión')
            except Exception:
                pass

    def _disconnect_cinta(self):
        try:
            if self.ser_cinta and getattr(self.ser_cinta, 'is_open', False):
                self.ser_cinta.close()
            self._append_cinta_log('Cinta desconectada')
            try:
                self.label_cinta_status.config(text='Estado: Desconectada')
            except Exception:
                pass
        except Exception:
            pass

    def _read_cinta_loop(self):
        """Lee periódicamente datos del puerto serial de la cinta y los muestra en el log."""
        if self.ser_cinta and getattr(self.ser_cinta, 'is_open', False):
            try:
                n = self.ser_cinta.in_waiting
                if n and n > 0:
                    data = self.ser_cinta.read(n)
                    try:
                        texto = data.decode('utf-8', errors='ignore')
                    except Exception:
                        texto = repr(data)
                    self._append_cinta_log('<-- ' + texto.strip())
                    
                    # Detectar respuestas del PLC para cambiar color de estaciones
                    self._detect_pallet_status(texto)
            except Exception as e:
                self._append_cinta_log(f'Error leyendo cinta: {e}')
        # Reprogramar siguiente lectura
        self.root.after(CINTA_READ_INTERVAL_MS, self._read_cinta_loop)

    def _detect_pallet_status(self, response_text):
        """
        Detecta pallet en estación desde mensajes PLC (puede haber múltiples en un buffer).
        Procesa TODAS las estaciones/pallets encontradas, permitiendo múltiples pasadas.
        """
        response = response_text.strip()
        if not response:
            return
        
        resp_upper = response.upper()
        resp_lower = response.lower()

        # Buscar TODOS los patrones EX en el texto (puede haber múltiples mensajes)
        for m_ex in re.finditer(r'EX(\d{4})(\d{4})', resp_upper):
            try:
                station_found = int(m_ex.group(1))
                pallet_found = int(m_ex.group(2))
            except Exception:
                continue

            # Registrar siempre un pass al detectar EX (centraliza UI y limpieza)
            try:
                # Debug log: mostrar lo que se parseó
                self._append_cinta_log(f"DBG: EX match raw='{m_ex.group(0)}' station={station_found} pallet={pallet_found}")
                self._record_pass_event(station_found, pallet_found)
            except Exception as e:
                self._append_cinta_log(f'Error en pass event: {e}')

            # Intentar confirmar si hay un comando pendiente para este pallet (no registrar otra vez)
            if pallet_found is not None:
                hid = self.deliver_by_pallet.get(pallet_found)
                if hid:
                    try:
                        self._confirm_command(hid)
                        self.deliver_by_pallet.pop(pallet_found, None)
                        for s, v in list(self.deliver_last_sent_by_station.items()):
                            if v == hid:
                                self.deliver_last_sent_by_station.pop(s, None)
                    except Exception as e:
                        self._append_cinta_log(f'Error confirmando pallet {pallet_found}: {e}')
                    continue

            # Si no hay mapeo por pallet, intentar por estación (confirmar sólo)
            hid = self.deliver_last_sent_by_station.get(station_found)
            if hid:
                try:
                    self._confirm_command(hid)
                    self.deliver_last_sent_by_station.pop(station_found, None)
                    for p, v in list(self.deliver_by_pallet.items()):
                        if v == hid:
                            self.deliver_by_pallet.pop(p, None)
                except Exception as e:
                    self._append_cinta_log(f'Error en estación {station_found}: {e}')

    # ---------------------- Robot panel ----------------------
    def _build_robot_panel(self, parent):
        frame = ttk.LabelFrame(parent, text='Control Robot', padding=8)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        main = ttk.Frame(frame)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(0, weight=2, minsize=380)
        main.columnconfigure(1, weight=3, minsize=320)
        main.rowconfigure(0, weight=1)

        left = ttk.Frame(main)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 6))

        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky='nsew')

        # Selector de puerto COM para robot
        port_frame = ttk.Frame(left)
        port_frame.pack(fill=tk.X, pady=(0,4))
        ttk.Label(port_frame, text='Puerto COM:').pack(side=tk.LEFT, padx=(0,4))
        self.combo_robot_ports = ttk.Combobox(port_frame, state='normal', width=12)
        self.combo_robot_ports.pack(side=tk.LEFT, padx=(0,6))
        ttk.Button(port_frame, text='Refrescar', command=self._refresh_robot_ports).pack(side=tk.LEFT, padx=(0,6))
        
        btns = ttk.Frame(left)
        btns.pack(fill=tk.X, pady=4)
        ttk.Button(btns, text='Conectar Robot', command=self._connect_robot).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text='Desconectar', command=self._disconnect_robot).pack(side=tk.LEFT, padx=6)
        self.label_robot_status = ttk.Label(btns, text='Desconectado', foreground='red')
        self.label_robot_status.pack(side=tk.LEFT, padx=(12,0))

        # Comandos rápidos: Programas ARU
        grid = ttk.Frame(left)
        grid.pack(pady=6)
        aru_actions = [
            ('ARU', lambda: self._robot_queue_cmd('RUN ARU')),
            ('ARU1', lambda: self._robot_queue_cmd('RUN ARU1')),
            ('ARU2', lambda: self._robot_queue_cmd('RUN ARU2')),
            ('ARU3', lambda: self._robot_queue_cmd('RUN ARU3')),
            ('ARU4', lambda: self._robot_queue_cmd('RUN ARU4')),
        ]
        for i,(t,cmd) in enumerate(aru_actions):
            ttk.Button(grid, text=t, command=cmd).grid(row=0, column=i, padx=4, pady=4)
        
        # Secuencias fijas que esperan 'ok' entre pasos
        seq_quick = ttk.Frame(left)
        seq_quick.pack(pady=(0,6))
        ttk.Button(seq_quick, text='SEQ ARU → ARU2', command=lambda: self._execute_sequence_programs(['ARU','ARU2'])).pack(side=tk.LEFT, padx=4)
        ttk.Button(seq_quick, text='SEQ ARU1 → ARU3 → ARU4', command=lambda: self._execute_sequence_programs(['ARU1','ARU3','ARU4'])).pack(side=tk.LEFT, padx=4)
        
        # Fila adicional para más comandos
        grid2 = ttk.Frame(left)
        grid2.pack(pady=(0,6))
        actions2 = [
            ('AUTO', lambda: self._robot_send_cmd('AUTO')),
        ]
        for i,(t,cmd) in enumerate(actions2):
            ttk.Button(grid2, text=t, command=cmd).grid(row=0, column=i, padx=4, pady=4)

        self.robot_log = tk.Text(left, height=9, state=tk.DISABLED)
        self.robot_log.pack(fill=tk.BOTH, pady=6)

        # Robot positions: save arbitrary command text per named position
        pos_frame = ttk.Frame(left)
        pos_frame.pack(fill=tk.X, pady=(6,4))
        ttk.Label(pos_frame, text='Comando/Posición:').pack(side=tk.LEFT)
        self.entry_robot_cmd = ttk.Entry(pos_frame, width=28)
        self.entry_robot_cmd.pack(side=tk.LEFT, padx=(6,8))
        ttk.Label(pos_frame, text='Nombre:').pack(side=tk.LEFT)
        self.entry_robot_pos_name = ttk.Entry(pos_frame, width=12)
        self.entry_robot_pos_name.pack(side=tk.LEFT, padx=(6,8))
        ttk.Button(pos_frame, text='Guardar Posición', command=self._save_robot_position).pack(side=tk.LEFT, padx=6)

        pos_select = ttk.Frame(left)
        pos_select.pack(fill=tk.X)
        ttk.Label(pos_select, text='Posiciones:').pack(side=tk.LEFT)
        self.combo_robot_positions = ttk.Combobox(pos_select, values=list(self.robot_positions.keys()), state='readonly', width=20)
        self.combo_robot_positions.pack(side=tk.LEFT, padx=(6,4))
        ttk.Button(pos_select, text='Ir', command=self._goto_robot_position).pack(side=tk.LEFT, padx=2)
        ttk.Button(pos_select, text='Borrar', command=self._delete_robot_position).pack(side=tk.LEFT, padx=2)
        
        # Secuencias
        seq_frame = ttk.LabelFrame(left, text='Secuencias / Macros', padding=4)
        seq_frame.pack(fill=tk.X, pady=(6,4))
        
        seq_top = ttk.Frame(seq_frame)
        seq_top.pack(fill=tk.X)
        ttk.Label(seq_top, text='Nombre:').pack(side=tk.LEFT, padx=(0,2))
        self.entry_seq_name = ttk.Entry(seq_top, width=12)
        self.entry_seq_name.pack(side=tk.LEFT, padx=(0,4))
        ttk.Button(seq_top, text='Nueva Secuencia', command=self._new_sequence).pack(side=tk.LEFT, padx=2)
        ttk.Button(seq_top, text='Agregar Cmd Actual', command=self._add_to_sequence).pack(side=tk.LEFT, padx=2)
        
        seq_mid = ttk.Frame(seq_frame)
        seq_mid.pack(fill=tk.X, pady=(4,0))
        ttk.Label(seq_mid, text='Secuencias:').pack(side=tk.LEFT)
        self.combo_sequences = ttk.Combobox(seq_mid, values=list(self.robot_sequences.keys()), state='readonly', width=12)
        self.combo_sequences.pack(side=tk.LEFT, padx=(4,4))
        ttk.Button(seq_mid, text='Ejecutar', command=self._run_sequence).pack(side=tk.LEFT, padx=2)
        ttk.Button(seq_mid, text='Ver', command=self._view_sequence).pack(side=tk.LEFT, padx=2)
        ttk.Button(seq_mid, text='Borrar', command=self._delete_sequence).pack(side=tk.LEFT, padx=2)

        # Cámara ubicada a la derecha del panel de robot
        self._build_camera_panel(right, title='Cámara / Detección')
        
        # Refrescar puertos al iniciar
        self._refresh_robot_ports()

    def _refresh_robot_ports(self):
        """Actualiza la lista de puertos COM disponibles para el robot."""
        try:
            ports = self._list_serial_ports()
            common_ports = ['COM1', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 
                           'COM10', 'COM11', 'COM12']
            all_ports = list(set(ports + common_ports))
            all_ports.sort()
            
            if self.ser_robot and getattr(self.ser_robot, 'port', None):
                current_port = self.ser_robot.port
                if current_port not in all_ports:
                    all_ports.insert(0, current_port)
            
            self.combo_robot_ports['values'] = all_ports
            cur = self.combo_robot_ports.get()
            if not cur or cur not in all_ports:
                self.combo_robot_ports.set(ports[0] if ports else 'COM4')
            
            self._append_robot_log(f'Puertos disponibles: {", ".join(all_ports)}')
        except Exception as e:
            self._append_robot_log(f'Error actualizando puertos: {e}')

    def _connect_robot(self):
        if serial is None:
            messagebox.showinfo('Robot','pyserial no instalado - modo simulación')
            return
        
        port = self.combo_robot_ports.get()
        if not port:
            messagebox.showwarning('Robot', 'Por favor selecciona o ingresa un puerto COM')
            return
        
        try:
            if self.ser_robot is not None:
                try:
                    self.ser_robot.close()
                except Exception:
                    pass
            time.sleep(0.2)
            
            self.ser_robot = serial.Serial(port, baudrate=9600, bytesize=serial.EIGHTBITS, 
                                          parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, 
                                          timeout=2)
            self.ser_robot.reset_input_buffer()
            self.ser_robot.reset_output_buffer()
            
            # Iniciar cola de comandos
            self.robot_queue_running = True
            self.robot_queue_thread = threading.Thread(target=self._robot_queue_worker, daemon=True)
            self.robot_queue_thread.start()
            
            self._append_robot_log(f'✓ Robot conectado en {port}')
            self.label_robot_status.config(text='Conectado', foreground='green')
            
            # Configuración inicial
            time.sleep(0.3)
            self._robot_send_cmd('READY', wait=False)

            # Iniciar lector de stream para mostrar TODO lo recibido
            if not self.robot_stream_polling:
                self.robot_stream_polling = True
                self._robot_start_stream_reader()
        except Exception as e:
            messagebox.showerror('Robot', f'No se pudo conectar en {port}:\n{e}')
            self.label_robot_status.config(text='Error', foreground='red')

    def _disconnect_robot(self):
        try:
            # Detener lector de stream
            self.robot_stream_polling = False
            self.robot_queue_running = False
            if self.ser_robot and getattr(self.ser_robot, 'is_open', False):
                try:
                    self._robot_send_cmd('COFF', wait=False)
                    time.sleep(0.3)
                except Exception:
                    pass
                self.ser_robot.close()
            self._append_robot_log('Robot desconectado')
            self.label_robot_status.config(text='Desconectado', foreground='red')
        except Exception:
            pass

    def _robot_send_cmd(self, cmd, wait=True, timeout=10):
        """Envía comando ACL al robot con manejo robusto y NO bloqueante. O(1) para envío."""
        if not self.ser_robot or not getattr(self.ser_robot,'is_open',False):
            self.root.after(0, lambda: self._append_robot_log('⚠ Robot no conectado'))
            return False
        
        try:
            cmd_clean = cmd.strip().upper()
            
            # Envío O(1) - no bloqueante
            try:
                self.ser_robot.reset_input_buffer()
            except:
                pass
            
            payload = (cmd_clean + '\r').encode('ascii', errors='ignore')
            self.ser_robot.write(payload)
            self.ser_robot.flush()
            self.root.after(0, lambda c=cmd_clean: self._append_robot_log(f'→ {c}'))
            
            if not wait:
                return True
            
            # Lectura con polling eficiente - timeout reducido
            start_time = time.time()
            response = ''
            check_interval = 0.02  # 20ms entre checks - más responsive
            # Bloqueo la lectura periódica mientras espero respuesta
            self.robot_active_read = True
            try:
                while (time.time() - start_time) < timeout:
                    try:
                        waiting = self.ser_robot.in_waiting
                        if waiting > 0:
                            chunk = self.ser_robot.read(waiting).decode('ascii', errors='ignore')
                            response += chunk
                            
                            # Detección rápida de respuesta completa - O(n) donde n es tamaño respuesta
                            if 'Done.' in response or 'Error' in response or '>' in response:
                                break
                    except:
                        break
                    
                    time.sleep(check_interval)
            finally:
                self.robot_active_read = False
            
            response = response.strip()
            
            # Validación O(n) donde n es tamaño de respuesta (pequeño)
            if 'Done.' in response:
                self.root.after(0, lambda r=response: self._append_robot_log(f'✓ OK: {r}'))
                return True
            elif 'Error' in response:
                self.root.after(0, lambda r=response: self._append_robot_log(f'✗ ERROR: {r}'))
                return False
            elif response:
                self.root.after(0, lambda r=response: self._append_robot_log(f'← {r}'))
                return True
            else:
                self.root.after(0, lambda: self._append_robot_log('⚠ Sin respuesta (timeout)'))
                return False
                
        except Exception as e:
            self.root.after(0, lambda ex=e: self._append_robot_log(f'✗ Excepción: {ex}'))
            return False

    def _robot_start_stream_reader(self):
        # Inicia un lector basado en after() que muestra todo lo recibido en la terminal
        def _tick():
            if not self.robot_stream_polling:
                return
            try:
                if self.ser_robot and getattr(self.ser_robot, 'is_open', False) and not self.robot_active_read:
                    waiting = self.ser_robot.in_waiting
                    if waiting and waiting > 0:
                        data = self.ser_robot.read(waiting).decode('ascii', errors='ignore')
                        if data:
                            # Mostrar exactamente lo recibido
                            self._append_robot_log(f'← {data.strip()}')
                            try:
                                if 'ok' in data.lower():
                                    self.robot_ok_event.set()
                            except Exception:
                                pass
            except Exception:
                # Silencioso para no saturar; se puede loguear si es necesario
                pass
            finally:
                # Reprogramar próximo tick
                self.root.after(60, _tick)
        # Primera ejecución
        self.root.after(60, _tick)
    
    def _robot_queue_worker(self):
        """Worker thread optimizado - procesa comandos O(1) sin bloquear UI."""
        while self.robot_queue_running:
            try:
                # Get con timeout - O(1) operación
                cmd = self.robot_command_queue.get(timeout=0.05)
                if cmd:
                    self.robot_executing = True
                    # Ejecutar comando (puede tardar pero no bloquea UI)
                    success = self._robot_send_cmd(cmd, wait=True, timeout=8)
                    self.robot_executing = False
                    
                    # Pequeña pausa entre comandos para estabilidad
                    if success:
                        time.sleep(0.1)
            except queue.Empty:
                continue
            except Exception as e:
                self.root.after(0, lambda ex=e: self._append_robot_log(f'⚠ Error en cola: {ex}'))
                self.robot_executing = False
                time.sleep(0.1)
    
    def _robot_queue_cmd(self, cmd):
        """Agrega comando a la cola - Operación O(1) garantizada."""
        if not self.robot_queue_running:
            self._append_robot_log('⚠ Cola de comandos no activa')
            return False
        
        try:
            # put() es O(1) en Queue
            self.robot_command_queue.put_nowait(cmd)
            self._append_robot_log(f'⏱ En cola: {cmd}')
            return True
        except queue.Full:
            self._append_robot_log('⚠ Cola llena - espere')
            return False
        except Exception as e:
            self._append_robot_log(f'⚠ Error agregando a cola: {e}')
            return False

    def _robot_cmd_home(self): self._robot_queue_cmd('HOME')
    def _robot_cmd_ready(self): self._robot_queue_cmd('READY')
    def _robot_cmd_coff(self): self._robot_queue_cmd('COFF')
    def _robot_cmd_open(self): self._robot_queue_cmd('OPEN')
    def _robot_cmd_close(self): self._robot_queue_cmd('CLOSE')

    # Secuencias fijas: ejecutar RUN <prog> y esperar 'ok' entre pasos
    def _execute_sequence_programs(self, programs, ok_timeout=180):
        try:
            threading.Thread(target=self._sequence_worker, args=(programs, ok_timeout), daemon=True).start()
        except Exception as e:
            self._append_robot_log(f'✗ No se pudo iniciar la secuencia: {e}')

    def _sequence_worker(self, programs, ok_timeout):
        if not self.ser_robot or not getattr(self.ser_robot, 'is_open', False):
            self._append_robot_log('⚠ Robot no conectado')
            return
        try:
            self._append_robot_log(f"=== INICIANDO SECUENCIA: {' → '.join(programs)} ===")
            for i, prog in enumerate(programs, 1):
                self.robot_ok_event.clear()
                cmd = f"RUN {prog.upper()}"
                sent = self._robot_send_cmd(cmd, wait=True, timeout=15)
                if not sent:
                    self._append_robot_log(f'✗ Falló envío/resp de {cmd}')
                    return
                self._append_robot_log('… Esperando ok …')
                ok = self.robot_ok_event.wait(timeout=ok_timeout)
                if not ok:
                    self._append_robot_log('✗ Timeout esperando ok')
                    return
                self._append_robot_log('✓ ok recibido')
                time.sleep(0.3)
            self._append_robot_log('=== SECUENCIA COMPLETADA ===')
        except Exception as e:
            self._append_robot_log(f'✗ Excepción en secuencia: {e}')
            return

    def _append_robot_log(self, msg):
        ts = time.strftime('%H:%M:%S')
        self.robot_log.configure(state='normal')
        self.robot_log.insert('end', f"[{ts}] {msg}\n")
        self.robot_log.see('end')
        self.robot_log.configure(state='disabled')

    def _save_robot_position(self):
        name = (self.entry_robot_pos_name.get() or '').strip()
        if not name:
            messagebox.showwarning('Robot', 'Ingresa un nombre para la posición')
            return
        
        # Validar nombre - O(n) donde n es longitud del nombre (pequeño)
        if not name.replace('_', '').isalnum():
            messagebox.showerror('Robot', 'El nombre solo puede contener letras, números y _')
            return
        
        # Guardar en diccionario - O(1) operación
        self.robot_positions[name] = name
        vals = list(self.robot_positions.keys())
        self.combo_robot_positions['values'] = vals
        self.combo_robot_positions.set(name)
        self.entry_robot_pos_name.delete(0, tk.END)
        
        # Enviar HERE a la cola - O(1)
        cmd = f"HERE {name}"
        if self._robot_queue_cmd(cmd):
            self._append_robot_log(f'💾 Posición "{name}" guardada (ejecutando...)')
        else:
            messagebox.showwarning('Robot', 'Comando en cola - verifica conexión')

    def _goto_robot_position(self):
        name = (self.combo_robot_positions.get() or '').strip()
        if not name:
            messagebox.showwarning('Robot', 'Selecciona una posición válida')
            return
        
        # Enviar a cola - O(1), no bloquea UI
        cmd = f"MOVE {name}"
        if self._robot_queue_cmd(cmd):
            self._append_robot_log(f'📍 Movimiento a "{name}" en cola')
        else:
            messagebox.showwarning('Robot', 'No se pudo encolar comando')
    
    def _delete_robot_position(self):
        name = (self.combo_robot_positions.get() or '').strip()
        if not name:
            return
        if messagebox.askyesno('Confirmar', f'¿Borrar posición "{name}"?'):
            self.robot_positions.pop(name, None)
            vals = list(self.robot_positions.keys())
            self.combo_robot_positions['values'] = vals
            self.combo_robot_positions.set('')
            self._append_robot_log(f'🗑 Posición "{name}" eliminada')
    
    def _new_sequence(self):
        name = (self.entry_seq_name.get() or '').strip()
        if not name:
            messagebox.showwarning('Secuencias', 'Ingresa un nombre para la secuencia')
            return
        if name in self.robot_sequences:
            if not messagebox.askyesno('Confirmar', f'¿Sobrescribir secuencia "{name}"?'):
                return
        self.robot_sequences[name] = []
        vals = list(self.robot_sequences.keys())
        self.combo_sequences['values'] = vals
        self.combo_sequences.set(name)
        self._append_robot_log(f'📝 Secuencia "{name}" creada')
    
    def _add_to_sequence(self):
        seq_name = (self.combo_sequences.get() or '').strip()
        if not seq_name or seq_name not in self.robot_sequences:
            messagebox.showwarning('Secuencias', 'Selecciona o crea una secuencia primero')
            return
        
        cmd = (self.entry_robot_cmd.get() or '').strip()
        if not cmd:
            messagebox.showwarning('Secuencias', 'Ingresa un comando en "Comando/Posición"')
            return
        
        self.robot_sequences[seq_name].append(cmd.upper())
        self._append_robot_log(f'➕ Agregado a "{seq_name}": {cmd}')
        self.entry_robot_cmd.delete(0, tk.END)
    
    def _run_sequence(self):
        name = (self.combo_sequences.get() or '').strip()
        if not name or name not in self.robot_sequences:
            messagebox.showwarning('Secuencias', 'Selecciona una secuencia válida')
            return
        
        # Acceso a diccionario - O(1)
        seq = self.robot_sequences[name]
        if not seq:
            messagebox.showwarning('Secuencias', 'La secuencia está vacía')
            return
        
        self._append_robot_log(f'▶ Ejecutando secuencia "{name}" ({len(seq)} comandos)')
        
        # Agregar todos los comandos a la cola - O(n) donde n = número de comandos
        # Pero cada put es O(1), así que complejidad total es O(n)
        count = 0
        for cmd in seq:
            if self._robot_queue_cmd(cmd):
                count += 1
            else:
                break
        
        if count == len(seq):
            self._append_robot_log(f'✓ {count} comandos en cola para "{name}"')
        else:
            self._append_robot_log(f'⚠ Solo {count}/{len(seq)} comandos encolados')
    
    def _view_sequence(self):
        name = (self.combo_sequences.get() or '').strip()
        if not name or name not in self.robot_sequences:
            return
        
        seq = self.robot_sequences[name]
        msg = f'Secuencia: {name}\n\n'
        if seq:
            for i, cmd in enumerate(seq, 1):
                msg += f'{i}. {cmd}\n'
        else:
            msg += '(vacía)'
        
        messagebox.showinfo('Ver Secuencia', msg)
    
    def _delete_sequence(self):
        name = (self.combo_sequences.get() or '').strip()
        if not name or name not in self.robot_sequences:
            return
        
        if messagebox.askyesno('Confirmar', f'¿Borrar secuencia "{name}"?'):
            self.robot_sequences.pop(name, None)
            vals = list(self.robot_sequences.keys())
            self.combo_sequences['values'] = vals
            self.combo_sequences.set('')
            self._append_robot_log(f'🗑 Secuencia "{name}" eliminada')


    # ---------------------- Laser panel ----------------------
    def _build_laser_panel(self, parent):
        frame = ttk.LabelFrame(parent, text='Sistema Láser', padding=8)
        frame.pack(fill=tk.BOTH, expand=False, padx=8, pady=8)

        top = ttk.Frame(frame)
        top.pack(fill=tk.X)
        ttk.Button(top, text='Conectar Láser', command=self._connect_laser).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text='Desconectar', command=self._disconnect_laser).pack(side=tk.LEFT, padx=6)

        mid = ttk.Frame(frame)
        mid.pack(fill=tk.X, pady=6)
        ttk.Button(mid, text='Seleccionar Imagen', command=self._select_laser_image).pack(side=tk.LEFT, padx=6)
        ttk.Button(mid, text='Generar G-code (sim)', command=self._generate_gcode_sim).pack(side=tk.LEFT, padx=6)
        ttk.Button(mid, text='Iniciar Grabado (sim)', command=self._start_laser_sim).pack(side=tk.LEFT, padx=6)

        # Offset / posiciones del láser
        pos_frame = ttk.Frame(frame)
        pos_frame.pack(fill=tk.X, pady=(8,4))

        ttk.Label(pos_frame, text='Offset X (mm):').pack(side=tk.LEFT, padx=(0,4))
        self.entry_offset_x = ttk.Entry(pos_frame, width=8)
        self.entry_offset_x.insert(0, '0.0')
        self.entry_offset_x.pack(side=tk.LEFT, padx=(0,8))

        ttk.Label(pos_frame, text='Offset Y (mm):').pack(side=tk.LEFT, padx=(0,4))
        self.entry_offset_y = ttk.Entry(pos_frame, width=8)
        self.entry_offset_y.insert(0, '0.0')
        self.entry_offset_y.pack(side=tk.LEFT, padx=(0,8))

        ttk.Button(pos_frame, text='Ir a Offset', command=self._goto_offset_from_entries).pack(side=tk.LEFT, padx=6)

        # Posiciones guardadas
        save_frame = ttk.Frame(frame)
        save_frame.pack(fill=tk.X, pady=(4,6))
        ttk.Label(save_frame, text='Nombre posición:').pack(side=tk.LEFT, padx=(0,4))
        self.entry_pos_name = ttk.Entry(save_frame, width=12)
        self.entry_pos_name.pack(side=tk.LEFT, padx=(0,8))
        ttk.Button(save_frame, text='Guardar Posición', command=self._save_laser_position).pack(side=tk.LEFT, padx=6)

        ttk.Label(save_frame, text='Posiciones:').pack(side=tk.LEFT, padx=(12,4))
        self.combo_positions = ttk.Combobox(save_frame, values=list(self.laser_positions.keys()), state='readonly', width=16)
        self.combo_positions.pack(side=tk.LEFT, padx=(0,6))
        ttk.Button(save_frame, text='Ir a Posición', command=self._goto_laser_position).pack(side=tk.LEFT, padx=6)

        self.laser_log = tk.Text(frame, height=6, state=tk.DISABLED)
        self.laser_log.pack(fill=tk.BOTH, pady=6)

        self.laser_image_path = None

    def _connect_laser(self):
        if serial is None:
            messagebox.showinfo('Laser','pyserial no instalado - modo simulación')
            return
        ports = self._list_serial_ports()
        if not ports:
            messagebox.showwarning('Laser','No se encontraron puertos')
            return
        try:
            self.ser_laser = serial.Serial(ports[0], baudrate=115200, timeout=1)
            self._append_laser_log(f'Laser conectado en {ports[0]}')
        except Exception as e:
            messagebox.showerror('Laser', f'No se pudo conectar: {e}')

    def _disconnect_laser(self):
        try:
            if self.ser_laser and self.ser_laser.is_open:
                self.ser_laser.close()
            self._append_laser_log('Laser desconectado')
        except Exception:
            pass

    def _select_laser_image(self):
        path = filedialog.askopenfilename(title='Seleccionar imagen', filetypes=[('Images','*.png;*.jpg;*.bmp'),('All','*.*')])
        if path:
            self.laser_image_path = path
            self._append_laser_log(f'Imagen seleccionada: {os.path.basename(path)}')

    def _generate_gcode_sim(self):
        if not self.laser_image_path:
            messagebox.showwarning('Laser','Selecciona una imagen primero')
            return
        # If project provides generate_gcode_text we could use it — here we simulate
        self._append_laser_log('G-code generado (simulado)')

    def _start_laser_sim(self):
        self._append_laser_log('Grabado iniciado (SIM) — no enviar comandos reales')

    def _append_laser_log(self, msg):
        ts = time.strftime('%H:%M:%S')
        self.laser_log.configure(state='normal')
        self.laser_log.insert('end', f"[{ts}] {msg}\n")
        self.laser_log.see('end')
        self.laser_log.configure(state='disabled')

    def _save_laser_position(self):
        name = (self.entry_pos_name.get() or '').strip()
        if not name:
            messagebox.showwarning('Laser', 'Ingresa un nombre para la posición')
            return
        try:
            x = float(self.entry_offset_x.get())
            y = float(self.entry_offset_y.get())
        except Exception:
            messagebox.showerror('Laser', 'Offsets inválidos')
            return
        self.laser_positions[name] = (x, y)
        # actualizar combobox
        vals = list(self.laser_positions.keys())
        self.combo_positions['values'] = vals
        self.combo_positions.set(name)
        self._append_laser_log(f'Posición guardada: {name} -> X={x} Y={y}')

    def _goto_laser_position(self):
        name = (self.combo_positions.get() or '').strip()
        if not name or name not in self.laser_positions:
            messagebox.showwarning('Laser', 'Selecciona una posición válida')
            return
        x, y = self.laser_positions[name]
        self._send_laser_move(x, y)

    def _goto_offset_from_entries(self):
        try:
            x = float(self.entry_offset_x.get())
            y = float(self.entry_offset_y.get())
        except Exception:
            messagebox.showerror('Laser', 'Offsets inválidos')
            return
        self._send_laser_move(x, y)

    def _send_laser_move(self, x_mm, y_mm):
        # Envía comando de movimiento al láser / controlador GRBL
        cmd = f"G0 X{x_mm:.4f} Y{y_mm:.4f}"
        if self.ser_laser and getattr(self.ser_laser, 'is_open', False):
            try:
                self.ser_laser.write((cmd + '\r\n').encode())
                self._append_laser_log(f'Enviado movimiento: {cmd}')
            except Exception as e:
                self._append_laser_log(f'Error enviando movimiento: {e}')
        else:
            self._append_laser_log(f'(SIM) Movimiento simulado: {cmd}')

    # ---------------------- ArUco generator panel ----------------------
    def _build_aruco_panel(self, parent):
        frame = ttk.LabelFrame(parent, text='Generador ArUco', padding=8)
        frame.pack(fill=tk.BOTH, expand=False, padx=8, pady=8)

        row = ttk.Frame(frame); row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text='ID:').pack(side=tk.LEFT)
        self.entry_aruco_id = ttk.Entry(row, width=6); self.entry_aruco_id.insert(0,'1'); self.entry_aruco_id.pack(side=tk.LEFT, padx=6)
        ttk.Label(row, text='Tamaño(px):').pack(side=tk.LEFT)
        self.entry_aruco_size = ttk.Entry(row, width=6); self.entry_aruco_size.insert(0,'200'); self.entry_aruco_size.pack(side=tk.LEFT, padx=6)
        ttk.Button(row, text='Generar', command=self._generate_aruco_image).pack(side=tk.LEFT, padx=6)
        ttk.Button(row, text='Usar con Láser', command=self._use_aruco_with_laser).pack(side=tk.LEFT, padx=6)

        self.aruco_preview = ttk.Label(frame, text='(preview)')
        self.aruco_preview.pack(pady=6)

    def _generate_aruco_image(self):
        try:
            import cv2
            import numpy as np
            idv = int(self.entry_aruco_id.get())
            size = int(self.entry_aruco_size.get())
            dic = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100)
            marker = cv2.aruco.generateImageMarker(dic, idv, size)
            
            # Guardar la imagen generada para usar en el láser
            import tempfile
            temp_dir = tempfile.gettempdir()
            self.aruco_generated_path = os.path.join(temp_dir, f'aruco_{idv}_{size}.png')
            cv2.imwrite(self.aruco_generated_path, marker)
            
            img = Image.fromarray(marker)
            img = img.resize((150,150))
            self.aruco_imgtk = ImageTk.PhotoImage(img)
            self.aruco_preview.config(image=self.aruco_imgtk, text='')
            self._append_laser_log(f'ArUco generado y guardado: {os.path.basename(self.aruco_generated_path)}')
        except Exception as e:
            messagebox.showerror('ArUco', f'Error generando ArUco: {e}')

    def _use_aruco_with_laser(self):
        """Usa la imagen ArUco generada con el sistema de láser."""
        if not self.aruco_generated_path or not os.path.exists(self.aruco_generated_path):
            messagebox.showwarning('ArUco', 'Genera una imagen ArUco primero')
            return
        # Establecer la imagen generada como la imagen del láser
        self.laser_image_path = self.aruco_generated_path
        self._append_laser_log(f'Imagen ArUco cargada para láser: {os.path.basename(self.laser_image_path)}')
        messagebox.showinfo('ArUco', f'Imagen ArUco lista para grabar:\n{os.path.basename(self.laser_image_path)}')

    # ---------------------- Camera panel ----------------------
    def _build_camera_panel(self, parent, title='Cámara / Detección'):
        frame = ttk.LabelFrame(parent, text=title, padding=8)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        top = ttk.Frame(frame); top.pack(fill=tk.X)
        ttk.Label(top, text='Cámara:').pack(side=tk.LEFT, padx=6)
        self.camera_combo = ttk.Combobox(top, values=['Cámara 0', 'Cámara 1'], state='readonly', width=12)
        self.camera_combo.set('Cámara 0')
        self.camera_combo.pack(side=tk.LEFT, padx=6)
        self.camera_combo.bind('<<ComboboxSelected>>', self._on_camera_selected)
        ttk.Button(top, text='Iniciar Cámara', command=self._start_camera).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text='Detener Cámara', command=self._stop_camera).pack(side=tk.LEFT, padx=6)

        # Usamos tk.Label porque ttk.Label no admite height/width en algunos temas
        self.cam_label = tk.Label(frame, text='Cam preview', width=90, height=26, anchor='center', relief=tk.SUNKEN)
        self.cam_label.pack(fill=tk.BOTH, expand=True, padx=(2, 4), pady=4)

    def _on_camera_selected(self, event=None):
        """Actualizar el índice de cámara seleccionada"""
        if self.camera_combo.get() == 'Cámara 0':
            self.camera_index = 0
        else:
            self.camera_index = 1
        
        # Si la cámara está en ejecución, reiniciarla
        if self.cam_running:
            self._stop_camera()
            time.sleep(0.5)
            self._start_camera()

    def _camera_loop(self):
        try:
            import cv2
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            # Bajar resolución base para acelerar la inferencia y refresco
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            if not cap.isOpened():
                self._append_laser_log(f'No se pudo abrir cámara ({self.camera_index})')
                return

            frame_idx = 0
            last_detected_frame = None
            while self.cam_running:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.01)
                    continue

                frame_idx += 1
                display_frame = frame.copy()

                # --- DETECCIÓN CON YOLO EN CADA FRAME ---
                if self.model_yolo:
                    try:
                        results = self.model_yolo.predict(display_frame, conf=0.79, verbose=False)
                        display_frame = results[0].plot()
                        last_detected_frame = display_frame.copy()
                    except Exception as e:
                        self._append_laser_log(f'Error en detección YOLO: {e}')
                        # Si hay error, usa el último frame detectado o el frame actual
                        if last_detected_frame is not None:
                            display_frame = last_detected_frame.copy()

                # Redimensionar y convertir para la interfaz de Tkinter
                frame_rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
                frame_rgb = cv2.resize(frame_rgb, (960, 540))
                img = Image.fromarray(frame_rgb)
                imgtk = ImageTk.PhotoImage(img)

                # Actualizar la UI en el hilo principal
                self.root.after(0, lambda i=imgtk: self.cam_label.config(image=i) or setattr(self, 'last_cam_img', i))

            cap.release()
        except Exception as e:
            self._append_laser_log(f'Error en loop de cámara: {e}')

    def _start_camera(self):
        if self.cam_running:
            return
        self.cam_running = True
        self.cam_thread = threading.Thread(target=self._camera_loop, daemon=True)
        self.cam_thread.start()
        self._append_laser_log('Cámara iniciada')

    def _stop_camera(self):
        self.cam_running = False
        self._append_laser_log('Cámara detenida')

    # ---------------------- Network panel ----------------------
    def _build_network_panel(self, parent):
        frame = ttk.LabelFrame(parent, text='Comunicaciones TCP', padding=8)
        frame.pack(fill=tk.BOTH, expand=True)

        srv = ttk.LabelFrame(frame, text='Servidor (host)', padding=6)
        srv.pack(fill=tk.X, pady=(0,6))
        ttk.Label(srv, text='Host: 0.0.0.0').pack(side=tk.LEFT, padx=4)
        ttk.Label(srv, text='Puerto:').pack(side=tk.LEFT)
        self.entry_srv_port = ttk.Entry(srv, width=8)
        self.entry_srv_port.insert(0, '8888')
        self.entry_srv_port.pack(side=tk.LEFT, padx=(2,8))
        self.btn_srv_start = ttk.Button(srv, text='Iniciar', command=self._start_server)
        self.btn_srv_start.pack(side=tk.LEFT, padx=4)
        self.btn_srv_stop = ttk.Button(srv, text='Detener', command=self._stop_server, state=tk.DISABLED)
        self.btn_srv_stop.pack(side=tk.LEFT, padx=4)
        self.label_srv_status = ttk.Label(srv, text='Servidor detenido', foreground='red')
        self.label_srv_status.pack(side=tk.LEFT, padx=8)

        cli = ttk.LabelFrame(frame, text='Cliente (conectar a otro panel)', padding=6)
        cli.pack(fill=tk.X, pady=(0,6))
        ttk.Label(cli, text='Host:').pack(side=tk.LEFT, padx=(2,2))
        self.entry_cli_host = ttk.Entry(cli, width=14)
        self.entry_cli_host.insert(0, '127.0.0.1')
        self.entry_cli_host.pack(side=tk.LEFT, padx=(0,6))
        ttk.Label(cli, text='Puerto:').pack(side=tk.LEFT)
        self.entry_cli_port = ttk.Entry(cli, width=8)
        self.entry_cli_port.insert(0, '8888')
        self.entry_cli_port.pack(side=tk.LEFT, padx=(2,6))
        ttk.Label(cli, text='Nombre:').pack(side=tk.LEFT)
        self.entry_cli_name = ttk.Entry(cli, width=12)
        self.entry_cli_name.insert(0, 'Panel')
        self.entry_cli_name.pack(side=tk.LEFT, padx=(2,6))
        self.btn_cli_connect = ttk.Button(cli, text='Conectar', command=self._connect_client)
        self.btn_cli_connect.pack(side=tk.LEFT, padx=4)
        self.btn_cli_disconnect = ttk.Button(cli, text='Desconectar', command=self._disconnect_client, state=tk.DISABLED)
        self.btn_cli_disconnect.pack(side=tk.LEFT, padx=4)

        send = ttk.Frame(frame)
        send.pack(fill=tk.X, pady=(4,4))
        ttk.Label(send, text='Mensaje / comando:').pack(side=tk.LEFT, padx=(2,4))
        self.entry_net_msg = ttk.Entry(send)
        self.entry_net_msg.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,6))
        ttk.Button(send, text='Enviar', command=self._net_send_manual).pack(side=tk.LEFT, padx=2)

        logf = ttk.LabelFrame(frame, text='Log de red', padding=4)
        logf.pack(fill=tk.BOTH, expand=True)
        self.net_log = tk.Text(logf, height=10, state=tk.DISABLED)
        self.net_log.pack(fill=tk.BOTH, expand=True)

    def _append_net_log(self, msg):
        ts = time.strftime('%H:%M:%S')
        self.net_log.configure(state='normal')
        self.net_log.insert('end', f"[{ts}] {msg}\n")
        self.net_log.see('end')
        self.net_log.configure(state='disabled')

    def _start_server(self):
        if self.server_running:
            return
        try:
            port = int(self.entry_srv_port.get())
        except Exception:
            messagebox.showerror('Servidor', 'Puerto inválido')
            return
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)
            self.server_running = True
            self.server_connections = []
            self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self.server_thread.start()
            self.label_srv_status.config(text=f'Servidor escuchando {port}', foreground='green')
            self.btn_srv_start.config(state=tk.DISABLED)
            self.btn_srv_stop.config(state=tk.NORMAL)
            self._append_net_log(f'Servidor iniciado en puerto {port}')
        except Exception as e:
            messagebox.showerror('Servidor', f'No se pudo iniciar:\n{e}')
            try:
                if self.server_socket:
                    self.server_socket.close()
            except Exception:
                pass
            self.server_running = False

    def _stop_server(self):
        self.server_running = False
        try:
            if self.server_socket:
                self.server_socket.close()
        except Exception:
            pass
        for conn, _addr, _name in list(self.server_connections):
            try:
                conn.close()
            except Exception:
                pass
        self.server_connections.clear()
        self.label_srv_status.config(text='Servidor detenido', foreground='red')
        self.btn_srv_start.config(state=tk.NORMAL)
        self.btn_srv_stop.config(state=tk.DISABLED)
        self._append_net_log('Servidor detenido')

    def _server_loop(self):
        while self.server_running:
            try:
                conn, addr = self.server_socket.accept()
            except socket.timeout:
                continue
            except Exception:
                break

            name = f"{addr[0]}:{addr[1]}"
            try:
                conn.settimeout(1.0)
            except Exception:
                pass
            self.server_connections.append((conn, addr, name))
            self.net_queue.put(('log', f'Cliente conectado: {name}'))
            t = threading.Thread(target=self._handle_client_conn, args=(conn, addr, name), daemon=True)
            t.start()

    def _handle_client_conn(self, conn, addr, name):
        buffer = ''
        try:
            data = conn.recv(1024)
            if data:
                first = data.decode(errors='ignore').strip()
                if first:
                    name = first
        except Exception:
            pass

        while self.server_running:
            try:
                data = conn.recv(1024)
                if not data:
                    break
                buffer += data.decode(errors='ignore')
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if line:
                        self.net_queue.put(('cmd', f'cliente {name}', line))
            except socket.timeout:
                continue
            except Exception:
                break

        try:
            conn.close()
        except Exception:
            pass
        self.server_connections = [(c,a,n) for (c,a,n) in self.server_connections if c != conn]
        self.net_queue.put(('log', f'Conexión cerrada: {name}'))

    def _connect_client(self):
        if self.client_connected:
            return
        host = self.entry_cli_host.get().strip() or '127.0.0.1'
        try:
            port = int(self.entry_cli_port.get())
        except Exception:
            messagebox.showerror('Cliente', 'Puerto inválido')
            return

        def worker():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((host, port))
                sock.settimeout(1.0)
                name = (self.entry_cli_name.get() or 'Panel').strip()
                try:
                    sock.sendall((name + '\n').encode())
                except Exception:
                    pass
                self.client_socket = sock
                self.client_connected = True
                self.net_queue.put(('log', f'Cliente conectado a {host}:{port}'))
                self.client_thread = threading.Thread(target=self._client_recv_loop, daemon=True)
                self.client_thread.start()
                self.root.after(0, lambda: self.btn_cli_connect.config(state=tk.DISABLED))
                self.root.after(0, lambda: self.btn_cli_disconnect.config(state=tk.NORMAL))
            except Exception as e:
                self.net_queue.put(('log', f'Error de conexión: {e}'))
                try:
                    sock.close()
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def _disconnect_client(self):
        self.client_connected = False
        try:
            if self.client_socket:
                self.client_socket.close()
        except Exception:
            pass
        self.client_socket = None
        self.btn_cli_connect.config(state=tk.NORMAL)
        self.btn_cli_disconnect.config(state=tk.DISABLED)
        self._append_net_log('Cliente desconectado')

    def _client_recv_loop(self):
        buffer = ''
        while self.client_connected and self.client_socket:
            try:
                data = self.client_socket.recv(1024)
                if not data:
                    break
                buffer += data.decode(errors='ignore')
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if line:
                        self.net_queue.put(('cmd', 'servidor', line))
            except socket.timeout:
                continue
            except Exception:
                break
        self.client_connected = False
        self.net_queue.put(('log', 'Conexión cerrada por el servidor'))
        self.root.after(0, lambda: self.btn_cli_connect.config(state=tk.NORMAL))
        self.root.after(0, lambda: self.btn_cli_disconnect.config(state=tk.DISABLED))

    def _net_send_manual(self):
        txt = self.entry_net_msg.get().strip()
        if not txt:
            return
        self.entry_net_msg.delete(0, tk.END)
        self._net_send_line(txt)
        self._append_net_log(f'Tú -> {txt}')

    def _net_broadcast_plc(self, action, estacion, pallet):
        msg = f"PLC,{estacion},{pallet},{action}"
        self._net_send_line(msg)

    def _net_send_line(self, text):
        payload = (text.strip() + '\n').encode()
        if self.server_running:
            for conn, _addr, name in list(self.server_connections):
                try:
                    conn.sendall(payload)
                except Exception:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    try:
                        self.server_connections.remove((conn, _addr, name))
                    except Exception:
                        pass
        if self.client_connected and self.client_socket:
            try:
                self.client_socket.sendall(payload)
            except Exception:
                self.client_connected = False

    def _net_ui_pump(self):
        try:
            while True:
                item = self.net_queue.get_nowait()
                if not item:
                    break
                kind = item[0]
                if kind == 'log':
                    self._append_net_log(item[1])
                elif kind == 'cmd':
                    _src, line = item[1], item[2]
                    self._append_net_log(f'{item[1]} -> {line}')
                    self._handle_net_command(line, source=item[1])
        except queue.Empty:
            pass
        self.root.after(300, self._net_ui_pump)

    def _handle_net_command(self, line, source='net'):
        txt = line.strip()
        if not txt:
            return
        parts = [p.strip() for p in txt.split(',') if p.strip()]
        if not parts:
            return
        head = parts[0].lower()
        if head == 'plc' and len(parts) >= 4:
            try:
                est = int(parts[1]); pal = int(parts[2]); act = parts[3].lower()
            except Exception:
                self._append_net_log('Comando PLC inválido')
                return
            if act.startswith('del'):
                self._append_net_log(f'Acción remota: DELIVER E{est} P{pal}')
                self._send_deliver(est, pal, broadcast=False)
            elif act.startswith('free'):
                self._append_net_log(f'Acción remota: FREE E{est} P{pal}')
                self._send_free(est, pal, broadcast=False)
            else:
                self._append_net_log(f'Acción PLC desconocida: {act}')
            return
        # Por ahora, otros mensajes solo se muestran en el log
        self._append_net_log(f'Mensaje recibido ({source}): {txt}')

    # ---------------------- Robot QC (Quality Control) Panel ----------------------
    def _build_robot_qc_panel(self, parent):
        """Panel de control para robot SCORBOT-ER V plus con programas de control de calidad."""
        # Título principal
        title_frame = ttk.Frame(parent)
        title_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(title_frame, text="SCORBOT-ER V plus - Control de Calidad", 
                 font=('Arial', 14, 'bold')).pack(side=tk.LEFT)
        
        ttk.Label(title_frame, text="Puerto: COM6", 
                 font=('Arial', 10)).pack(side=tk.LEFT, padx=20)
        
        # Frame principal con 2 columnas: controles + log
        main_frame = ttk.Frame(parent)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # ===== COLUMNA 1: Botones de Programas =====
        control_frame = ttk.LabelFrame(main_frame, text="Programas de Movimiento", padding=20)
        control_frame.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)
        
        # Información de estado
        status_frame = ttk.Frame(control_frame)
        status_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(status_frame, text="Estado del Robot:", font=('Arial', 10, 'bold')).pack(side=tk.LEFT)
        self.lbl_qc_robot_status = ttk.Label(status_frame, text="Desconectado", 
                                            font=('Arial', 10), foreground='red')
        self.lbl_qc_robot_status.pack(side=tk.LEFT, padx=10)
        
        # Botón de conexión
        conn_frame = ttk.Frame(control_frame)
        conn_frame.pack(fill=tk.X, pady=10)
        
        self.btn_qc_connect = ttk.Button(conn_frame, text="Conectar Robot (COM6)", 
                                        command=self._qc_connect_robot)
        self.btn_qc_connect.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        self.btn_qc_disconnect = ttk.Button(conn_frame, text="Desconectar", 
                                           command=self._qc_disconnect_robot, state="disabled")
        self.btn_qc_disconnect.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Separador
        ttk.Separator(control_frame, orient='horizontal').pack(fill=tk.X, pady=10)
        
        # Botones de programas: SR1, SR2, SR3, SR4
        programs = [
            ('SR1', 'SR1', '🔵 SR1 - Programa 1'),
            ('SR2', 'SR2', '🟢 SR2 - Programa 2'),
            ('SR3', 'SR3', '🟡 SR3 - Programa 3'),
            ('SR4', 'SR4', '🔴 SR4 - Programa 4'),
        ]
        
        for i, (prog_name, prog_code, display_name) in enumerate(programs):
            btn_frame = ttk.Frame(control_frame)
            btn_frame.pack(fill=tk.X, pady=8)
            
            btn = ttk.Button(btn_frame, text=display_name, 
                           command=lambda code=prog_code: self._qc_execute_program(code),
                           width=30)
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            # Etiqueta de estado
            status_label = ttk.Label(btn_frame, text="○", font=('Arial', 12))
            status_label.pack(side=tk.LEFT, padx=10)
            
            # Guardar referencia para actualizar estado
            if prog_name == 'SR1':
                self.lbl_qc_sr1_status = status_label
            elif prog_name == 'SR2':
                self.lbl_qc_sr2_status = status_label
            elif prog_name == 'SR3':
                self.lbl_qc_sr3_status = status_label
            elif prog_name == 'SR4':
                self.lbl_qc_sr4_status = status_label
        
        # Separador
        ttk.Separator(control_frame, orient='horizontal').pack(fill=tk.X, pady=10)
        
        # Botones adicionales de control
        extra_frame = ttk.Frame(control_frame)
        extra_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(extra_frame, text="Home", 
                  command=lambda: self._qc_send_command('HOME')).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(extra_frame, text="Ready", 
                  command=lambda: self._qc_send_command('READY')).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(extra_frame, text="Detener", 
                  command=lambda: self._qc_send_command('COFF')).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Instrucciones
        instr_frame = ttk.LabelFrame(control_frame, text="Instrucciones", padding=10)
        instr_frame.pack(fill=tk.X, pady=10)
        
        instructions = """1. Click 'Conectar Robot (COM6)' para iniciar
2. Selecciona un programa (SR1, SR2, SR3 o SR4)
3. El robot ejecutará el programa almacenado
4. Observa el estado en el panel de log
5. Click 'Desconectar' cuando termines"""
        
        ttk.Label(instr_frame, text=instructions, font=('Arial', 9), 
                 justify=tk.LEFT).pack(anchor=tk.W)
        
        # ===== COLUMNA 2: Log de Ejecución =====
        log_frame = ttk.LabelFrame(main_frame, text="Registro de Ejecución", padding=10)
        log_frame.grid(row=0, column=1, sticky='nsew', padx=5, pady=5)
        
        self.text_qc_log = tk.Text(log_frame, height=30, width=50, 
                                   font=('Consolas', 9), wrap=tk.WORD)
        self.text_qc_log.pack(fill=tk.BOTH, expand=True)
        
        # Scrollbar para el log
        scrollbar = ttk.Scrollbar(log_frame, orient='vertical', command=self.text_qc_log.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text_qc_log.config(yscrollcommand=scrollbar.set)
        
        # Botón para limpiar log
        clear_btn = ttk.Button(log_frame, text="Limpiar Log", 
                              command=self._qc_clear_log)
        clear_btn.pack(fill=tk.X, pady=5)
        
        # Configurar grid
        main_frame.columnconfigure(0, weight=0)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)
        
        # Estado inicial
        self._qc_append_log("Sistema listo. Haga click en 'Conectar Robot (COM6)' para comenzar.")
    
    def _qc_connect_robot(self):
        """Conecta el robot a través del puerto COM6."""
        try:
            if serial is None:
                messagebox.showwarning('Robot QC', 'pyserial no instalado - modo simulación')
                return
            
            # Usar COM6 directamente
            port = 'COM6'
            
            try:
                if self.ser_robot is not None and self.ser_robot.is_open:
                    # Si ya hay un robot conectado, lo desconectamos primero
                    self._qc_disconnect_robot()
            except:
                pass
            
            # Conectar al robot en COM6
            self.ser_robot = serial.Serial(port, baudrate=9600, bytesize=serial.EIGHTBITS, 
                                          parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, 
                                          timeout=2)
            self.ser_robot.reset_input_buffer()
            self.ser_robot.reset_output_buffer()
            
            # Iniciar cola de comandos si no está corriendo
            if not self.robot_queue_running:
                self.robot_queue_running = True
                self.robot_queue_thread = threading.Thread(target=self._robot_queue_worker, daemon=True)
                self.robot_queue_thread.start()
            
            # Actualizar UI
            self.lbl_qc_robot_status.config(text='Conectado', foreground='green')
            self.btn_qc_connect.config(state='disabled')
            self.btn_qc_disconnect.config(state='normal')
            
            self._qc_append_log(f'✓ Robot conectado en {port}')
            
            # Iniciar lector de stream
            if not self.robot_stream_polling:
                self.robot_stream_polling = True
                self._robot_start_stream_reader()
            
            # Enviar comandos iniciales
            time.sleep(0.3)
            self._qc_send_command('READY')
            
        except Exception as e:
            messagebox.showerror('Robot QC', f'No se pudo conectar en COM6:\n{str(e)}')
            self.lbl_qc_robot_status.config(text='Error', foreground='red')
    
    def _qc_disconnect_robot(self):
        """Desconecta el robot."""
        try:
            self.robot_queue_running = False
            
            if self.ser_robot and getattr(self.ser_robot, 'is_open', False):
                try:
                    self._qc_send_command('COFF')
                    time.sleep(0.3)
                except Exception:
                    pass
                self.ser_robot.close()
            
            # Actualizar UI
            self.lbl_qc_robot_status.config(text='Desconectado', foreground='red')
            self.btn_qc_connect.config(state='normal')
            self.btn_qc_disconnect.config(state='disabled')
            
            self._qc_append_log('✓ Robot desconectado')
            
        except Exception as e:
            self._qc_append_log(f'⚠ Error al desconectar: {str(e)}')
    
    def _qc_execute_program(self, program_name):
        """Ejecuta un programa específico del robot (SR1, SR2, SR3 o SR4)."""
        if not self.ser_robot or not self.ser_robot.is_open:
            messagebox.showwarning('Robot QC', 'El robot no está conectado')
            self._qc_append_log('⚠ Error: Robot no conectado')
            return
        
        self._qc_append_log(f'▶ Iniciando programa {program_name}...')
        
        # Ejecutar el programa enviando el comando RUN
        command = f'RUN {program_name}'
        self._qc_send_command(command)
    
    def _qc_send_command(self, command):
        """Envía un comando al robot."""
        if not self.ser_robot or not self.ser_robot.is_open:
            self._qc_append_log('⚠ Robot no conectado')
            return False
        
        try:
            cmd_clean = command.strip().upper()
            payload = (cmd_clean + '\r').encode('ascii', errors='ignore')
            
            self.ser_robot.write(payload)
            self.ser_robot.flush()
            
            self._qc_append_log(f'→ Enviado: {cmd_clean}')
            
            # Esperar respuesta breve
            time.sleep(0.1)
            waiting = self.ser_robot.in_waiting
            if waiting > 0:
                response = self.ser_robot.read(waiting).decode('ascii', errors='ignore')
                self._qc_append_log(f'← Respuesta: {response.strip()}')
            
            return True
            
        except Exception as e:
            self._qc_append_log(f'✗ Error enviando comando: {str(e)}')
            return False
    
    def _qc_append_log(self, message):
        """Añade un mensaje al log con timestamp."""
        import datetime
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        log_message = f'[{timestamp}] {message}\n'
        
        self.text_qc_log.insert(tk.END, log_message)
        self.text_qc_log.see(tk.END)  # Scroll automático
        self.root.update_idletasks()
    
    def _qc_clear_log(self):
        """Limpia el log de ejecución."""
        self.text_qc_log.delete(1.0, tk.END)
        self._qc_append_log('Log limpiado')

    # ---------------------- Advanced Robot Control panel ----------------------
    def _build_advanced_robot_panel(self, parent):
        """Panel de control avanzado del robot con movimientos por ejes y grabación."""
        # Frame principal con 3 columnas
        main_container = ttk.Frame(parent)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # ===== COLUMNA 1: Movimientos por Ejes =====
        frame_movimientos = ttk.LabelFrame(main_container, text="Movimientos por Ejes", padding=10)
        frame_movimientos.grid(row=0, column=0, padx=5, pady=5, sticky=tk.NSEW)
        
        # Control de incremento
        inc_frame = ttk.Frame(frame_movimientos)
        inc_frame.grid(row=0, column=0, columnspan=2, pady=10)
        ttk.Label(inc_frame, text="Incremento (grados):").pack(side=tk.LEFT, padx=5)
        self.spin_axis_increment = tk.Spinbox(inc_frame, from_=1, to=90, width=10, font=('Arial', 10))
        self.spin_axis_increment.delete(0, tk.END)
        self.spin_axis_increment.insert(0, "10")
        self.spin_axis_increment.pack(side=tk.LEFT, padx=5)
        
        # Botones de ejes
        row = 1
        ejes = [("Base", "BASE"), ("Hombro", "SHOULDER"), ("Codo", "ELBOW"), 
                ("Muñeca", "WRIST"), ("Pitch", "PITCH")]
        
        for label, eje in ejes:
            ttk.Button(frame_movimientos, text=f"{label} +", 
                      command=lambda e=eje: self._mover_eje(e, "+")).grid(
                          row=row, column=0, padx=5, pady=5, sticky=tk.EW)
            ttk.Button(frame_movimientos, text=f"{label} -", 
                      command=lambda e=eje: self._mover_eje(e, "-")).grid(
                          row=row, column=1, padx=5, pady=5, sticky=tk.EW)
            row += 1
        
        # Pinza
        ttk.Button(frame_movimientos, text="Abrir Pinza", 
                  command=self._adv_abrir_pinza).grid(row=row, column=0, padx=5, pady=5, sticky=tk.EW)
        ttk.Button(frame_movimientos, text="Cerrar Pinza", 
                  command=self._adv_cerrar_pinza).grid(row=row, column=1, padx=5, pady=5, sticky=tk.EW)
        
        # Configurar columnas
        frame_movimientos.columnconfigure(0, weight=1)
        frame_movimientos.columnconfigure(1, weight=1)
        
        # ===== COLUMNA 2: Log de Comandos =====
        frame_log = ttk.LabelFrame(main_container, text="Registro de Comandos", padding=10)
        frame_log.grid(row=0, column=1, padx=5, pady=5, sticky=tk.NSEW)
        
        self.adv_robot_log = tk.Text(frame_log, height=25, width=40, font=('Consolas', 9))
        self.adv_robot_log.pack(fill=tk.BOTH, expand=True)
        
        # Botones de comandos rápidos
        quick_frame = ttk.Frame(frame_log)
        quick_frame.pack(fill=tk.X, pady=5)
        # Botones principales: AUTO y programas ARU
        ttk.Button(quick_frame, text="AUTO", command=lambda: self._robot_queue_cmd("AUTO")).pack(side=tk.LEFT, padx=2)
        ttk.Button(quick_frame, text="ARU", command=lambda: self._robot_queue_cmd("RUN ARU")).pack(side=tk.LEFT, padx=2)
        ttk.Button(quick_frame, text="ARU1", command=lambda: self._robot_queue_cmd("RUN ARU1")).pack(side=tk.LEFT, padx=2)
        ttk.Button(quick_frame, text="ARU2", command=lambda: self._robot_queue_cmd("RUN ARU2")).pack(side=tk.LEFT, padx=2)
        ttk.Button(quick_frame, text="ARU3", command=lambda: self._robot_queue_cmd("RUN ARU3")).pack(side=tk.LEFT, padx=2)
        ttk.Button(quick_frame, text="ARU4", command=lambda: self._robot_queue_cmd("RUN ARU4")).pack(side=tk.LEFT, padx=2)
        
        # ===== COLUMNA 3: Grabación de Secuencias =====
        frame_secuencias = ttk.LabelFrame(main_container, text="Grabación de Secuencias", padding=10)
        frame_secuencias.grid(row=0, column=2, padx=5, pady=5, sticky=tk.NSEW)
        
        # Estado de grabación
        self.lbl_axis_recording = ttk.Label(frame_secuencias, text="○ Detenido", 
                                           font=('Arial', 10, 'bold'))
        self.lbl_axis_recording.pack(pady=5)
        
        # Botones de control
        control_frame = ttk.Frame(frame_secuencias)
        control_frame.pack(fill=tk.X, pady=5)
        
        self.btn_axis_start_rec = ttk.Button(control_frame, text="● Iniciar Grabación", 
                                             command=self._start_axis_recording)
        self.btn_axis_start_rec.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        
        self.btn_axis_stop_rec = ttk.Button(control_frame, text="■ Detener", 
                                           command=self._stop_axis_recording, state="disabled")
        self.btn_axis_stop_rec.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        
        # Contador
        self.lbl_axis_seq_count = ttk.Label(frame_secuencias, text="Comandos: 0", font=('Arial', 9))
        self.lbl_axis_seq_count.pack(pady=5)
        
        # Visualización de secuencia
        ttk.Label(frame_secuencias, text="Secuencia Grabada:").pack(anchor=tk.W)
        self.text_axis_sequence = tk.Text(frame_secuencias, height=12, width=35, 
                                         font=('Consolas', 9), state="disabled")
        self.text_axis_sequence.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Botones de acción
        action_frame = ttk.Frame(frame_secuencias)
        action_frame.pack(fill=tk.X, pady=5)
        
        self.btn_axis_execute = ttk.Button(action_frame, text="▶ Ejecutar", 
                                          command=self._execute_axis_sequence, state="disabled")
        self.btn_axis_execute.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        
        self.btn_axis_clear = ttk.Button(action_frame, text="✖ Limpiar", 
                                        command=self._clear_axis_sequence)
        self.btn_axis_clear.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        
        self.btn_axis_save = ttk.Button(action_frame, text="💾 Guardar", 
                                       command=self._save_axis_sequence, state="disabled")
        self.btn_axis_save.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        
        # Instrucciones
        instr = """Instrucciones:
1. Conecte el robot en la pestaña Robot & Laser
2. Click 'Iniciar Grabación'
3. Use los controles de ejes
4. Click 'Detener' cuando termine
5. Click 'Ejecutar' para repetir la secuencia"""
        ttk.Label(frame_secuencias, text=instr, font=('Arial', 8), 
                 justify=tk.LEFT, wraplength=280).pack(anchor=tk.W, pady=5)
        
        # Configurar grid
        main_container.columnconfigure(0, weight=0)
        main_container.columnconfigure(1, weight=1)
        main_container.columnconfigure(2, weight=0)
        main_container.rowconfigure(0, weight=1)
    
    def _mover_eje(self, eje, direccion):
        """Mueve un eje específico del robot."""
        if not self.ser_robot or not self.ser_robot.is_open:
            messagebox.showerror("Error", "Debe conectar el robot primero (pestaña Robot & Laser)")
            return
        
        ejes = {"BASE": 1, "SHOULDER": 2, "ELBOW": 3, "WRIST": 4, "PITCH": 5}
        
        if eje not in ejes:
            return
        
        try:
            increment = int(self.spin_axis_increment.get())
        except:
            increment = 10
        
        value = increment if direccion == "+" else -increment
        joint_num = ejes[eje]
        command = f"MJ {joint_num} {value}"
        
        # Grabar si está en modo grabación
        if self.axis_sequence_recording:
            self.axis_recorded_sequence.append(command)
            self._update_axis_sequence_display()
        
        # Enviar comando
        self._robot_queue_cmd(command)
        self._append_adv_robot_log(f"{eje} {direccion}{abs(value)}°: {command}")
    
    def _adv_abrir_pinza(self):
        """Abre la pinza."""
        if self.axis_sequence_recording:
            self.axis_recorded_sequence.append("OPEN")
            self._update_axis_sequence_display()
        self._robot_queue_cmd("OPEN")
        self._append_adv_robot_log("Pinza ABIERTA")
    
    def _adv_cerrar_pinza(self):
        """Cierra la pinza."""
        if self.axis_sequence_recording:
            self.axis_recorded_sequence.append("CLOSE")
            self._update_axis_sequence_display()
        self._robot_queue_cmd("CLOSE")
        self._append_adv_robot_log("Pinza CERRADA")
    
    def _start_axis_recording(self):
        """Inicia grabación de secuencia de ejes."""
        self.axis_sequence_recording = True
        self.axis_recorded_sequence = []
        self.btn_axis_start_rec.config(state="disabled")
        self.btn_axis_stop_rec.config(state="normal")
        self.btn_axis_execute.config(state="disabled")
        self.btn_axis_save.config(state="disabled")
        self.lbl_axis_recording.config(text="● GRABANDO", foreground="red")
        self._update_axis_sequence_display()
        self._append_adv_robot_log("=== GRABACIÓN INICIADA ===")
    
    def _stop_axis_recording(self):
        """Detiene grabación de secuencia."""
        self.axis_sequence_recording = False
        self.btn_axis_start_rec.config(state="normal")
        self.btn_axis_stop_rec.config(state="disabled")
        if self.axis_recorded_sequence:
            self.btn_axis_execute.config(state="normal")
            self.btn_axis_save.config(state="normal")
        self.lbl_axis_recording.config(text="○ Detenido", foreground="black")
        self._append_adv_robot_log(f"=== GRABACIÓN DETENIDA ({len(self.axis_recorded_sequence)} comandos) ===")
    
    def _execute_axis_sequence(self):
        """Ejecuta la secuencia grabada."""
        if not self.axis_recorded_sequence:
            messagebox.showwarning("Advertencia", "No hay secuencia grabada")
            return
        
        if not self.ser_robot or not self.ser_robot.is_open:
            messagebox.showerror("Error", "Debe conectar el robot primero")
            return
        
        self._append_adv_robot_log(f"=== EJECUTANDO SECUENCIA ({len(self.axis_recorded_sequence)} pasos) ===")
        for i, cmd in enumerate(self.axis_recorded_sequence, 1):
            self._robot_queue_cmd(cmd)
            self._append_adv_robot_log(f"Paso {i}/{len(self.axis_recorded_sequence)}: {cmd}")
        self._append_adv_robot_log("=== SECUENCIA EN COLA ===")
    
    def _clear_axis_sequence(self):
        """Limpia la secuencia grabada."""
        if self.axis_recorded_sequence:
            if messagebox.askyesno("Confirmar", "¿Limpiar la secuencia actual?"):
                self.axis_recorded_sequence = []
                self._update_axis_sequence_display()
                self.btn_axis_execute.config(state="disabled")
                self.btn_axis_save.config(state="disabled")
                self._append_adv_robot_log("=== SECUENCIA LIMPIADA ===")
    
    def _save_axis_sequence(self):
        """Guarda la secuencia en un archivo."""
        if not self.axis_recorded_sequence:
            messagebox.showwarning("Advertencia", "No hay secuencia para guardar")
            return
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".seq",
            filetypes=[("Sequence Files", "*.seq"), ("Text Files", "*.txt"), ("All Files", "*.*")],
        )
        if filepath:
            try:
                with open(filepath, "w") as f:
                    for cmd in self.axis_recorded_sequence:
                        f.write(cmd + "\n")
                messagebox.showinfo("Éxito", f"Secuencia guardada en {filepath}")
                self._append_adv_robot_log(f"Secuencia guardada: {filepath}")
            except Exception as e:
                messagebox.showerror("Error", f"Error al guardar: {e}")
    
    def _update_axis_sequence_display(self):
        """Actualiza la visualización de la secuencia."""
        self.text_axis_sequence.config(state="normal")
        self.text_axis_sequence.delete("1.0", tk.END)
        for i, cmd in enumerate(self.axis_recorded_sequence, 1):
            self.text_axis_sequence.insert(tk.END, f"{i}. {cmd}\n")
        self.text_axis_sequence.config(state="disabled")
        self.lbl_axis_seq_count.config(text=f"Comandos: {len(self.axis_recorded_sequence)}")
    
    def _append_adv_robot_log(self, msg):
        """Agrega mensaje al log de robot avanzado."""
        self.adv_robot_log.insert("1.0", f"{msg}\n")

    # ---------------------- Helpers ----------------------
    def _serial_write(self, ser, data: str):
        if ser and getattr(ser,'is_open',False):
            try:
                ser.write((data + '\r\n\r\n').encode())
            except Exception as e:
                self._append_cinta_log(f'Error al escribir serial: {e}')
        else:
            # simulation: just log
            self._append_cinta_log(f'(SIM) Enviado: {data}')

    def _serial_poll_loop(self):
        # Called periodically from Tk mainloop — place to read serials and update UI
        # For demo, randomly toggle station 1 every few seconds? Keep minimal.
        # Real implementation: read from self.ser_cinta and call _set_cinta_station accordingly
        self.root.after(500, self._serial_poll_loop)

    # ---------------------- Tracking (prototype) ----------------------
    def _build_tracking_panel(self, parent):
        frame = ttk.LabelFrame(parent, text='Tracking de Pallets - Movimiento por Estaciones', padding=8)
        frame.pack(fill=tk.BOTH, expand=True)

        # Treeview for PASS events only (pallet movement by station)
        cols = ('id','pallet','station','time')
        self.track_tree = ttk.Treeview(frame, columns=cols, show='headings', height=12)
        for c in cols:
            self.track_tree.heading(c, text=c)
            self.track_tree.column(c, width=120, anchor='center')
        self.track_tree.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Controls: filter, clear, and follow pallet
        ctrl1 = ttk.Frame(frame)
        ctrl1.pack(fill=tk.X, pady=(4,2))

        ttk.Label(ctrl1, text='Filtrar por Estación:').pack(side=tk.LEFT, padx=(4,2))
        self.filter_station_combo = ttk.Combobox(ctrl1, values=[1,2,3,'Todos'], state='readonly', width=8)
        self.filter_station_combo.set('Todos')
        self.filter_station_combo.pack(side=tk.LEFT, padx=(0,6))

        ttk.Button(ctrl1, text='Filtrar', command=self._filter_tracking_by_station).pack(side=tk.LEFT, padx=4)
        ttk.Button(ctrl1, text='Mostrar Todo', command=self._update_tracking_view).pack(side=tk.LEFT, padx=4)
        ttk.Button(ctrl1, text='Limpiar', command=self._clear_history).pack(side=tk.LEFT, padx=4)

        # Follow pallet row
        ctrl2 = ttk.Frame(frame)
        ctrl2.pack(fill=tk.X, pady=(0,4))
        ttk.Label(ctrl2, text='Seguir Pallet (ID):').pack(side=tk.LEFT, padx=(4,2))
        self.entry_follow_pallet = ttk.Entry(ctrl2, width=12)
        self.entry_follow_pallet.pack(side=tk.LEFT, padx=(0,4))
        ttk.Button(ctrl2, text='Activar Seguimiento', command=self._toggle_follow_pallet).pack(side=tk.LEFT, padx=4)
        self.follow_status_label = ttk.Label(ctrl2, text='Status: -')
        self.follow_status_label.pack(side=tk.LEFT, padx=12)

    def _record_command(self, typ, station, pallet):
        """Registra un comando enviado en el historial (deliver/free), solo en logs, no en tracking visual."""
        self._history_counter += 1
        hid = self._history_counter
        t = time.time()
        entry = {'id': hid, 'type': typ, 'station': station, 'pallet': pallet,
                 'status': 'sent', 't_sent': t, 't_confirmed': None, 'duration': None}
        # append to list and map for O(1) lookup
        self.deliver_history.append(entry)
        self.deliver_history_map[hid] = entry
        # if deliver, update pallet->hid and station->hid maps
        if typ == 'deliver' and pallet is not None:
            try:
                self.deliver_by_pallet[int(pallet)] = hid
            except Exception:
                pass
            try:
                self.deliver_last_sent_by_station[int(station)] = hid
            except Exception:
                pass
        # Log only (not in treeview - that's for pass events only)
        self._append_cinta_log(f'CMD: {typ} {pallet}→{station} (id={hid})')
        return hid

    def _record_pass_event(self, station, pallet_id):
        """Registra un evento PASS (pallet detectado en estación) en el tracking.
        También actualiza la posición actual del pallet y limpia estaciones anteriores."""
        self.pass_counter += 1
        pid = self.pass_counter
        t = time.time()
        entry = {'id': pid, 'pallet': pallet_id, 'station': station, 'time': t}
        self.pass_history.append(entry)
        self.pass_history_map[pid] = entry
        # Actualizar posición actual del pallet (si conocemos el id)
        if pallet_id is not None:
            try:
                self.pallet_current_position[int(pallet_id)] = {'station': station, 'time': t}
            except Exception:
                pass

        # Limpiar el pallet de estaciones anteriores (solo si el mismo pallet estaba allí)
        for est in [1, 2, 3]:
            if est == station:
                continue
            # Solo borrar si el pallet que está en 'est' coincide con el pallet que llega
            existing = self.station_pallet_info.get(est, {}).get('pallet')
            try:
                if pallet_id is not None and existing is not None and int(existing) == int(pallet_id):
                    self._set_cinta_station(est, False)
            except Exception:
                # si hay algun problema comparando, no borrar por seguridad
                pass

        # Mostrar el pallet en la estación actual (solo mostrar número si está en lista válida)
        valid_display = None
        try:
            p_int = int(pallet_id) if pallet_id is not None else None
            allowed = [1, 2, 3, 5, 6]
            if p_int in allowed:
                valid_display = p_int
            else:
                # Fallback: intentar usar último dígito (caso de códigos largos)
                try:
                    last = int(str(p_int)[-1])
                    if last in allowed:
                        valid_display = last
                except Exception:
                    pass
        except Exception:
            valid_display = None

        self._set_cinta_station(station, True, pallet_id=valid_display)
        
        # insert into treeview (ONLY pass events here)
        try:
            t_str = time.strftime('%H:%M:%S', time.localtime(t))
            self.track_tree.insert('', 'end', iid=str(pid), values=(pid, pallet_id, station, t_str))
        except Exception:
            pass
        # log to cinta
        self._append_cinta_log(f'PASS: Pallet {pallet_id} detectado en estación {station}')
        # If following this pallet, update label
        try:
            if self.follow_active and self.follow_pallet_id is not None and int(pallet_id) == int(self.follow_pallet_id):
                self._update_follow_label(pallet_id, station, 'pass')
        except Exception:
            pass
        return pid

    def _confirm_command(self, hid):
        """Marca un comando como confirmado y actualiza la vista y estadísticas."""
        e = self.deliver_history_map.get(hid)
        if not e:
            return
        e['status'] = 'confirmed'
        e['t_confirmed'] = time.time()
        try:
            e['duration'] = e['t_confirmed'] - e['t_sent'] if e['t_sent'] else None
        except Exception:
            e['duration'] = None
        # update treeview row
        try:
            t_sent = time.strftime('%H:%M:%S', time.localtime(e['t_sent'])) if e['t_sent'] else ''
            t_conf = time.strftime('%H:%M:%S', time.localtime(e['t_confirmed'])) if e['t_confirmed'] else ''
            dur = f"{e['duration']:.2f}" if e['duration'] is not None else ''
            self.track_tree.item(str(hid), values=(hid, e['type'], e['station'], e['pallet'], e['status'], t_sent, t_conf, dur))
        except Exception:
            pass
        # remove pallet/station quick mappings that pointed to this hid
        try:
            # remove pallet mapping(s)
            for p, v in list(self.deliver_by_pallet.items()):
                if v == hid:
                    self.deliver_by_pallet.pop(p, None)
            # remove station mapping(s)
            for s, v in list(self.deliver_last_sent_by_station.items()):
                if v == hid:
                    self.deliver_last_sent_by_station.pop(s, None)
        except Exception:
            pass
        # Update follow label if we're following this pallet
        try:
            if self.follow_active and self.follow_pallet_id is not None and e.get('pallet') is not None:
                if int(e.get('pallet')) == int(self.follow_pallet_id):
                    self._update_follow_label(e.get('pallet'), e.get('station'), 'confirmed')
        except Exception:
            pass
        self._append_cinta_log(f'[{time.strftime("%H:%M:%S")}] TRACK: {e["type"]} {e["id"]} confirmed, dur={e.get("duration")}s')
        self._compute_stats()
        return

    def _toggle_follow_pallet(self):
        """Start/stop following the pallet id entered in the follow entry. Muestra posición ACTUAL."""
        val = (self.entry_follow_pallet.get() or '').strip()
        if not val:
            # stop following if no val
            self.follow_active = False
            self.follow_pallet_id = None
            try:
                self.follow_status_label.config(text='Status: -')
            except Exception:
                pass
            self._append_cinta_log('Seguimiento detenido (sin ID)')
            return
        
        # toggle: if same id and active -> stop, otherwise start following
        try:
            val_int = int(val)
            if self.follow_active and self.follow_pallet_id is not None and self.follow_pallet_id == val_int:
                # Deactivate
                self.follow_active = False
                self.follow_pallet_id = None
                self.follow_status_label.config(text='Status: -')
                self._append_cinta_log(f'Seguimiento detenido para pallet {val}')
            else:
                # Activate
                self.follow_active = True
                self.follow_pallet_id = val_int
                self.follow_status_label.config(text=f'Siguiendo: P{val}')
                self._append_cinta_log(f'Seguimiento iniciado para pallet {val}')
                
                # Mostrar posición ACTUAL del pallet
                curr_pos = self.pallet_current_position.get(val_int)
                if curr_pos:
                    st = curr_pos.get('station')
                    self._update_follow_label(val_int, st, 'now')
                    self._append_cinta_log(f'  Pallet {val} está AHORA en estación {st}')
                else:
                    self._append_cinta_log(f'  Pallet {val} no se ha detectado aún en el sistema')
        except ValueError:
            self._append_cinta_log(f'Error: "{val}" no es un ID válido (debe ser un número)')

    def _update_follow_label(self, pallet, station, evt_type):
        """Update label showing current station/state for followed pallet."""
        try:
            txt = f'P{pallet}: @E{station}' if station is not None else f'P{pallet}'
            self.follow_status_label.config(text=txt)
        except Exception:
            pass

    def _update_tracking_view(self):
        try:
            # Clear and repopulate with pass events only
            for i in self.track_tree.get_children():
                self.track_tree.delete(i)
            for e in self.pass_history:
                t_str = time.strftime('%H:%M:%S', time.localtime(e.get('time'))) if e.get('time') else ''
                self.track_tree.insert('', 'end', iid=str(e['id']), values=(e['id'], e['pallet'], e['station'], t_str))
        except Exception:
            pass

    def _filter_tracking_by_station(self):
        """Muestra en el treeview solo los eventos PASS cuyo campo station coincide con la estación seleccionada."""
        try:
            val = self.filter_station_combo.get()
            if not val or val == 'Todos':
                self._update_tracking_view()
                return
            station = int(val)
        except Exception:
            return
        try:
            for i in self.track_tree.get_children():
                self.track_tree.delete(i)
            for e in self.pass_history:
                try:
                    if int(e.get('station') or -1) != station:
                        continue
                except Exception:
                    continue
                t_str = time.strftime('%H:%M:%S', time.localtime(e.get('time'))) if e.get('time') else ''
                self.track_tree.insert('', 'end', iid=str(e['id']), values=(e['id'], e['pallet'], e['station'], t_str))
        except Exception:
            pass

    def _compute_stats(self):
        # Compute average confirmation time per station and overall
        sums = {}
        counts = {}
        for e in self.deliver_history:
            if e.get('duration') is not None:
                s = e['station']
                sums[s] = sums.get(s, 0.0) + e['duration']
                counts[s] = counts.get(s, 0) + 1
        parts = []
        total_sum = 0.0; total_count = 0
        for s in sorted(sums.keys()):
            avg = sums[s] / counts[s] if counts[s] else 0.0
            parts.append(f'E{s} avg {avg:.2f}s')
            total_sum += sums[s]; total_count += counts[s]
        if total_count:
            parts.insert(0, f'Overall avg {total_sum/total_count:.2f}s')
        txt = ' | '.join(parts) if parts else 'Stats: no confirmed entries yet'
        try:
            self.track_stats_label.config(text=txt)
        except Exception:
            pass

    def _clear_history(self):
        self.deliver_history.clear()
        self.deliver_history_map.clear()
        self.deliver_by_pallet.clear()
        self.deliver_last_sent_by_station.clear()
        self.pass_history.clear()
        self.pass_history_map.clear()
        self.pallet_current_position.clear()
        self.pass_counter = 0
        self._history_counter = 0
        try:
            for i in self.track_tree.get_children():
                self.track_tree.delete(i)
        except Exception:
            pass
        # Limpiar todas las estaciones
        for est in [1, 2, 3]:
            self._set_cinta_station(est, False)
        self._append_cinta_log('Historial limpiado')

    # ---------------------- Start/stop robot/layer convenience ----------------------
    def run(self):
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self.root.mainloop()

    def _on_close(self):
        # Cleanly stop threads/serial (defensivo para evitar excepciones al cerrar)
        try:
            self.cam_running = False
            self.cinta_reading = False

            if hasattr(self, 'ser_cinta') and self.ser_cinta and getattr(self.ser_cinta, 'is_open', False):
                self.ser_cinta.close()
            if hasattr(self, 'ser_robot') and self.ser_robot and getattr(self.ser_robot, 'is_open', False):
                self.ser_robot.close()
            if hasattr(self, 'ser_laser') and self.ser_laser and getattr(self.ser_laser, 'is_open', False):
                self.ser_laser.close()

            try:
                self._stop_server()
            except Exception:
                pass
            try:
                self._disconnect_client()
            except Exception:
                pass
        finally:
            try:
                self.root.quit()
                self.root.destroy()
            except Exception:
                pass

if __name__ == '__main__':
    root = tk.Tk()
    app = IntegratedApp(root)
    app.run()
