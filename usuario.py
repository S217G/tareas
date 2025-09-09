# -*- coding: utf-8 -*-
import os, time, socket, threading, tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ===== Serial para el ROBOT (7E1 + XON/XOFF) =====
try:
    import serial
except Exception:
    serial = None

def open_robot_serial(port: str, baud: int):
    if serial is None:
        raise RuntimeError("Falta pyserial. Instala con: pip install pyserial")
    ser = serial.Serial(
        port=port,
        baudrate=baud,
        bytesize=serial.SEVENBITS,     # 7 bits
        parity=serial.PARITY_EVEN,     # paridad par
        stopbits=serial.STOPBITS_ONE,  # 1 stop
        timeout=0.2,
        write_timeout=0.5,
        xonxoff=True,                  # flow control SW
        rtscts=False,
        dsrdtr=False,
    )
    ser.reset_input_buffer(); ser.reset_output_buffer()
    return ser

# ===== Utilidades LÁSER (tus funciones existentes) =====
try:
    from laser_nuevo_parche import (
        open_serial, generate_gcode_text, stream_to_grbl,
        move_to_offset_and_set_origin, move_back_to_machine_origin, send_cmd,
    )
except Exception:
    def open_serial(*a, **k): raise RuntimeError("open_serial() no disponible.")
    def generate_gcode_text(*a, **k): return ""
    def stream_to_grbl(*a, **k): return 0
    def move_to_offset_and_set_origin(*a, **k): pass
    def move_back_to_machine_origin(*a, **k): pass
    def send_cmd(*a, **k): pass

HOST, PORT = "10.4.3.76", 8888
SCORBOT_EOL_DEFAULT = "\r"

PROFILE="photo"; F_TRAVEL=1000; SIZE_MM=(20,20); OFFSET_DX,OFFSET_DY,OFFSET_FEED=270,-170,1000
RUTAS_IMAGENES = {f"Opción {i}": rf"C:\Users\cimla\Pictures\Camera Roll\aruco_{i}.png" for i in range(1,16)}
OPCIONES = list(RUTAS_IMAGENES.keys())

# ===================== Cliente TCP =====================
class ClientGUI:
    def __init__(self, master, laser_panel=None):
        self.master = master
        self.laser_panel = laser_panel
        self.connected = False
        self.socket = None
        self.name = tk.StringVar(value="UsuarioPLC")

        self.received_messages_text = tk.Text(master, state="disabled")
        self.received_messages_text.place(x=10, y=40, width=360, height=260)

        self.message_entry = tk.Entry(master, width=53); self.message_entry.place(x=10, y=305)
        self.name_entry = tk.Entry(master, width=16, textvariable=self.name, state=tk.DISABLED); self.name_entry.place(x=10, y=10)

        self.connect_button = tk.Button(master, text='Conectar', command=self.connect_to_server); self.connect_button.place(x=150, y=8)
        self.disconnect_button = tk.Button(master, text='Desconectar', command=self.disconnect_from_server, state=tk.DISABLED); self.disconnect_button.place(x=230, y=8)
        self.send_button = tk.Button(master, text='Enviar', command=self.send_message, state=tk.DISABLED); self.send_button.place(x=345, y=302)

    def append_message(self, text: str):
        self.received_messages_text.config(state="normal")
        self.received_messages_text.insert(tk.END, text)
        self.received_messages_text.see(tk.END)
        self.received_messages_text.config(state="disabled")

    def connect_to_server(self):
        def attempt():
            while not self.connected:
                try:
                    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.socket.connect((HOST, PORT)); self.connected = True
                    self.socket.sendall((self.name.get() + "\n").encode()); self.socket.settimeout(1.0)
                    threading.Thread(target=self.receive_messages, daemon=True).start()
                    self.send_button.config(state=tk.NORMAL)
                    self.connect_button.config(state=tk.DISABLED, text="Conectado", bg='lightgreen')
                    self.append_message("✅ Conectado al servidor.\n"); break
                except Exception:
                    self.append_message(" Error de conexión. Reintentando en 5 s...\n"); time.sleep(5)
        threading.Thread(target=attempt, daemon=True).start()
        self.disconnect_button.config(state=tk.NORMAL)

    def disconnect_from_server(self):
        if self.connected:
            try:
                self.connected = False; self.socket.shutdown(socket.SHUT_RDWR); self.socket.close()
                self.append_message(" Desconectado del servidor.\n")
            except Exception:
                self.append_message(" Error al desconectar.\n")
        self.send_button.config(state=tk.DISABLED)
        self.connect_button.config(state=tk.NORMAL, text="Conectar", bg='SystemButtonFace')
        self.disconnect_button.config(state=tk.DISABLED)

    def send_message(self):
        if not self.connected:
            messagebox.showerror("Error", "No hay conexión con el servidor."); return
        try:
            self.socket.sendall((self.message_entry.get() + "\n").encode())
        except Exception as e:
            messagebox.showerror('Error', f"No se pudo enviar: {e}")

    def receive_messages(self):
        buffer = ""
        while self.connected:
            try:
                data = self.socket.recv(1024)
                if not data:
                    self.append_message(" Conexión cerrada por el servidor.\n"); break
                buffer += data.decode(errors="ignore"); buffer = buffer.replace("\r\n","\n").replace("\r","\n")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n",1); line=line.strip()
                    if line:
                        self.append_message("📨 server: " + line + "\n")
                        self._try_handle_server_line(line)
            except socket.timeout:
                if buffer:
                    partial = buffer.strip()
                    if partial:
                        self.append_fmessage("📨 server: " + partial + "\n")
                        self._try_handle_server_line(partial)
                    buffer = ""
                continue
            except Exception:
                self.connected = False
                if self.socket: self.socket.close()
                self.append_message(" Error al recibir. Conexión cerrada.\n"); break

    def _try_handle_server_line(self, line: str):
        # Acepta: 'Laser,1,Imprimir' | 'Laser,Imprimir,1' | 'Laser,PosicionarLaser'
        txt = line.strip()
        if txt.lower().startswith("server:"):
            txt = txt.split(":",1)[1].strip()

        parts = [p.strip() for p in txt.split(",") if p.strip()]
        if not parts or parts[0].lower()!="laser": return

        tokens = [parts[0]] + ["".join(ch for ch in p.lower() if ch not in (" ","_")) for p in parts[1:]]
        accion=None; numero=None
        for p in tokens[1:]:
            if p.isdigit(): numero=int(p)
            elif p in ("imprimir","imprime","print"): accion="imprimir"
            elif p in ("posicionarlaser","poslaser","posicionar"): accion="posicionarlaser"

        if accion=="imprimir" and numero is not None and self.laser_panel:
            self.master.after(0, self.laser_panel.print_option, numero)
            self.append_message(f" Orden LÁSER: imprimir opción {numero}\n")
        elif accion=="PosicionarLaser" and self.laser_panel:
            self.master.after(0, self.laser_panel.robot_run_pos1)
            self.append_message(" Orden ROBOT: run POS1\n")
        else:
            self.append_message("ℹ️ Comando LÁSER/ROBOT no reconocido o faltan datos.\n")

# ===================== Panel Serial =====================
class SerialPanel(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bd=2, relief="groove")

        # --- ROBOT ---
        self.ser_robot=None
        self.robot_port=tk.StringVar(value="COM4")
        self.robot_baud=tk.StringVar(value="9600")
        self.robot_eol =tk.StringVar(value={"\r":"CR","\n":"LF","\r\n":"CRLF"}[SCORBOT_EOL_DEFAULT])
        self.robot_upper=tk.BooleanVar(value=False)     # RUN POS1 en mayúsculas
        self.robot_semic=tk.BooleanVar(value=False)    # ';' OFF

        robot=tk.LabelFrame(self, text="🤖 ROBOT (Scorbot)")
        robot.place(x=10, y=10, width=420, height=280)

        tk.Label(robot, text="Puerto").place(x=8,y=8)
        ttk.Combobox(robot, state="readonly", values=[f"COM{i}" for i in range(1,33)],
                     textvariable=self.robot_port, width=8).place(x=60,y=6)
        tk.Label(robot, text="Baud").place(x=140,y=8)
        ttk.Combobox(robot, state="readonly", values=["9600","19200","38400","57600","115200"],
                     textvariable=self.robot_baud, width=8).place(x=175,y=6)
        tk.Button(robot, text="Conectar", width=10, command=self.robot_connect).place(x=260,y=4)
        tk.Button(robot, text="Desconectar", width=12, command=self.robot_disconnect).place(x=335,y=4)

        self.robot_log=tk.Text(robot, font=("Arial",9), state="disabled"); self.robot_log.place(x=8,y=32,width=380,height=160)
        tk.Scrollbar(robot, command=self.robot_log.yview).place(x=388,y=32,height=160)

        tk.Label(robot, text="EOL").place(x=8,y=200)
        ttk.Combobox(robot, state="readonly", values=["CR","LF","CRLF"],
                     textvariable=self.robot_eol, width=6).place(x=40,y=198)
        tk.Checkbutton(robot, text="Final ';'", variable=self.robot_semic).place(x=220,y=198)

        self.robot_cmd=tk.StringVar()
        tk.Entry(robot, textvariable=self.robot_cmd, width=36).place(x=8,y=225)
        tk.Button(robot, text="Enviar", width=10, command=self.robot_send_free).place(x=310,y=223)

        # --- LÁSER ---
        self.ser_laser=None
        self.laser_port=tk.StringVar(value="COM1")
        self.laser_baud=tk.StringVar(value="115200")
        self.selected_option=tk.StringVar(value="Elegir opción…")
        self._last_image_path=None

        laser=tk.LabelFrame(self, text="🔦 LÁSER (opcional)")
        laser.place(x=10, y=340, width=420, height=230)

        tk.Label(laser, text="Puerto").place(x=8,y=8)
        ttk.Combobox(laser, state="readonly", values=[f"COM{i}" for i in range(1,33)],
                     textvariable=self.laser_port, width=8).place(x=60,y=6)
        tk.Label(laser, text="Baud").place(x=140,y=8)
        ttk.Combobox(laser, state="readonly", values=["9600","19200","38400","57600","115200"],
                     textvariable=self.laser_baud, width=8).place(x=175,y=6)
        tk.Button(laser, text="Conectar", width=10, command=self.laser_connect).place(x=260,y=4)
        tk.Button(laser, text="Desconectar", width=12, command=self.laser_disconnect).place(x=335,y=4)

        self.laser_log=tk.Text(laser, font=("Arial",9), state="disabled"); self.laser_log.place(x=8,y=32,width=380,height=120)
        tk.Scrollbar(laser, command=self.laser_log.yview).place(x=388,y=32,height=120)

        self.menu_btn=tk.Menubutton(laser, textvariable=self.selected_option, relief="raised")
        self.menu_btn.place(x=8,y=160,width=220,height=26)
        self.menu=tk.Menu(self.menu_btn, tearoff=0); self.menu_btn["menu"]=self.menu
        for nombre in OPCIONES: self.menu.add_command(label=nombre, command=lambda n=nombre: self.on_select(n))
        self.menu.add_separator(); self.menu.add_command(label="Elegir archivo…", command=self.pick_file)
        tk.Button(laser, text="Imprimir", command=self.on_print).place(x=340,y=160,width=50,height=26)

        self.config(width=440, height=580)

    # -------- Utils de log --------
    def rlog(self, s):
        self.robot_log.config(state="normal"); self.robot_log.insert(tk.END, s+"\n"); self.robot_log.see(tk.END); self.robot_log.config(state="disabled")
    def llog(self, s):
        self.laser_log.config(state="normal"); self.laser_log.insert(tk.END, s+"\n"); self.laser_log.see(tk.END); self.laser_log.config(state="disabled")

    # -------- ROBOT --------
    def robot_connect(self):
        try:
            if self.ser_robot and getattr(self.ser_robot,"is_open",False):
                self.rlog("Ya conectado."); return
            port=self.robot_port.get(); baud=int(self.robot_baud.get())
            self.ser_robot=open_robot_serial(port, baud)
            self.rlog(f"✅ Conectado ROBOT {port} @ {baud} (7E1, XON/XOFF)")
        except Exception as e:
            messagebox.showerror("ROBOT", f"No se pudo abrir {self.robot_port.get()}\n{e}")

    def robot_disconnect(self):
        try:
            if self.ser_robot and getattr(self.ser_robot,"is_open",False):
                self.ser_robot.close(); self.rlog("🔌 ROBOT desconectado.")
        except Exception as e:
            messagebox.showerror("ROBOT", str(e))

    def _robot_eol(self)->str:
        v=self.robot_eol.get().upper()
        return "\r\n" if v=="CRLF" else ("\r" if v=="CR" else "\n")

    def _robot_format(self, raw:str)->str:
        cmd=raw.strip()
        if self.robot_upper.get(): cmd=cmd.upper()
        if self.robot_semic.get() and not cmd.endswith(";"): cmd+=";"
        return cmd

    def robot_send(self, raw:str):
        try:
            if not (self.ser_robot and getattr(self.ser_robot,"is_open",False)):
                self.robot_connect()
            eol=self._robot_eol(); cmd=self._robot_format(raw)
            payload=(cmd+eol).encode("ascii", errors="ignore")
            self.ser_robot.write(payload); self.ser_robot.flush()   # << asegura envío
            hexs=" ".join(f"{b:02X}" for b in payload)
            self.rlog(f"[ROBOT >>] {cmd}  (hex: {hexs})")
            time.sleep(0.1)
            try:
                n=self.ser_robot.in_waiting if hasattr(self.ser_robot,"in_waiting") else 0
                if n:
                    resp=self.ser_robot.read(n).decode(errors="ignore").strip()
                    if resp: self.rlog(f"[<< ROBOT] {resp}")
            except Exception: pass
        except Exception as e:
            messagebox.showerror("ROBOT", f"No se pudo enviar '{raw}': {e}")

    def robot_send_free(self):
        cmd=(self.robot_cmd.get() or "").strip()
        if cmd: self.robot_send(cmd)

    # --- llamado directo desde el servidor ---
    def robot_run_pos1(self):
        self.rlog("[SERVER] Ejecutar run POS1")
        self.robot_send("run POS1")  # << envía directo al puerto (sin depender de la caja)

    # -------- LÁSER --------
    def laser_connect(self):
        try:
            if self.ser_laser and getattr(self.ser_laser,"is_open",False):
                self.llog("Ya conectado."); return
            port=self.laser_port.get(); baud=int(self.laser_baud.get())
            self.ser_laser=open_serial(port, baud)
            self.llog(f"✅ Conectado LÁSER {port} @ {baud}")
        except Exception as e:
            messagebox.showerror("LÁSER", f"No se pudo abrir {self.laser_port.get()}\n{e}")

    def laser_disconnect(self):
        try:
            if self.ser_laser and getattr(self.ser_laser,"is_open",False):
                try: send_cmd(self.ser_laser,"M5")
                except Exception: pass
                self.ser_laser.close(); self.llog("🔌 LÁSER desconectado.")
        except Exception as e:
            messagebox.showerror("LÁSER", str(e))

    def print_option(self, n:int):
        nombre=f"Opción {n}"; path=RUTAS_IMAGENES.get(nombre)
        if not path: self.llog(f"[SERVER] Opción {n} no existe."); return
        self.selected_option.set(nombre); self._last_image_path=path
        self.llog(f"[SERVER] Imprimir {nombre}"); self.on_print()

    def on_select(self, nombre):
        self.selected_option.set(nombre); self._last_image_path=RUTAS_IMAGENES.get(nombre)

    def pick_file(self):
        path=filedialog.askopenfilename(title="Selecciona imagen",
            filetypes=[("Imágenes","*.png;*.jpg;*.jpeg;*.bmp"), ("Todos los archivos","*.*")])
        if path: self._last_image_path=path; self.selected_option.set(os.path.basename(path))

    def on_print(self):
        if not self._last_image_path:
            messagebox.showwarning("Falta selección","Elige una imagen antes de imprimir."); return
        self.laser_connect()
        self.llog("[GCODE] Generando…")
        gcode=generate_gcode_text(image_path=self._last_image_path, size_mm=SIZE_MM, ppmm=5,
                                  mode="grayscale", invert=False, gamma_val=0.6, origin_xy=(0.0,0.0),
                                  f_engrave=1000, f_travel=F_TRAVEL, s_max=600)
        self.llog("[POSICIÓN] Moviendo a offset…"); move_to_offset_and_set_origin(self.ser_laser, dx=OFFSET_DX, dy=OFFSET_DY, feed=OFFSET_FEED)
        self.llog("[ENVÍO] Enviando trabajo…"); stream_to_grbl(self.ser_laser, gcode)
        self.llog("Regresando a origen…"); move_back_to_machine_origin(self.ser_laser)
        self.llog("✅ Grabado finalizado.")

# ===================== Main =====================
def main():
    root=tk.Tk(); root.geometry("1050x620"); root.resizable(0,0); root.title("Comunicacion Serial")
    frame_cliente=tk.LabelFrame(root, text="🌐 Cliente"); frame_cliente.place(x=10,y=10,width=390,height=340)
    frame_serial =tk.LabelFrame(root, text="🔌 Conexiones Serie"); frame_serial.place(x=410,y=10,width=470,height=600)

    panel=SerialPanel(frame_serial); panel.pack(fill="both", expand=True, padx=8, pady=8)
    ClientGUI(frame_cliente, laser_panel=panel)
    root.mainloop()

if __name__=="__main__":
    main()
