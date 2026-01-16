import tkinter as tk  # hace import de tkinter para GUI
from tkinter import ttk, messagebox  # hace import de widgets ttk y messagebox
import serial  # hace import de pyserial para comunicación por COM
import time  # hace import para pausas y timeouts

# Aplicación simple y fácil para controlar una cinta transportadora por serial
# - Conectar/desconectar puerto COM
# - Enviar comandos Deliver / Free para estación y pallet (control)
# - Enviar comandos crudos para pruebas
# - Opcionalmente enviar Deliver y esperar confirmación del PLC

# --- Configuración (cambiar si es necesario) ---
BAUDRATE = 9600  # hace configurar la velocidad de baudios
BYTESIZE = serial.SEVENBITS  # hace configurar tamaño de byte
PARITY = serial.PARITY_EVEN  # hace configurar paridad
STOPBITS = serial.STOPBITS_TWO  # hace configurar bits de parada
READ_INTERVAL_MS = 200  # hace intervalo de lectura en ms


ser = None  # hace referencia al objeto serial.Serial
is_serial_open = False  # hace un "flag" para saber si el puerto está abierto

# --- Funciones auxiliares ---
def append_log(text):
    """ hace añadir una línea al área de logs de la GUI """
    texto_recibidos.config(state="normal")
    texto_recibidos.insert(tk.END, text + "\n")
    texto_recibidos.see(tk.END)
    texto_recibidos.config(state="disabled")

# --- Control de puerto serial ---
def connect_serial():
    """ hace abrir el puerto serial seleccionado desde el combobox """
    global ser, is_serial_open
    if is_serial_open:
        return
    port = combo_puertos.get()  # hace leer el puerto seleccionado
    try:
        ser = serial.Serial(port)  # hace crear la conexión serial
        ser.baudrate = BAUDRATE
        ser.bytesize = BYTESIZE
        ser.parity = PARITY
        ser.stopbits = STOPBITS
        ser.timeout = 0.2  # hace timeout en lecturas
        is_serial_open = True
        texto_estado_serial.config(state="normal")
        texto_estado_serial.delete(1.0, tk.END)
        texto_estado_serial.insert(1.0, "Conectado")
        texto_estado_serial.config(background="lightgreen")
        texto_estado_serial.config(state="disabled")
        append_log(f"Serial conectado en {port}")
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo abrir {port}: {e}")
        ser = None
        is_serial_open = False


def disconnect_serial():
    """ hace cerrar el puerto serial si está abierto """
    global ser, is_serial_open
    if not is_serial_open or ser is None:
        return
    try:
        ser.close()  # hace cerrar la conexión serial
    except Exception:
        pass
    ser = None
    is_serial_open = False
    texto_estado_serial.config(state="normal")
    texto_estado_serial.delete(1.0, tk.END)
    texto_estado_serial.insert(1.0, "Desconectado")
    texto_estado_serial.config(background="red")
    texto_estado_serial.config(state="disabled")
    append_log("Serial desconectado")


def read_serial_loop():
    """ hace leer periódicamente lo que llega por serial y lo muestra en el log """
    global ser
    if is_serial_open and ser is not None:
        try:
            n = ser.in_waiting  # hace comprobar cuantos bytes hay esperando
            if n and n > 0:
                data = ser.read(n)  # hace leer los bytes disponibles
                try:
                    texto = data.decode('utf-8', errors='ignore')  # hace decodificar a texto
                except Exception:
                    texto = repr(data)  # hace fallback a repr si no es texto
                append_log("<-- " + texto.strip())
        except Exception as e:
            append_log(f"Error leyendo serial: {e}")
    ventana.after(READ_INTERVAL_MS, read_serial_loop)  # hace reprogramar la función

# --- Envío de comandos ---
def send_raw_command():
    """ hace enviar el texto exacto puesto en 'Comando crudo' por serial """
    cmd = entrada_comando_raw.get().strip()  # hace leer el campo de entrada cruda
    if not cmd:
        messagebox.showinfo("Info", "Ingrese un comando en el campo 'Comando crudo'.")
        return
    if not is_serial_open or ser is None:
        messagebox.showerror("Error", "Puerto serial no conectado")
        return
    try:
        append_log("--> " + cmd)  # hace registrar el envío
        ser.write((cmd + "\r\n\r\n").encode())  # hace enviar con terminadores CR/LF
        append_log("Comando crudo enviado")
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo enviar: {e}")


def send_deliver(estacion, pallet):
    """ hace enviar el comando Deliver según estación y pallet (if/elif simple) """
    if not is_serial_open or ser is None:
        messagebox.showerror("Error", "Puerto serial no conectado")
        return
    # hace seleccionar el comando correcto según estación/pallet
    if estacion == 1 and pallet == 1:
        cmd = "@00WD000900015B*"
    elif estacion == 1 and pallet == 2:
        cmd = "@00WD0010000153*"
    elif estacion == 1 and pallet == 3:
        cmd = "@00WD0011000152*"
    elif estacion == 1 and pallet == 5:
        cmd = "@00WD0013000150*"
    elif estacion == 1 and pallet == 6:
        cmd = "@00WD0014000157*"
    elif estacion == 2 and pallet == 1:
        cmd = "@00WD0009000258*"
    elif estacion == 2 and pallet == 2:
        cmd = "@00WD0010000250*"
    elif estacion == 2 and pallet == 3:
        cmd = "@00WD0011000251*"
    elif estacion == 2 and pallet == 5:
        cmd = "@00WD0013000253*"
    elif estacion == 2 and pallet == 6:
        cmd = "@00WD0014000254*"
    elif estacion == 3 and pallet == 1:
        cmd = "@00WD0009000359*"
    elif estacion == 3 and pallet == 2:
        cmd = "@00WD0010000351*"
    elif estacion == 3 and pallet == 3:
        cmd = "@00WD0011000350*"
    elif estacion == 3 and pallet == 5:
        cmd = "@00WD0013000352*"
    elif estacion == 3 and pallet == 6:
        cmd = "@00WD0014000355*"
    elif estacion == 5 and pallet == 1:
        cmd = "@00WD000900055F*"
    elif estacion == 5 and pallet == 2:
        cmd = "@00WD0010000557*"
    elif estacion == 5 and pallet == 3:
        cmd = "@00WD0011000556*"
    elif estacion == 5 and pallet == 5:
        cmd = "@00WD0013000554*"
    elif estacion == 5 and pallet == 6:
        cmd = "@00WD0014000553*"
    elif estacion == 6 and pallet == 1:
        cmd = "@00WD000900065C*"
    elif estacion == 6 and pallet == 2:
        cmd = "@00WD0010000654*"
    elif estacion == 6 and pallet == 3:
        cmd = "@00WD0011000655*"
    elif estacion == 6 and pallet == 5:
        cmd = "@00WD0013000657*"
    elif estacion == 6 and pallet == 6:
        cmd = "@00WD0014000650*"
    else:
        messagebox.showwarning("Atención", "Combinación estación/pallet no válida")
        return
    try:
        append_log("--> " + cmd)  # hace registrar el envío
        ser.write((cmd + "\r\n\r\n").encode())  # hace enviar comando al PLC
        append_log(f"Deliver enviado a estación {estacion}, pallet {pallet}")
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo enviar deliver: {e}")


def send_free(estacion, pallet):
    """ hace enviar secuencia Free: liberar estación y confirmar salida pallet """
    if not is_serial_open or ser is None:
        messagebox.showerror("Error", "Puerto serial no conectado")
        return
    # hace determinar comando para liberar la estación
    if estacion == 1:
        cmd1 = "@00WD004800015E*"
    elif estacion == 2:
        cmd1 = "@00WD004900015F*"
    elif estacion == 3:
        cmd1 = "@00WD0050000157*"
    elif estacion == 5:
        cmd1 = "@00WD0052000155*"
    elif estacion == 6:
        cmd1 = "@00WD0053000154*"
    else:
        messagebox.showwarning("Atención", "Estación no válida")
        return
    # hace determinar comando para confirmar salida del pallet
    if pallet == 1:
        cmd2 = "@00WD000900995A*"
    elif pallet == 2:
        cmd2 = "@00WD0010009952*"
    elif pallet == 3:
        cmd2 = "@00WD0011009953*"
    elif pallet == 5:
        cmd2 = "@00WD0013009951*"
    elif pallet == 6:
        cmd2 = "@00WD0014009956*"
    else:
        messagebox.showwarning("Atención", "Pallet no válido")
        return
    try:
        append_log("--> " + cmd1)  # hace registrar y enviar cmd1
        ser.write((cmd1 + "\r\n\r\n").encode())
        time.sleep(0.5)  # hace pequeña pausa
        append_log("--> " + cmd2)  # hace registrar y enviar cmd2
        ser.write((cmd2 + "\r\n\r\n").encode())
        append_log(f"Free enviado a estación {estacion}, pallet {pallet}")
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo enviar free: {e}")

# --- Enviar y esperar confirmación (básico) ---
def send_and_wait(estacion, pallet, confirm_text, timeout_s=10):
    """ hace enviar deliver y esperar hasta encontrar confirm_text en el serial """
    if not is_serial_open or ser is None:
        messagebox.showerror("Error", "Puerto serial no conectado")
        return
    append_log(f"Enviando deliver a estación {estacion}, esperando '{confirm_text}' (timeout {timeout_s}s)")
    send_deliver(estacion, pallet)  # hace enviar el deliver primero
    deadline = time.time() + timeout_s  # hace calcular deadline
    buffer = ""  # hace acumular datos leídos
    while time.time() < deadline:
        try:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                texto = data.decode('utf-8', errors='ignore')
                append_log("<-- " + texto.strip())
                buffer += texto
                if confirm_text in buffer:
                    append_log(f"Confirmación recibida: {confirm_text}")
                    messagebox.showinfo("Info", f"Llegada confirmada en estación {estacion}")
                    return
        except Exception as e:
            append_log(f"Error mientras esperaba confirmación: {e}")
        time.sleep(0.2)  # hace esperar un poco antes de volver a leer
    messagebox.showwarning("Timeout", f"No se recibió '{confirm_text}' antes de {timeout_s} segundos")

# --- Interfaz gráfica ---
ventana = tk.Tk()  # hace crear la ventana principal
ventana.title("Cinta básica - control serial")  # hace establecer título
ventana.geometry("760x420")  # hace establecer tamaño

# --- Frame izquierdo: Puerto Serial y Logs ---
frame_left = ttk.LabelFrame(ventana, text="Puerto Serial y Logs")  # hace frame izquierdo
frame_left.place(x=10, y=10, width=360, height=380)

ttk.Label(frame_left, text="Puerto:").place(x=10, y=10)  # hace etiqueta de puerto
combo_puertos = ttk.Combobox(frame_left, values=["COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7"], state="readonly")  # hace combobox de puertos
combo_puertos.set("COM3")  # hace valor por defecto
combo_puertos.place(x=60, y=10, width=120)

btn_connect = tk.Button(frame_left, text="Conectar", command=connect_serial)  # hace botón conectar
btn_connect.place(x=190, y=8)

btn_disconnect = tk.Button(frame_left, text="Desconectar", command=disconnect_serial)  # hace botón desconectar
btn_disconnect.place(x=260, y=8)

texto_estado_serial = tk.Text(frame_left, height=1, width=18)  # hace cuadro que muestra estado serial
texto_estado_serial.insert(1.0, "Desconectado")
texto_estado_serial.config(state="disabled")
texto_estado_serial.place(x=60, y=40)

texto_recibidos = tk.Text(frame_left, state="disabled", width=42, height=18)  # hace área de logs
texto_recibidos.place(x=10, y=70)

scroll_l = tk.Scrollbar(frame_left, command=texto_recibidos.yview)  # hace scrollbar para logs
scroll_l.place(x=330, y=70, height=290)
texto_recibidos.config(yscrollcommand=scroll_l.set)

# Raw command entry
ttk.Label(frame_left, text="Comando crudo:").place(x=10, y=340)  # hace etiqueta para comando crudo
entrada_comando_raw = tk.Entry(frame_left, width=32)  # hace entrada para comando crudo
entrada_comando_raw.place(x=100, y=340)
btn_send_raw = tk.Button(frame_left, text="Enviar crudo", command=send_raw_command)  # hace botón enviar crudo
btn_send_raw.place(x=100, y=370)

# --- Frame derecho: Control de Estaciones ---
frame_right = ttk.LabelFrame(ventana, text="Control Estaciones")  # hace frame derecho
frame_right.place(x=380, y=10, width=370, height=380)

ttk.Label(frame_right, text="Estación:").place(x=10, y=20)  # hace etiqueta estación
combo_estacion = ttk.Combobox(frame_right, values=[1,2,3,5,6], state="readonly", width=5)  # hace combobox estación
combo_estacion.set(1)
combo_estacion.place(x=80, y=20)

ttk.Label(frame_right, text="Pallet:").place(x=150, y=20)  # hace etiqueta pallet
combo_pallet = ttk.Combobox(frame_right, values=[1,2,3,5,6], state="readonly", width=5)  # hace combobox pallet
combo_pallet.set(1)
combo_pallet.place(x=200, y=20)

btn_deliver = tk.Button(frame_right, text="Deliver", width=12, command=lambda: send_deliver(int(combo_estacion.get()), int(combo_pallet.get())))  # hace botón Deliver
btn_deliver.place(x=10, y=60)

btn_free = tk.Button(frame_right, text="Free", width=12, command=lambda: send_free(int(combo_estacion.get()), int(combo_pallet.get())))  # hace botón Free
btn_free.place(x=140, y=60)

# Send and wait controls
ttk.Label(frame_right, text="Confirmación esperada:").place(x=10, y=120)  # hace etiqueta confirmación
entry_confirm = tk.Entry(frame_right, width=20)  # hace entrada para texto que confirma llegada
entry_confirm.insert(0, "ARRIVED")
entry_confirm.place(x=140, y=120)

ttk.Label(frame_right, text="Timeout (s):").place(x=10, y=150)  # hace etiqueta timeout
entry_timeout = tk.Entry(frame_right, width=5)  # hace entrada para timeout en segundos
entry_timeout.insert(0, "10")
entry_timeout.place(x=140, y=150)

btn_send_wait = tk.Button(frame_right, text="Deliver y esperar", width=20, command=lambda: send_and_wait(int(combo_estacion.get()), int(combo_pallet.get()), entry_confirm.get(), int(entry_timeout.get())))  # hace botón enviar y esperar confirmación
btn_send_wait.place(x=10, y=190)

# Stop / test movement
btn_test_move = tk.Button(frame_right, text="Probar movimiento (1,1)", width=20, command=lambda: send_deliver(1,1))  # hace botón de prueba movimiento
btn_test_move.place(x=10, y=230)

btn_stop = tk.Button(frame_right, text="Enviar STOP crudo", width=20, command=lambda: (entrada_comando_raw.delete(0, tk.END), entrada_comando_raw.insert(0, "STOP*"), send_raw_command()))  # hace botón para enviar STOP crudo
btn_stop.place(x=10, y=270)

# --- Inicia el loop de lectura periódica del serial ---
ventana.after(READ_INTERVAL_MS, read_serial_loop)

# --- Inicia la ventana principal ---
ventana.mainloop()