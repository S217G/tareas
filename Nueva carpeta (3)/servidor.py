import socket #permite crear el servidor TCP/IP que escucha conexiones de clientes.
import threading #se usa para manejar las conexiones en paralelo, sin congelar la interfaz.
import tkinter as tk #Sirve para crear la interfaz gráfica.
from tkinter import ttk, messagebox #widgets de Tkinter para crear combobox, cuadros de mensaje, etc.

#Variables globales
HOST='0.0.0.0' #El servidor escucha en todas las interfaces de red.
PORT=8888  #Puerto de conexión.
MAX_CONNECTIONS= 2  #Número máximo de clientes permitidos
global Server_Socket #será el objeto socket.
global connections  #lista donde se guardan los clientes conectados.    
server_running = False #bandera para controlar si el servidor está activo o no.

#FUNCIONES DE CONTROL DE SERVIDOR
def iniciar_Servidor():
    Servidor_Thread=threading.Thread(target=correr_Servidor)
    Servidor_Thread.start()

    Start_Button.config(state=tk.DISABLED)
    Stop_Button.config(state=tk.NORMAL)
    mensaje_Text.config(state=tk.NORMAL)
    BDeliver.config(state=tk.NORMAL)
    BFree.config(state=tk.NORMAL)
    Bimprimir.config(state=tk.NORMAL)
    Balmacenar.config(state=tk.NORMAL)
    Bretirar.config(state=tk.NORMAL)
    BPosicionar.config(state=tk.NORMAL)
    Bretirar_laser.config(state=tk.NORMAL)

    EstadoLabel.config(text='Servidor corriendo',bg="lightgreen")
#Lanza el servidor en un hilo aparte (correr_Servidor), para que la interfaz no se bloquee.

def detener_Servidor():
    global server_running

    server_running = False  # detiene el bucle del servidor

    for conn in connections:
        try:
            conn.close()
        except:
            pass

    try:
        Server_Socket.close()
    except:
        pass

    Start_Button.config(state=tk.NORMAL)
    Stop_Button.config(state=tk.DISABLED)
    BDeliver.config(state=tk.DISABLED)
    BFree.config(state=tk.DISABLED)
    mensaje_Text.config(state=tk.DISABLED)
    Bimprimir.config(state=tk.DISABLED)
    Balmacenar.config(state=tk.DISABLED)
    Bretirar.config(state=tk.DISABLED)
    BPosicionar.config(state=tk.DISABLED)
    Bretirar_laser.config(state=tk.DISABLED)
    EstadoLabel.config(text='Servidor Detenido',bg="red")
    log("Servidor detenido y sockets cerrados.")
    #Marca server_running = False, lo que detiene el bucle principal.
    #Cierra todas las conexiones de clientes y el socket del servidor.
    #Cambia la interfaz a estado "detenido".


def log(mensaje):
    Log_Text.insert(tk.END, mensaje + '\n')
    Log_Text.see(tk.END)
    #Muestra mensajes en el área de texto de la interfaz (log del servidor).

#MANEJO DE CLIENTES

def Manejar_conexion(conn, addr, name):
    log(f'{name} conectado por {addr}')

    while True: 
        #Recibimos los datos del cliente
        data = conn.recv(1024)
        mensaje = data.decode().strip()

        if not mensaje:
            #Cliente termina de enviar el mensaje
            break

        log(f'Datos recibidos de {name}: {mensaje}')

        #Procesamos el mensaje del cliente
        respuesta = f'Recibido: {mensaje}'.encode()

     #Enviamos la respuesta al cliente
        conn.sendall(respuesta)

    # cerrar la conexion
    conn.close()
    if conn in connections:   
        connections.remove(conn)
    log(f'Conexión cerrada con {name}')
#Se ejecuta en un hilo separado para cada cliente.
#Recibe mensajes (recv) y los devuelve al cliente como eco (sendall).
#Si el cliente se desconecta, cierra el socket y lo elimina de connections.

#HILO PRINCIPAL DEL SERVIDOR

def correr_Servidor():
    global Server_Socket, connections, server_running
    Server_Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    Server_Socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        Server_Socket.bind((HOST, PORT))
        Server_Socket.listen(MAX_CONNECTIONS)
        log(f'Servidor corriendo en el puerto {PORT}')
    except OSError as e:
        log(f'Error al iniciar el servidor: {e}')
        return

    connections = []
    names = []
    server_running = True

    while server_running:
        try:
            Server_Socket.settimeout(1.0)  # para salir del accept cada 1 segundo
            conn, addr = Server_Socket.accept()
        except socket.timeout:
            continue
        except OSError:
            break  # el socket ya está cerrado

        connections.append(conn)

        try:
            data = conn.recv(1024)
            name = data.decode().strip()
        except:
            name = "Desconocido"

        names.append(name)

        t = threading.Thread(target=Manejar_conexion, args=(conn, addr, name))
        t.start()
#Crea el socket servidor.
#Hace bind y listen.
#Entra en un bucle donde acepta conexiones (accept).
#Cada cliente se maneja en un nuevo hilo (Manejar_conexion).

#FUNCIONES PARA ENVIAR MENSAJES 

def enviar_Mensaje(event=None):
    mensaje = mensaje_Text.get(1.0, tk.END).strip()
    mensaje_Text.delete(1.0,tk.END)
    if mensaje:
        log(f'Mensaje enviado a los clientes: {mensaje}')
    for conn in connections[:]:   # copiamos la lista para modificarla dentro
        try:
            conn.sendall(mensaje.encode())
        except:
            log("Error al enviar mensaje a un cliente. Eliminando conexión.")
            connections.remove(conn)
            conn.close()

    if event is not None:
        return "break"

def on_closing():
    try:
        detener_Servidor()
    except:
        pass
    ventana.destroy()
#Envía a todos los clientes lo que el usuario escribe en la caja de texto de la GUI.


def enviar_comando(tipo, valores):
    mensaje = f"{tipo}," + ",".join(str(v) for v in valores)
    log(f'Mensaje a clientes: {mensaje}')
    for conn in connections[:]:   # copiamos la lista para modificarla dentro
        try:
            conn.sendall(mensaje.encode())
        except:
            log("Error al enviar mensaje a un cliente. Eliminando conexión.")
            connections.remove(conn)
            conn.close()
#Igual que la anterior, pero usado por los botones de comando (PLC, Laser, etc.), construyendo mensajes específicos.
#(PLC,Laser y almacen corresponden a otras interfaces de tipo cliente desarrolladas por otros practicantes)
# ⚠️ Nota:
# Actualmente existe un comportamiento inesperado: 
# si un cliente se conecta, luego se desconecta y más tarde vuelve a conectarse, 
# puede aparecer el mensaje "Error al enviar mensaje a un cliente. Eliminando conexión",
# incluso aunque el cliente reciba correctamente los mensajes.
# 💡 Desafío: encuentra la causa y propón la solución a este problema, joven padawan.

#INTERFAZ GRAFICA

#Ventana
ventana = tk.Tk()
ventana.title("Servidor")
ventana.geometry("600x600")
ventana.resizable(False, False)

#Frames
Frame_chatservidor = tk.LabelFrame(ventana,text="Chat servidor",font=("Arial", 10, "bold"))
Frame_chatservidor.place(x=5, y=5, width=415, height=300)
Frame_chatservidor.lower()

Frame_PLC=tk.LabelFrame(ventana,text="PLC",font=("Arial", 10, "bold"))
Frame_PLC.place(x=5, y=310, width=190, height=100)

Frame_almacen=tk.LabelFrame(ventana,text="Almacen",font=("Arial", 10, "bold"))
Frame_almacen.place(x=200, y=310, width=220, height=100)

Frame_laser=tk.LabelFrame(ventana,text="Laser",font=("Arial", 10, "bold"))
Frame_laser.place(x=5, y=415, width=210, height=100)



#Label
EstadoLabel = tk.Label(Frame_chatservidor, text='Servidor detenido',bd=1,relief="solid")
EstadoLabel.place(x=50,y=210)

PalletText = tk.Label(Frame_PLC, text="Pallet")
PalletText.place(x= 10,y= 10)

EstacionText = tk.Label(Frame_PLC, text="Estación")
EstacionText.place(x= 10,y= 40)

ArucoLabel=tk.Label(Frame_laser, text="Nº ArUco")
ArucoLabel.place(x=10,y=10)

ArucoLabel_almacen=tk.Label(Frame_almacen, text="Nº ArUco")
ArucoLabel_almacen.place(x=10,y=10)

posicion_almacen=tk.Label(Frame_almacen,text="Posición")
posicion_almacen.place(x= 10,y= 40)

#Text
Log_Text = tk.Text(Frame_chatservidor)
Log_Text.place(x=5, y=10, width=398, height=190)

mensaje_Text = tk.Text(Frame_chatservidor)
mensaje_Text.place(x=5, y=240, width=400, height=20)
mensaje_Text.bind("<Return>", enviar_Mensaje)

#Botones
Start_Button = tk.Button(Frame_chatservidor, text='Iniciar',width=9, command=iniciar_Servidor)
Start_Button.place(x=160, y=210)

Stop_Button = tk.Button(Frame_chatservidor, text='Detener',width=9, command=detener_Servidor, state=tk.DISABLED)
Stop_Button.place(x=240, y=210)

# #Boton
BDeliver = tk.Button(Frame_PLC, text="Deliver",
    command=lambda: enviar_comando("PLC", [estacion.get(), pallet.get(), "deliver"]),
    state=tk.DISABLED)
BDeliver.place(x=130, y=10)

BFree = tk.Button(Frame_PLC, text="Free",
    command=lambda: enviar_comando("PLC", [estacion.get(), pallet.get(), "free"]),
    state=tk.DISABLED)
BFree.place(x=130, y=40)

Bimprimir = tk.Button(Frame_laser, text="Imprimir",
    command=lambda: enviar_comando("Laser,Imprimir",[spinAruco.get()]),
    state=tk.DISABLED)
Bimprimir.place(x=130, y=6)

Balmacenar = tk.Button(Frame_almacen, text="Almacenar",
    command=lambda: enviar_comando("Almacen", [spinPosicion.get(), spinAruco_almacen.get(), "Almacenar"]),
    state=tk.DISABLED)
Balmacenar.place(x=130, y=10)

Bretirar=tk.Button(Frame_almacen, text="Retirar",command=lambda: enviar_comando("Almacen",[spinPosicion.get(),spinAruco_almacen.get(),"Retirar"]),state=tk.DISABLED)
Bretirar.place(x=130,y=40)

BPosicionar=tk.Button(Frame_laser, text="Posicionar",command=lambda: enviar_comando("Laser",["Posicionar"]),state=tk.DISABLED)
BPosicionar.place(x=10,y=40)

Bretirar_laser=tk.Button(Frame_laser, text="Retirar",command=lambda: enviar_comando("Laser",["Retirar"]),state=tk.DISABLED)
Bretirar_laser.place(x=80,y=40)

#Combobox
estacion = ttk.Combobox(
    Frame_PLC,
    state="readonly",
    values = [1,2, 3, 5, 6]
    )
estacion.set(1)
estacion.place(x = 70, y = 40,width = 50, height = 22)

pallet = ttk.Combobox(
    Frame_PLC,
    state="readonly",
    values = [1, 2, 3, 5, 6]
    )
pallet.set(1)
pallet.place(x = 70, y = 10,width=50, height=22)

#Spinbox
spinAruco=tk.Spinbox(Frame_laser,from_=1,to=15,font=("Arial", 12),width=2)
spinAruco.place(x=80,y=10)

spinAruco_almacen=tk.Spinbox(Frame_almacen,from_=1,to=15,font=("Arial", 12),width=2)
spinAruco_almacen.place(x=80,y=10)

spinPosicion=tk.Spinbox(Frame_almacen,from_=1,to=3,font=("Arial", 12),width=2)
spinPosicion.place(x=80,y=40)

ventana.protocol("WM_DELETE_WINDOW", on_closing)
ventana.mainloop()