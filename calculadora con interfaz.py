from tkinter import *
import numpy as np

ventana = Tk()
ventana.title("Calculadora")
ventana.geometry("400x190")


pepe1= Label(ventana, text="Juan")
pepe2= Label(ventana, text="Sergio")
pepe1.grid(row=0, column=0,padx=5, pady=5)
pepe2.grid(row=0, column=3,padx=5, pady=5)

entradaUno=Entry(ventana)
entradaDos=Entry(ventana)
entradaSuma= Entry(ventana, state = "readonly")
entradaResta= Entry(ventana, state = DISABLED)
ventana.mainloop()