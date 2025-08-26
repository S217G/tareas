print("Bienvenido a la calculadora ")
print("Ingrese los dos primeros valores")
print("Seleccione el valor numero 1")
a=int(input())
print("Seleccione el valor numero 2")
b=int(input())
print("Seleccione una opcion ")
print("========================== ")
print("1 SUMA ")
print("2 RESTA ")
print("3 Multiplicacion ")
print("4 DIVISION ")
x=int(input())

if x==1:
    s=a+b
    print(f"la suma es {s}")
elif x==2:
    s=a-b
    print(f"la resta es {s}")
elif x==3:
    s=a*b
    print(f"la multiplicacion es {s}")
elif x==4:
    while a==0:
        print("No puede ser 0 el primer valor!")
        a=int(input())
    while b==0:
        print("No puede ser 0 el segundo valor!")
        b=int(input())
    s=a/b
    print(f"La division es {s}")