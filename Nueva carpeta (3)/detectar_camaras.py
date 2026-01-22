"""
Script para detectar cámaras disponibles en el sistema
"""
import cv2

def detectar_camaras():
    """Detecta todas las cámaras disponibles"""
    print("Detectando cámaras disponibles...")
    camaras = []
    
    # Probar índices del 0 al 9
    for idx in range(10):
        try:
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            if cap is None or not cap.isOpened():
                continue
            
            # Intentar leer un frame para confirmar que funciona
            ret, frame = cap.read()
            if ret:
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = int(cap.get(cv2.CAP_PROP_FPS))
                camaras.append({
                    'índice': idx,
                    'resolución': f'{width}x{height}',
                    'fps': fps
                })
                print(f"✓ Cámara encontrada en índice {idx}: {width}x{height} @ {fps}fps")
            
            cap.release()
        except Exception as e:
            pass
    
    if camaras:
        print(f"\nTotal de cámaras detectadas: {len(camaras)}")
        for cam in camaras:
            print(f"  Índice {cam['índice']}: {cam['resolución']} @ {cam['fps']}fps")
        return camaras
    else:
        print("No se detectaron cámaras disponibles")
        return []

if __name__ == "__main__":
    detectar_camaras()
