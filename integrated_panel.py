

import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import os

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

        self.ser_cinta = None
        self.ser_robot = None
        self.ser_laser = None

        self.is_serial_available = serial is not None

        self.station_states = {1: False, 2: False, 3: False}

        self.cam_thread = None
        self.cam_running = False

        self.laser_positions = {}
        self.robot_positions = {}
        self.aruco_generated_path = None

        # Flag y control para lectura continua de cinta
        self.cinta_read_thread = None
        self.cinta_reading = False

        self._build_ui()
        # Inicia loop de lectura de la cinta
        self.root.after(CINTA_READ_INTERVAL_MS, self._read_cinta_loop)
        self.root.after(200, self._serial_poll_loop)

    def _build_ui(self):
        # Use paned window to layout panels
        paned = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(paned, width=360)
        right_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        paned.add(right_frame, weight=3)

        # LEFT: cinta + robot quick
        self._build_cinta_panel(left_frame)
        self._build_robot_panel(left_frame)

        # RIGHT: laser + aruco + camera
        self._build_laser_panel(right_frame)
        self._build_aruco_panel(right_frame)
        self._build_camera_panel(right_frame)

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

        # Station canvas
        self.canvas_cinta = tk.Canvas(frame, height=160, bg="#f0f0f0")
        self.canvas_cinta.pack(fill=tk.X, padx=4, pady=4)

        # Draw track and station ovals
        self._draw_cinta_layout()

        # Controls row
        controls = ttk.Frame(frame)
        controls.pack(fill=tk.X, pady=(6,0))

        # Port selector and connect controls for cinta
        ttk.Label(controls, text='Puerto:').pack(side=tk.LEFT, padx=(0,4))
        self.combo_cinta_ports = ttk.Combobox(controls, values=self._list_serial_ports(), state='readonly', width=18)
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

    def _draw_cinta_layout(self):
        c = self.canvas_cinta
        c.delete('all')
        positions = {1:80, 2:180, 3:280}
        y = 50
        # track
        c.create_line(30, y, 330, y, width=6, fill='black')
        self.cinta_ovals = {}
        for est, x in positions.items():
            c.create_rectangle(x-40, y-40, x+40, y+40, fill='#ddd', outline='#999')
            oval = c.create_oval(x-20, y-20, x+20, y+20, fill='red')
            c.create_text(x, y+58, text=f"Est {est}")
            self.cinta_ovals[est] = oval

    def _set_cinta_station(self, station, ok:bool):
        color = 'green' if ok else 'red'
        oval = self.cinta_ovals.get(station)
        if oval:
            self.canvas_cinta.itemconfig(oval, fill=color)
        self.station_states[station] = ok

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

    def _send_deliver(self, estacion, pallet):
        cmd = DELIVER_COMMANDS.get((estacion,pallet))
        if not cmd:
            self._append_cinta_log('Comando no encontrado')
            return
        if not self.ser_cinta or not getattr(self.ser_cinta, 'is_open', False):
            self._append_cinta_log('(SIM) Deliver no conectado: ' + cmd)
            return
        try:
            # Registrar la estación para detectarla en la respuesta
            self._last_deliver_station = estacion
            self._append_cinta_log(f'--> {cmd}')
            self.ser_cinta.write((cmd + '\r\n\r\n').encode())
            self._append_cinta_log(f'Deliver enviado a estación {estacion}, pallet {pallet}')
        except Exception as e:
            self._append_cinta_log(f'Error enviando deliver: {e}')

    def _send_free(self, estacion, pallet):
        # Sequence Free: liberar estación y confirmar salida pallet
        cmd_est = {1: "@00WD004800015E*",2:"@00WD004900015F*",3:"@00WD0050000157*"}.get(estacion)
        cmd_pal = {1: "@00WD000900995A*",2:"@00WD0010009952*",3:"@00WD0011009953*",5:"@00WD0013009951*",6:"@00WD0014009956*"}.get(pallet)
        if not cmd_est or not cmd_pal:
            self._append_cinta_log('Comando Free inválido')
            return
        if not self.ser_cinta or not getattr(self.ser_cinta, 'is_open', False):
            self._append_cinta_log(f'(SIM) Free no conectado: {cmd_est} + {cmd_pal}')
            return
        try:
            # Registrar la estación para detectarla en la respuesta
            self._last_free_station = estacion
            self._append_cinta_log(f'--> {cmd_est}')
            self.ser_cinta.write((cmd_est + '\r\n\r\n').encode())
            time.sleep(0.5)
            self._append_cinta_log(f'--> {cmd_pal}')
            self.ser_cinta.write((cmd_pal + '\r\n\r\n').encode())
            self._append_cinta_log(f'Free enviado a estación {estacion}, pallet {pallet}')
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
        try:
            ports = self._list_serial_ports()
            self.combo_cinta_ports['values'] = ports
            if ports:
                # keep selected if still available, otherwise pick first
                cur = self.combo_cinta_ports.get()
                if not cur or cur not in ports:
                    self.combo_cinta_ports.set(ports[0])
            else:
                self.combo_cinta_ports.set('')
            self._append_cinta_log('Lista de puertos actualizada')
        except Exception as e:
            self._append_cinta_log(f'Error actualizando puertos: {e}')

    def _connect_cinta(self):
        if serial is None:
            messagebox.showinfo('Cinta','pyserial no instalado - modo simulación')
            return
        ports = self._list_serial_ports()
        if not ports:
            messagebox.showwarning('Cinta','No se encontraron puertos')
            return
        port = self.combo_cinta_ports.get() or ports[0]
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
            
            self._append_cinta_log(f'Cinta conectada en {port} (9600 7E2)')
            try:
                self.label_cinta_status.config(text=f'Estado: Conectada ({port})')
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror('Cinta', f'No se pudo conectar: {e}')
            self.ser_cinta = None

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
        Detecta si la respuesta del PLC indica que un pallet llegó (verde) o salió (rojo).
        Patrones esperados:
        - Respuesta de comando Deliver (pallet llegó a estación): verde
        - Respuesta de comando Free (pallet salió de estación): rojo
        """
        response = response_text.strip().lower()
        
        # Respuestas típicas del PLC (adaptarse según el sistema real)
        # Si recibe OK o confirmación después de un comando Deliver → pallet en estación (verde)
        if 'ok' in response or 'ok' in response:
            # Cambiar última estación envida a verde
            for est in [1, 2, 3]:
                if hasattr(self, '_last_deliver_station') and self._last_deliver_station == est:
                    self._set_cinta_station(est, True)
                    self._append_cinta_log(f'✓ Pallet detectado en estación {est}')
                    break
        
        # Si recibe respuesta a comando Free → pallet salió (rojo)
        if 'free' in response or 'liberar' in response.lower():
            for est in [1, 2, 3]:
                if hasattr(self, '_last_free_station') and self._last_free_station == est:
                    self._set_cinta_station(est, False)
                    self._append_cinta_log(f'✗ Pallet liberado de estación {est}')
                    break

    # ---------------------- Robot panel ----------------------
    def _build_robot_panel(self, parent):
        frame = ttk.LabelFrame(parent, text='Control Robot', padding=8)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        btns = ttk.Frame(frame)
        btns.pack(fill=tk.X, pady=4)
        ttk.Button(btns, text='Conectar Robot', command=self._connect_robot).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text='Desconectar', command=self._disconnect_robot).pack(side=tk.LEFT, padx=6)

        grid = ttk.Frame(frame)
        grid.pack(pady=6)
        actions = [
            ('HOME', self._robot_cmd_home), ('READY', self._robot_cmd_ready),
            ('COFF', self._robot_cmd_coff), ('OPEN', self._robot_cmd_open), ('CLOSE', self._robot_cmd_close)
        ]
        for i,(t,cmd) in enumerate(actions):
            ttk.Button(grid, text=t, command=cmd).grid(row=0, column=i, padx=4, pady=4)

        self.robot_log = tk.Text(frame, height=8, state=tk.DISABLED)
        self.robot_log.pack(fill=tk.BOTH, pady=6)

        # Robot positions: save arbitrary command text per named position
        pos_frame = ttk.Frame(frame)
        pos_frame.pack(fill=tk.X, pady=(6,4))
        ttk.Label(pos_frame, text='Comando/Posición:').pack(side=tk.LEFT)
        self.entry_robot_cmd = ttk.Entry(pos_frame, width=28)
        self.entry_robot_cmd.pack(side=tk.LEFT, padx=(6,8))
        ttk.Label(pos_frame, text='Nombre:').pack(side=tk.LEFT)
        self.entry_robot_pos_name = ttk.Entry(pos_frame, width=12)
        self.entry_robot_pos_name.pack(side=tk.LEFT, padx=(6,8))
        ttk.Button(pos_frame, text='Guardar Posición', command=self._save_robot_position).pack(side=tk.LEFT, padx=6)

        pos_select = ttk.Frame(frame)
        pos_select.pack(fill=tk.X)
        ttk.Label(pos_select, text='Posiciones:').pack(side=tk.LEFT)
        self.combo_robot_positions = ttk.Combobox(pos_select, values=list(self.robot_positions.keys()), state='readonly', width=30)
        self.combo_robot_positions.pack(side=tk.LEFT, padx=(6,8))
        ttk.Button(pos_select, text='Ir a Posición', command=self._goto_robot_position).pack(side=tk.LEFT, padx=6)

    def _connect_robot(self):
        if serial is None:
            messagebox.showinfo('Robot','pyserial no instalado - modo simulación')
            return
        # Try open first available port
        ports = self._list_serial_ports()
        if not ports:
            messagebox.showwarning('Robot','No se encontraron puertos')
            return
        try:
            self.ser_robot = serial.Serial(ports[0], baudrate=9600, timeout=1)
            self._append_robot_log(f'Robot conectado en {ports[0]}')
        except Exception as e:
            messagebox.showerror('Robot', f'No se pudo conectar: {e}')

    def _disconnect_robot(self):
        try:
            if self.ser_robot and self.ser_robot.is_open:
                self.ser_robot.close()
            self._append_robot_log('Robot desconectado')
        except Exception:
            pass

    def _robot_cmd(self, cmd, desc=''):
        if not self.ser_robot or not getattr(self.ser_robot,'is_open',False):
            self._append_robot_log('Robot no conectado (simulación)')
            return
        try:
            s = (cmd.strip()+ '\r').encode()
            self.ser_robot.write(s)
            time.sleep(0.5)
            resp = self.ser_robot.read_all().decode(errors='ignore').strip()
            self._append_robot_log(f'> {cmd} | < {resp}')
        except Exception as e:
            self._append_robot_log(f'Error: {e}')

    def _robot_cmd_home(self): self._robot_cmd('HOME')
    def _robot_cmd_ready(self): self._robot_cmd('READY')
    def _robot_cmd_coff(self): self._robot_cmd('COFF')
    def _robot_cmd_open(self): self._robot_cmd('OPEN')
    def _robot_cmd_close(self): self._robot_cmd('CLOSE')

    def _append_robot_log(self, msg):
        ts = time.strftime('%H:%M:%S')
        self.robot_log.configure(state='normal')
        self.robot_log.insert('end', f"[{ts}] {msg}\n")
        self.robot_log.see('end')
        self.robot_log.configure(state='disabled')

    def _save_robot_position(self):
        name = (self.entry_robot_pos_name.get() or '').strip()
        cmd = (self.entry_robot_cmd.get() or '').strip()
        if not name:
            messagebox.showwarning('Robot', 'Ingresa un nombre para la posición')
            return
        if not cmd:
            messagebox.showwarning('Robot', 'Ingresa el comando o la posición')
            return
        self.robot_positions[name] = cmd
        vals = list(self.robot_positions.keys())
        self.combo_robot_positions['values'] = vals
        self.combo_robot_positions.set(name)
        self._append_robot_log(f'Posición robot guardada: {name} -> {cmd}')

    def _goto_robot_position(self):
        name = (self.combo_robot_positions.get() or '').strip()
        if not name or name not in self.robot_positions:
            messagebox.showwarning('Robot', 'Selecciona una posición válida')
            return
        cmd = self.robot_positions[name]
        # Enviar comando al robot usando _robot_cmd para logging/lectura
        try:
            self._robot_cmd(cmd)
            self._append_robot_log(f'Enviado comando posición {name}: {cmd}')
        except Exception as e:
            self._append_robot_log(f'Error enviando posición: {e}')

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
    def _build_camera_panel(self, parent):
        frame = ttk.LabelFrame(parent, text='Cámara / Detección', padding=8)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        top = ttk.Frame(frame); top.pack(fill=tk.X)
        ttk.Button(top, text='Iniciar Cámara', command=self._start_camera).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text='Detener Cámara', command=self._stop_camera).pack(side=tk.LEFT, padx=6)

        self.cam_label = ttk.Label(frame, text='Cam preview')
        self.cam_label.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    def _camera_loop(self):
        # Lightweight camera simulation / placeholder — if OpenCV available, could show real frames
        try:
            import cv2
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                self._append_laser_log('No se pudo abrir cámara (0)')
                return
            while self.cam_running:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.05); continue
                # Resize and convert to PIL for Tk (bigger preview)
                frame = cv2.resize(frame, (800,450))
                cv2.cvtColor(frame, cv2.COLOR_BGR2RGB, frame)
                img = Image.fromarray(frame)
                imgtk = ImageTk.PhotoImage(img)
                # update on main thread
                self.root.after(0, lambda i=imgtk: self.cam_label.config(image=i) or setattr(self, 'last_cam_img', i))
                time.sleep(0.04)
            cap.release()
        except Exception as e:
            # fallback simulation: cycle colored boxes
            cols = ['#333','#444','#555','#666']
            idx = 0
            while self.cam_running:
                col = cols[idx % len(cols)]; idx += 1
                self.root.after(0, lambda c=col: self.cam_label.config(background=c, text=''))
                time.sleep(0.3)

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

    # ---------------------- Start/stop robot/layer convenience ----------------------
    def run(self):
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self.root.mainloop()

    def _on_close(self):
        # Cleanly stop threads/serial
        self.cam_running = False
        self.cinta_reading = False
        try:
            if self.ser_cinta and getattr(self.ser_cinta, 'is_open', False): 
                self.ser_cinta.close()
        except Exception: pass
        try:
            if self.ser_robot and getattr(self.ser_robot, 'is_open', False): 
                self.ser_robot.close()
        except Exception: pass
        try:
            if self.ser_laser and getattr(self.ser_laser, 'is_open', False): 
                self.ser_laser.close()
        except Exception: pass
        self.root.quit()
        self.root.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    app = IntegratedApp(root)
    app.run()
