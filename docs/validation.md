# Validación

Adaptado del esquema F6.2 de clima-ideas. Nada de k-fold aleatorio: días vecinos y meses de un mismo año (y de un
mismo año ENSO) filtran información entre entrenamiento y test.

- **Externa, un año afuera con separación:** cada año es una vez el test; se quitan del entrenamiento los 6 meses
  anteriores y posteriores a ese año. Se informa el error por año, por región y por fase ENSO.
- **Interna, anidada:** hiperparámetros y selección de variables se eligen solo dentro del entrenamiento de cada
  partición externa. El año de test externo nunca toca esa elección.
- **Entradas tal como estaban disponibles** (solo para predicción, fase 6): ninguna variable con fecha de
  disponibilidad posterior a la de emisión.
- **Control:** el mismo esquema con origen móvil puro (entrenar hasta el año t, evaluar t+1), para ver si el error
  cambia en los años recientes.
- **Baseline siempre al lado:** cada modelo se compara con el método más simple de su tarea (factor de escala en
  la armonización, climatología y persistencia en predicción). Se publica el más simple que no pierde.
- Unit: ninguna fecha de test, separación incluida, aparece en el entrenamiento de su partición.
