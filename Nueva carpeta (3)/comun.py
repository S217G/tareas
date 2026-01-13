import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.filedialog import asksaveasfilename
import serial
import time
import serial.tools.list_ports

# Crear objeto Serial
SerialPort1 = serial.Serial()

# Variables para grabación de secuencias
sequence_recording = False
recorded_sequence = []
current_sequence_name = ""

# Variable global para el widget de incremento
spin_increment = None

# ==== FUNCIONES ACTUALIZADAS ====
def send_scorbot_command(command, description=""):
    """Función mejorada para enviar comandos al Scorbot-ER V Plus"""
    if SerialPort1.is_open:
        try:
            # Asegurar formato correcto del comando
            cmd = command.upper().strip() + '\r'  # Comandos en mayúsculas y con retorno de carro
            
            # Limpiar buffer de entrada
            SerialPort1.reset_input_buffer()
            
            # Enviar comando
            SerialPort1.write(cmd.encode())
            
            # Esperar respuesta (ajustar tiempo según necesidad)
            time.sleep(0.5)
            
            # Leer respuesta
            response = SerialPort1.read_all().decode('ascii', errors='ignore').strip()
            
            # Mostrar en la interfaz
            TextRecibidos.insert("1.0", f"> {cmd.strip()}\n")
            TextRecibidos.insert("2.0", f"< {response}\n")
            if description:
                TextRecibidos.insert("3.0", f"{description}\n")
            TextRecibidos.insert("4.0", "-"*50 + "\n")
            
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Error al enviar comando: {str(e)}")
            return False
    else:
        messagebox.showerror("Error", "Debe conectar el puerto primero")
        return False

def click_pcplc():
    send_scorbot_command("RUN PCPLC", "Ejecutar programa PCPLC")

def click_a():
    send_scorbot_command("ABORT", "Movimiento abortado")

def click_ttsib():
    send_scorbot_command("RUN TTSIB", "Ejecutar programa TTSIB")

def click_coff():
    send_scorbot_command("COFF", "Apagar servomotores")

def click_move():
    send_scorbot_command("MOVE 0", "Mover a posición 0")

def click_open():
    send_scorbot_command("OPEN", "Abrir gripper")

def click_close():
    send_scorbot_command("CLOSE", "Cerrar gripper")

def click_left():
    send_scorbot_command("MJ 1 -10", "Base movida 10° a la izquierda (antihorario)")

def click_right():
    send_scorbot_command("MJ 1 10", "Base movida 10° a la derecha (horario)")

def click_home():
    send_scorbot_command("HOME", "Mover a posición HOME")

def click_ready():
    send_scorbot_command("READY", "Preparar robot para movimiento")

def click_speed():
    send_scorbot_command("SPEED 50", "Velocidad establecida al 50%")

def mover_eje(eje, direccion):
    """Mueve un eje específico del robot en la dirección indicada."""
    global spin_increment
    
    # Mapeo de ejes a números de joint
    ejes = {
        "BASE": 1,
        "SHOULDER": 2,
        "ELBOW": 3,
        "WRIST": 4,
        "PITCH": 5
    }
    
    if eje not in ejes:
        messagebox.showerror("Error", f"Eje {eje} no válido")
        return
    
    # Verificar que el puerto esté conectado
    if not SerialPort1.is_open:
        messagebox.showerror("Error", "Debe conectar el robot primero")
        return
    
    # Obtener el incremento desde el spinbox (si existe) o usar valor por defecto
    try:
        if spin_increment is not None:
            increment = int(spin_increment.get())
        else:
            increment = 10
    except Exception as e:
        print(f"Error obteniendo incremento: {e}")
        increment = 10  # Valor por defecto
    
    # Determinar el signo del movimiento
    if direccion == "+":
        value = increment
    else:
        value = -increment
    
    joint_num = ejes[eje]
    command = f"MJ {joint_num} {value}"
    description = f"{eje} movido {value}°"
    
    print(f"Enviando comando: {command}")  # Debug
    
    # Grabar comando si está en modo grabación
    if sequence_recording:
        recorded_sequence.append(command)
        update_sequence_display()
    
    send_scorbot_command(command, description)

def abrir_pinza():
    """Abre la pinza del robot."""
    if sequence_recording:
        recorded_sequence.append("OPEN")
        update_sequence_display()
    click_open()

def cerrar_pinza():
    """Cierra la pinza del robot."""
    if sequence_recording:
        recorded_sequence.append("CLOSE")
        update_sequence_display()
    click_close()

def start_recording():
    """Inicia la grabación de una secuencia."""
    global sequence_recording, recorded_sequence
    sequence_recording = True
    recorded_sequence = []
    btn_start_rec.config(state="disabled")
    btn_stop_rec.config(state="normal")
    btn_execute_seq.config(state="disabled")
    lbl_recording_status.config(text="● GRABANDO", fg="red")
    update_sequence_display()
    TextRecibidos.insert("1.0", "=== GRABACIÓN INICIADA ===\n")

def stop_recording():
    """Detiene la grabación de una secuencia."""
    global sequence_recording
    sequence_recording = False
    btn_start_rec.config(state="normal")
    btn_stop_rec.config(state="disabled")
    if recorded_sequence:
        btn_execute_seq.config(state="normal")
        btn_save_seq.config(state="normal")
    lbl_recording_status.config(text="○ Detenido", fg="black")
    TextRecibidos.insert("1.0", f"=== GRABACIÓN DETENIDA ({len(recorded_sequence)} comandos) ===\n")

def execute_sequence():
    """Ejecuta la secuencia grabada."""
    if not recorded_sequence:
        messagebox.showwarning("Advertencia", "No hay secuencia grabada")
        return
    
    TextRecibidos.insert("1.0", "=== EJECUTANDO SECUENCIA ===\n")
    for i, cmd in enumerate(recorded_sequence, 1):
        TextRecibidos.insert("1.0", f"Paso {i}/{len(recorded_sequence)}: {cmd}\n")
        send_scorbot_command(cmd, f"Paso {i}")
        time.sleep(0.5)  # Pausa entre comandos
    TextRecibidos.insert("1.0", "=== SECUENCIA COMPLETADA ===\n")

def clear_sequence():
    """Limpia la secuencia grabada."""
    global recorded_sequence
    if messagebox.askyesno("Confirmar", "¿Limpiar la secuencia actual?"):
        recorded_sequence = []
        update_sequence_display()
        btn_execute_seq.config(state="disabled")
        btn_save_seq.config(state="disabled")
        TextRecibidos.insert("1.0", "=== SECUENCIA LIMPIADA ===\n")

def update_sequence_display():
    """Actualiza la visualización de la secuencia."""
    text_sequence.config(state="normal")
    text_sequence.delete("1.0", tk.END)
    for i, cmd in enumerate(recorded_sequence, 1):
        text_sequence.insert(tk.END, f"{i}. {cmd}\n")
    text_sequence.config(state="disabled")
    lbl_seq_count.config(text=f"Comandos: {len(recorded_sequence)}")

def save_sequence():
    """Guarda la secuencia actual en un archivo."""
    if not recorded_sequence:
        messagebox.showwarning("Advertencia", "No hay secuencia para guardar")
        return
    
    filepath = asksaveasfilename(
        defaultextension=".seq",
        filetypes=[("Sequence Files", "*.seq"), ("Text Files", "*.txt"), ("All Files", "*.*")],
    )
    if filepath:
        with open(filepath, "w") as f:
            for cmd in recorded_sequence:
                f.write(cmd + "\n")
        messagebox.showinfo("Guardado", f"Secuencia guardada en {filepath}")

def click_conectar():
    if not SerialPort1.is_open:
        SerialPort1.baudrate = 9600
        SerialPort1.bytesize = 8
        SerialPort1.parity = "N"
        SerialPort1.stopbits = serial.STOPBITS_ONE
        SerialPort1.timeout = 1  # Timeout de lectura
        SerialPort1.port = comboBox1.get()
        try:
            SerialPort1.open()
            TextoEstado.config(state="normal")
            TextoEstado.delete("1.0", tk.END)
            TextoEstado.insert("1.0", "CONECTADO")
            TextoEstado.configure(background="lime")
            
            # Configuración inicial recomendada para Scorbot-ER V Plus
            send_scorbot_command("JOINT", "Modo joint activado")
            send_scorbot_command("READY", "Robot listo para comandos")
            send_scorbot_command("SPEED 30", "Velocidad inicial al 30%")
            
            messagebox.showinfo("Conectado", "Conexión establecida con Scorbot-ER V Plus")
            TextoEstado.config(state="disabled")
        except Exception as e:
            messagebox.showerror("Error de conexión", f"No se pudo conectar: {str(e)}")
    else:
        messagebox.showinfo("Información", "El puerto ya está conectado.")

def click_desconectar():
    if SerialPort1.is_open:
        try:
            send_scorbot_command("COFF", "Apagando servomotores antes de desconectar")
            SerialPort1.close()
            TextoEstado.config(state="normal")
            TextoEstado.delete("1.0", tk.END)
            TextoEstado.insert("1.0", "DESCONECTADO")
            TextoEstado.configure(background="red")
            messagebox.showinfo("Desconectado", "Puerto serial desconectado")
            TextoEstado.config(state="disabled")
        except Exception as e:
            messagebox.showerror("Error", f"Error al desconectar: {str(e)}")
    else:
        messagebox.showinfo("Información", "El puerto ya está desconectado")

def click_enviar():
    custom_cmd = TextEnviar.get("1.0", tk.END).strip()
    if custom_cmd:
        send_scorbot_command(custom_cmd, "Comando personalizado enviado")
    else:
        messagebox.showwarning("Advertencia", "Escriba un comando primero")

def click_guardar():
    filepath = asksaveasfilename(
        defaultextension=".txt",
        filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
    )
    if not filepath:
        return
    with open(filepath, "w") as output_file:
        text = TextRecibidos.get("1.0", tk.END)
        output_file.write(text)

def update_com_ports():
    ports = [port.device for port in serial.tools.list_ports.comports()]
    comboBox1['values'] = ports
    if ports:
        comboBox1.set(ports[0])
    else:
        comboBox1.set("No ports found")

# ==== INTERFAZ GRÁFICA ====
root = tk.Tk()
root.title("Controlador Scorbot-ER V Plus - Control Avanzado")
root.geometry("1100x700")
root.resizable(True, True)

# Configuración de estilo
style = ttk.Style()
style.configure('TButton', font=('Arial', 9), padding=5)
style.configure('TLabel', font=('Arial', 9))

# Panel de estado
frame_estado = ttk.Frame(root, padding=10)
frame_estado.pack(fill=tk.X)

TextoEstado = tk.Text(frame_estado, height=1, width=15, state="disabled", 
                     bg="red", font=("Arial", 10, "bold"))
TextoEstado.insert("1.0", "DESCONECTADO")
TextoEstado.pack(side=tk.LEFT, padx=5)

ttk.Button(frame_estado, text="Conectar", command=click_conectar).pack(side=tk.LEFT, padx=5)
ttk.Button(frame_estado, text="Desconectar", command=click_desconectar).pack(side=tk.LEFT, padx=5)

comboBox1 = ttk.Combobox(frame_estado, state="readonly", width=25)
comboBox1.pack(side=tk.LEFT, padx=5)
update_com_ports()

# Panel de control principal
main_frame = ttk.Frame(root, padding=10)
main_frame.pack(fill=tk.BOTH, expand=True)

# Panel de comandos rápidos
cmd_frame = ttk.LabelFrame(main_frame, text="Comandos Rápidos", padding=10)
cmd_frame.grid(row=0, column=0, padx=5, pady=5, sticky=tk.N)

buttons = [
    ("Home", click_home),
    ("Ready", click_ready),
    ("Run PCPLC", click_pcplc),
    ("Run TTSIB", click_ttsib),
    ("Abortar", click_a),
    ("Apagar (COFF)", click_coff),
    ("Mover a 0", click_move),
    ("Velocidad 50%", click_speed)
]

for text, cmd in buttons:
    ttk.Button(cmd_frame, text=text, command=cmd).pack(fill=tk.X, pady=2)

# ===== PANEL DE MOVIMIENTOS POR EJES =====
frame_movimientos = ttk.LabelFrame(main_frame, text="Movimientos por Ejes", padding=10)
frame_movimientos.grid(row=1, column=0, padx=5, pady=5, sticky=tk.NSEW)

# Control de incremento
ttk.Label(frame_movimientos, text="Incremento (grados):").grid(row=0, column=0, columnspan=2, pady=5)
spin_increment = tk.Spinbox(frame_movimientos, from_=1, to=90, width=10, font=('Arial', 10))
spin_increment.delete(0, tk.END)
spin_increment.insert(0, "10")
spin_increment.grid(row=0, column=2, pady=5)

# Hacer el widget accesible globalmente
globals()['spin_increment'] = spin_increment

# Ejes
ttk.Button(frame_movimientos, text="Base +", command=lambda: mover_eje("BASE", "+")).grid(row=1, column=0, padx=5, pady=5, sticky=tk.EW)
ttk.Button(frame_movimientos, text="Base -", command=lambda: mover_eje("BASE", "-")).grid(row=1, column=1, padx=5, pady=5, sticky=tk.EW)

ttk.Button(frame_movimientos, text="Hombro +", command=lambda: mover_eje("SHOULDER", "+")).grid(row=2, column=0, padx=5, pady=5, sticky=tk.EW)
ttk.Button(frame_movimientos, text="Hombro -", command=lambda: mover_eje("SHOULDER", "-")).grid(row=2, column=1, padx=5, pady=5, sticky=tk.EW)

ttk.Button(frame_movimientos, text="Codo +", command=lambda: mover_eje("ELBOW", "+")).grid(row=3, column=0, padx=5, pady=5, sticky=tk.EW)
ttk.Button(frame_movimientos, text="Codo -", command=lambda: mover_eje("ELBOW", "-")).grid(row=3, column=1, padx=5, pady=5, sticky=tk.EW)

ttk.Button(frame_movimientos, text="Muñeca +", command=lambda: mover_eje("WRIST", "+")).grid(row=4, column=0, padx=5, pady=5, sticky=tk.EW)
ttk.Button(frame_movimientos, text="Muñeca -", command=lambda: mover_eje("WRIST", "-")).grid(row=4, column=1, padx=5, pady=5, sticky=tk.EW)

ttk.Button(frame_movimientos, text="Pitch +", command=lambda: mover_eje("PITCH", "+")).grid(row=5, column=0, padx=5, pady=5, sticky=tk.EW)
ttk.Button(frame_movimientos, text="Pitch -", command=lambda: mover_eje("PITCH", "-")).grid(row=5, column=1, padx=5, pady=5, sticky=tk.EW)

# Pinza
ttk.Button(frame_movimientos, text="Abrir Pinza", command=abrir_pinza).grid(row=6, column=0, padx=5, pady=5, sticky=tk.EW)
ttk.Button(frame_movimientos, text="Cerrar Pinza", command=cerrar_pinza).grid(row=6, column=1, padx=5, pady=5, sticky=tk.EW)

# Configurar pesos de columnas
frame_movimientos.columnconfigure(0, weight=1)
frame_movimientos.columnconfigure(1, weight=1)

# Panel de comunicación
comm_frame = ttk.LabelFrame(main_frame, text="Comunicación", padding=10)
comm_frame.grid(row=0, column=1, padx=5, pady=5, sticky=tk.NSEW)

# Área de envío
ttk.Label(comm_frame, text="Comando personalizado:").pack(anchor=tk.W)
TextEnviar = tk.Text(comm_frame, height=3, width=30, font=('Consolas', 10))
TextEnviar.pack(fill=tk.X, pady=5)

ttk.Button(comm_frame, text="Enviar Comando", command=click_enviar).pack(fill=tk.X, pady=5)

# Área de recepción
ttk.Label(comm_frame, text="Respuesta del robot:").pack(anchor=tk.W)
TextRecibidos = tk.Text(comm_frame, height=15, width=50, font=('Consolas', 9))
TextRecibidos.pack(fill=tk.BOTH, expand=True)

# Botón Guardar
ttk.Button(comm_frame, text="Guardar Log", command=click_guardar).pack(fill=tk.X, pady=5)

# ===== PANEL DE SECUENCIAS =====
seq_frame = ttk.LabelFrame(main_frame, text="Grabación de Secuencias", padding=10)
seq_frame.grid(row=0, column=2, rowspan=2, padx=5, pady=5, sticky=tk.NSEW)

# Estado de grabación
lbl_recording_status = ttk.Label(seq_frame, text="○ Detenido", font=('Arial', 10, 'bold'))
lbl_recording_status.pack(pady=5)

# Botones de control
control_frame = ttk.Frame(seq_frame)
control_frame.pack(fill=tk.X, pady=5)

btn_start_rec = ttk.Button(control_frame, text="● Iniciar Grabación", command=start_recording)
btn_start_rec.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

btn_stop_rec = ttk.Button(control_frame, text="■ Detener", command=stop_recording, state="disabled")
btn_stop_rec.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

# Contador de comandos
lbl_seq_count = ttk.Label(seq_frame, text="Comandos: 0", font=('Arial', 9))
lbl_seq_count.pack(pady=5)

# Visualización de secuencia
ttk.Label(seq_frame, text="Secuencia Grabada:").pack(anchor=tk.W)
text_sequence = tk.Text(seq_frame, height=12, width=35, font=('Consolas', 9), state="disabled")
text_sequence.pack(fill=tk.BOTH, expand=True, pady=5)

# Botones de acción
action_frame = ttk.Frame(seq_frame)
action_frame.pack(fill=tk.X, pady=5)

btn_execute_seq = ttk.Button(action_frame, text="▶ Ejecutar", command=execute_sequence, state="disabled")
btn_execute_seq.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

btn_clear_seq = ttk.Button(action_frame, text="✖ Limpiar", command=clear_sequence)
btn_clear_seq.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

btn_save_seq = ttk.Button(action_frame, text="💾 Guardar", command=save_sequence, state="disabled")
btn_save_seq.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

# Instrucciones
instr_text = """Instrucciones:
1. Click 'Iniciar Grabación'
2. Use los controles de ejes
3. Click 'Detener' cuando termine
4. Click 'Ejecutar' para repetir
"""
ttk.Label(seq_frame, text=instr_text, font=('Arial', 8), justify=tk.LEFT).pack(anchor=tk.W, pady=5)

# Configurar pesos de columnas y filas para expansión
main_frame.columnconfigure(0, weight=0)
main_frame.columnconfigure(1, weight=1)
main_frame.columnconfigure(2, weight=0)
main_frame.rowconfigure(0, weight=1)

root.mainloop()