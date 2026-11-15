# Sesgo del modelo de celda de LightGBM: ¿es estructural?

Corrida: 2026-11-15, con `backend/scripts/ml_bias_check.py` sobre la caché de la corrida final de
`firecal harmonize evaluate --ml` (sin reentrenar). Fuente: archivos por país de NASA FIRMS, procesamiento
standard; año afuera con 6 meses de separación, 14 años de test (2012–2025). Retrospectivo; no es un sistema de
alerta.

## Hipótesis

El modelo de celda solo predice en las filas donde la fuente está activa en la celda o en su 3×3, pero se lo
evalúa contra todas las detecciones del objetivo. Las detecciones fuera de esas filas son inalcanzables, así que
el sesgo total debería ser aproximadamente `−(fracción fuera de las filas)`.

## Resultado: estructural en el total, no en los años sueltos

| Sentido | Fracción fuera de las filas | Sesgo celda vs. todo | Sesgo celda vs. sus filas | Sesgo SA2.2 |
|---|---|---|---|---|
| SA2.4 VIIRS → MODIS | 2,58 % | −2,52 % | +0,06 % | +0,93 % |
| SA2.7 MODIS → VIIRS | 6,22 % | −6,73 % | −0,54 % | −0,95 % |

- **Total (verificado):** contado sobre sus propias filas, el sesgo del modelo de celda es casi cero (+0,06 % y
  −0,54 %). El sesgo negativo total viene de las detecciones que el modelo no puede alcanzar. La relación
  `sesgo_total = (1 + sesgo_filas) × (1 − fracción_fuera) − 1` se cumple exacta, pero es una identidad contable;
  la prueba de verdad es que `sesgo_filas ≈ 0`, y en el total se cumple.
- **Por año (no estructural):** el sesgo en sus filas va de −10,0 % a +3,6 % (SA2.4) y de −8,9 % a +5,3 %
  (SA2.7), mientras la fracción fuera va de 0,9 % a 9,4 %. La fracción fuera explica solo unos puntos de cada año.
- **Peor año de SA2.4 (2024, −12,4 %):** fracción fuera 2,7 %; en sus filas sigue en −10,0 %. No es
  estructural, y SA2.2 tiene casi el mismo sesgo ese año (−10,2 %): es un año difícil para los dos métodos, no un
  defecto propio de LightGBM. La causa queda sin verificar (2024 es el año en que cambia el cociente Terra/Aqua,
  ver la tabla de estabilidad en `baselines.md`).
- **Peor año de SA2.7 (2022, −13,0 %):** fracción fuera 4,6 %; en sus filas −8,9 %; SA2.2 −10,7 % ese año.
- **SA2.2 no cambia** si se lo restringe al alcance del modelo de celda (+0,93 % y −0,95 %): solo 0,02 % y 0,30 %
  de las detecciones caen en bloque-meses donde SA2.2 predice 0.

## Qué cambia

El veredicto no cambia: el criterio de publicación estaba fijado antes de la corrida y el modelo de celda falla
el sesgo total tal como se evaluó. Lo que sí se aprende: si se quisiera mejorar el modelo de celda, la pieza que
falta es estimar las detecciones fuera de sus filas (por ejemplo con el factor de bloque), no corregir el modelo
dentro de ellas. Eso sería un diseño nuevo y una corrida nueva con el criterio fijado de antemano, no un ajuste
de esta.

Comparación no usada en el veredicto: "SA2.2 vs. filas del modelo de celda" (+3,6 % y +5,6 %) no es justa,
porque SA2.2 es por bloque y no se entrenó sobre esas filas.

Reproducir: `cd backend && uv run python scripts/ml_bias_check.py <ml-cache.pkl>`.
