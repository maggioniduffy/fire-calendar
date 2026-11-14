# SA2.2 y SA2.3 Baselines de armonización MODIS-VIIRS

Corrida: 2026-11-14, con `firecal harmonize evaluate` (tablas generadas por código). Fuente: archivos por país (Argentina) de NASA FIRMS, procesamiento standard (MODIS, VIIRS S-NPP y NOAA-20; el detalle de cada versión de procesamiento está sin verificar).
Período de los datos locales: 2000-11 a 2025-12; período de solapamiento usado: 2012-02 a 2025-12.
Filtros: type en [0], confianza MODIS >= 30, clase VIIRS en ['nominal', 'high'] (`FilterConfig` por defecto). Conteo: detecciones tras el filtro, sumadas desde la grilla de 0,1°.

Todo es retrospectivo: cuenta focos ya detectados y no es un sistema de alerta.

## Resumen

- Factor nacional (cociente de sumas, en la muestra, 2012-02 a 2025-12): VIIRS -> MODIS = 0.302 (día 0.360, noche 0.147); MODIS -> VIIRS = 3.314 (día 2.777, noche 6.796).
- VIIRS (S-NPP) -> MODIS-equivalente, año afuera: WAPE bloque-mes SA2.2 17.2 % vs SA2.3 19.4 % (menor error: SA2.2 factor); WAPE bloque-año SA2.2 10.1 % vs SA2.3 11.1 % (menor error: SA2.2 factor); sesgo relativo SA2.2 +0.9 %, SA2.3 +3.4 %.
- VIIRS (S-NPP) -> MODIS-equivalente, origen móvil: WAPE bloque-mes SA2.2 18.7 % vs SA2.3 21.9 % (menor error: SA2.2 factor); WAPE bloque-año SA2.2 11.4 % vs SA2.3 13.8 % (menor error: SA2.2 factor); sesgo relativo SA2.2 +2.4 %, SA2.3 +8.0 %.
- MODIS -> VIIRS-equivalente (serie inversa), año afuera: WAPE bloque-mes SA2.2 17.9 % vs SA2.3 19.4 % (menor error: SA2.2 factor); WAPE bloque-año SA2.2 10.6 % vs SA2.3 11.2 % (menor error: SA2.2 factor); sesgo relativo SA2.2 -0.9 %, SA2.3 -1.9 %.
- MODIS -> VIIRS-equivalente (serie inversa), origen móvil: WAPE bloque-mes SA2.2 18.7 % vs SA2.3 20.3 % (menor error: SA2.2 factor); WAPE bloque-año SA2.2 11.5 % vs SA2.3 12.7 % (menor error: SA2.2 factor); sesgo relativo SA2.2 -2.1 %, SA2.3 -6.6 %.
- MODIS -> VIIRS-equivalente (serie inversa), cobertura empírica del intervalo jackknife (factor) (nominal 80%, año afuera, block-month con origen > 0, todos los años de test): 31.8 %, anchura relativa 0.30; con origen u observado > 0 (definición anterior) 26.0 %.
- MODIS -> VIIRS-equivalente (serie inversa), cobertura empírica del intervalo dispersion interanual (nominal 80%, año afuera, block-month con origen > 0, todos los años de test): 66.1 %, anchura relativa 0.72; con origen u observado > 0 (definición anterior) 53.9 %.
- MODIS -> VIIRS-equivalente (serie inversa), cobertura empírica del intervalo conformal (residuos relativos) (nominal 80%, año afuera, block-month con origen > 0, todos los años de test): 80.1 %, anchura relativa 0.62; con origen u observado > 0 (definición anterior) 65.3 %.
- VIIRS (S-NPP) -> MODIS-equivalente, cobertura empírica del intervalo conformal (residuos relativos) (nominal 80%, año afuera, block-month con origen > 0, todos los años de test): 80.2 %, anchura relativa 0.59; con origen u observado > 0 (definición anterior) 79.3 %.
- MODIS -> VIIRS-equivalente (serie inversa), cobertura empírica del intervalo conformal (residuos relativos) (nominal 80%, año afuera, block-year con origen > 0, todos los años de test): 80.7 %, anchura relativa 0.37; con origen u observado > 0 (definición anterior) 74.9 %.
- VIIRS (S-NPP) -> MODIS-equivalente, cobertura empírica del intervalo conformal (residuos relativos) (nominal 80%, año afuera, block-year con origen > 0, todos los años de test): 80.6 %, anchura relativa 0.35; con origen u observado > 0 (definición anterior) 80.5 %.
- Cociente MODIS/S-NPP nacional por período (media de los cocientes anuales): 2012-2017 0.315, 2018 0.302, 2019-2022 0.292, 2023 0.300, 2024-2025 0.316.
- Mismo cociente sin filtro de `type`: 2012-2017 0.307, 2018 0.308, 2019-2022 0.292, 2023 0.296, 2024-2025 0.316; con el filtro por defecto desde las detecciones: 2012-2017 0.315, 2018 0.302, 2019-2022 0.292, 2023 0.300, 2024-2025 0.316.

## Datos y supuestos

- Escalas: MODIS = Terra + Aqua; VIIRS = S-NPP solo. NOAA-20 no se suma a S-NPP: se ajusta un factor de transferencia NOAA-20 -> S-NPP desde 2018-05.
- Regiones: bloques de 2,5° (origen -90/-180), 70 bloques con algún foco. Día y noche se ajustan por separado y se suman.
- Meses parciales excluidos: S-NPP 2012-01, NOAA-20 2018-04, Aqua 2002-07.
- Primer mes de S-NPP en los datos locales: 2012-02.
- Unidad: se ajusta sobre sumas por bloque x mes del año x día/noche; se evalúa por bloque-mes de cada año de test y por total bloque-año.
- Año afuera: cada año es test una vez; el entrenamiento excluye el año de test y 6 meses a cada lado. Origen móvil: entrenar con todos los años anteriores, evaluar el siguiente (sin separación).
- SA2.2: `f = (M + k * f_nacional) / (V + k)`; `k` se elige dentro del entrenamiento con año afuera interno (6 meses de separación), minimizando el WAPE bloque-mes, sobre la grilla {0, 5, 20, 100, 500, 2000, 10000}.
- SA2.3: ajuste de cuantiles por bloque sobre totales bloque-mes (meses del año juntos); solo positivos; cero va a cero; sobre el máximo de entrenamiento, cociente constante; con menos de 12 meses positivos en alguna de las dos series el bloque usa el ajuste de todos los bloques juntos.
- Métricas: sesgo relativo = suma(pred)/suma(obs) - 1; WAPE = suma|pred-obs|/suma(obs); MAE; devianza de Poisson media (media predicha mínima 0,001). Son totales de bloque-mes (n = bloques x meses de test) y totales bloque-año.

## Factores nacionales (en la muestra)

Cociente de sumas objetivo/origen sobre todos los meses del par, sin validación (descriptivo). `NOAA-20 -> S-NPP` es el factor de transferencia desde 2018-05.

| Par | Meses | N | Total | Día | Noche |
|---|---|---|---|---|---|
| S-NPP -> MODIS (Terra+Aqua) | 2012-02 a 2025-12 | 167 | 0.302 | 0.360 | 0.147 |
| MODIS (Terra+Aqua) -> S-NPP | 2012-02 a 2025-12 | 167 | 3.314 | 2.777 | 6.796 |
| S-NPP -> Terra | 2012-02 a 2025-12 | 167 | 0.106 | 0.109 | 0.097 |
| Terra -> S-NPP | 2012-02 a 2025-12 | 167 | 9.473 | 9.179 | 10.349 |
| NOAA-20 -> S-NPP | 2018-05 a 2025-12 | 92 | 1.015 | 1.016 | 1.015 |

Factor nacional por mes del año (día y noche juntos):

| Par | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S-NPP -> MODIS (Terra+Aqua) | 0.269 | 0.259 | 0.266 | 0.281 | 0.285 | 0.299 | 0.320 | 0.332 | 0.319 | 0.294 | 0.276 | 0.283 |
| MODIS (Terra+Aqua) -> S-NPP | 3.719 | 3.854 | 3.759 | 3.559 | 3.504 | 3.341 | 3.125 | 3.010 | 3.134 | 3.400 | 3.623 | 3.528 |

## Error por método y sentido (todos los años de test juntos)

### VIIRS (S-NPP) -> MODIS-equivalente

| Esquema | Método | Sesgo b-mes | WAPE b-mes | MAE b-mes | Devianza b-mes | Sesgo b-año | WAPE b-año | MAE b-año |
|---|---|---|---|---|---|---|---|---|
| año afuera | SA2.2 factor | +0.9 % | 17.2 % | 11.3 | 5.20 | +0.9 % | 10.1 % | 79.2 |
| año afuera | SA2.3 cuantiles | +3.4 % | 19.4 % | 12.7 | 6.33 | +3.4 % | 11.1 % | 87.1 |
| origen móvil | SA2.2 factor | +2.4 % | 18.7 % | 12.3 | 5.64 | +2.4 % | 11.4 % | 89.5 |
| origen móvil | SA2.3 cuantiles | +8.0 % | 21.9 % | 14.4 | 6.99 | +8.0 % | 13.8 % | 108.3 |

### MODIS -> VIIRS-equivalente (serie inversa)

| Esquema | Método | Sesgo b-mes | WAPE b-mes | MAE b-mes | Devianza b-mes | Sesgo b-año | WAPE b-año | MAE b-año |
|---|---|---|---|---|---|---|---|---|
| año afuera | SA2.2 factor | -0.9 % | 17.9 % | 39.0 | 27.71 | -0.9 % | 10.6 % | 275.7 |
| año afuera | SA2.3 cuantiles | -1.9 % | 19.4 % | 42.3 | 27.85 | -1.9 % | 11.2 % | 290.5 |
| origen móvil | SA2.2 factor | -2.1 % | 18.7 % | 40.8 | 29.44 | -2.1 % | 11.5 % | 301.4 |
| origen móvil | SA2.3 cuantiles | -6.6 % | 20.3 % | 44.3 | 30.53 | -6.6 % | 12.7 % | 332.1 |

## Error por año de test (año afuera)

### VIIRS (S-NPP) -> MODIS-equivalente

| Año | SA2.2 sesgo | SA2.2 WAPE b-mes | SA2.2 WAPE b-año | SA2.3 sesgo | SA2.3 WAPE b-mes | SA2.3 WAPE b-año | Menor error (b-mes) |
|---|---|---|---|---|---|---|---|
| 2012 | -3.6 % | 15.8 % | 9.9 % | -0.2 % | 16.6 % | 9.6 % | SA2.2 factor |
| 2013 | +1.7 % | 17.5 % | 8.7 % | -0.0 % | 18.4 % | 11.3 % | SA2.2 factor |
| 2014 | -4.7 % | 18.2 % | 11.5 % | +0.8 % | 18.9 % | 10.2 % | SA2.2 factor |
| 2015 | -0.8 % | 18.8 % | 12.8 % | +2.5 % | 19.9 % | 12.0 % | SA2.2 factor |
| 2016 | -1.5 % | 16.4 % | 9.5 % | -1.5 % | 19.3 % | 11.5 % | SA2.2 factor |
| 2017 | -2.2 % | 15.2 % | 8.7 % | -1.4 % | 18.2 % | 11.0 % | SA2.2 factor |
| 2018 | +2.7 % | 15.4 % | 8.6 % | +5.8 % | 16.9 % | 9.8 % | SA2.2 factor |
| 2019 | -0.1 % | 15.0 % | 7.9 % | +2.5 % | 19.3 % | 12.0 % | SA2.2 factor |
| 2020 | +6.0 % | 14.7 % | 8.7 % | +4.3 % | 15.3 % | 6.9 % | SA2.2 factor |
| 2021 | +4.0 % | 16.7 % | 9.2 % | +6.3 % | 18.4 % | 9.9 % | SA2.2 factor |
| 2022 | +11.4 % | 22.0 % | 15.0 % | +15.7 % | 26.4 % | 17.6 % | SA2.2 factor |
| 2023 | -2.3 % | 17.0 % | 7.6 % | +6.0 % | 21.4 % | 11.9 % | SA2.2 factor |
| 2024 | -10.2 % | 19.6 % | 12.3 % | -5.3 % | 21.1 % | 12.4 % | SA2.2 factor |
| 2025 | -1.5 % | 20.3 % | 12.3 % | +5.8 % | 25.3 % | 12.8 % | SA2.2 factor |

### MODIS -> VIIRS-equivalente (serie inversa)

| Año | SA2.2 sesgo | SA2.2 WAPE b-mes | SA2.2 WAPE b-año | SA2.3 sesgo | SA2.3 WAPE b-mes | SA2.3 WAPE b-año | Menor error (b-mes) |
|---|---|---|---|---|---|---|---|
| 2012 | +5.3 % | 18.7 % | 12.7 % | +2.7 % | 16.9 % | 9.5 % | SA2.3 cuantiles |
| 2013 | -2.2 % | 17.9 % | 8.6 % | +4.9 % | 20.4 % | 13.9 % | SA2.2 factor |
| 2014 | +4.1 % | 20.0 % | 13.3 % | -0.1 % | 18.9 % | 10.1 % | SA2.3 cuantiles |
| 2015 | -0.0 % | 19.4 % | 13.4 % | -0.7 % | 19.3 % | 12.0 % | SA2.3 cuantiles |
| 2016 | +0.1 % | 16.5 % | 9.5 % | +3.1 % | 19.9 % | 12.6 % | SA2.2 factor |
| 2017 | +1.5 % | 16.7 % | 9.1 % | +2.1 % | 19.3 % | 11.5 % | SA2.2 factor |
| 2018 | -2.6 % | 16.6 % | 8.9 % | -4.0 % | 16.0 % | 9.2 % | SA2.3 cuantiles |
| 2019 | -2.3 % | 17.4 % | 10.1 % | +0.8 % | 19.8 % | 12.5 % | SA2.2 factor |
| 2020 | -3.1 % | 14.7 % | 8.6 % | -3.2 % | 15.7 % | 6.4 % | SA2.2 factor |
| 2021 | -3.6 % | 17.4 % | 8.3 % | -5.8 % | 17.9 % | 9.1 % | SA2.2 factor |
| 2022 | -10.7 % | 19.8 % | 13.9 % | -14.6 % | 24.3 % | 16.7 % | SA2.2 factor |
| 2023 | +2.3 % | 18.2 % | 8.2 % | -4.1 % | 19.7 % | 10.2 % | SA2.2 factor |
| 2024 | +12.1 % | 23.3 % | 15.4 % | +8.3 % | 22.4 % | 14.2 % | SA2.3 cuantiles |
| 2025 | +0.1 % | 19.9 % | 12.4 % | -5.0 % | 24.3 % | 11.7 % | SA2.2 factor |

Detalle por bloque (año afuera, años de test juntos): `baselines_by_block.csv`.

## Elección de k (SA2.2, año afuera)

| Año de test | VIIRS (S-NPP) -> MODIS-equivalente | MODIS -> VIIRS-equivalente (serie inversa) |
|---|---|---|
| 2012 | 500 | 100 |
| 2013 | 500 | 100 |
| 2014 | 500 | 100 |
| 2015 | 500 | 100 |
| 2016 | 500 | 100 |
| 2017 | 500 | 100 |
| 2018 | 500 | 100 |
| 2019 | 500 | 100 |
| 2020 | 500 | 20 |
| 2021 | 500 | 20 |
| 2022 | 500 | 20 |
| 2023 | 500 | 100 |
| 2024 | 500 | 100 |
| 2025 | 500 | 100 |

`k` es un pseudo-conteo en unidades del origen: `k = 0` es el cociente puro del bloque y `k = 10000` casi lo lleva al factor nacional.

## Intervalos

Nivel nominal 80%. Cobertura empírica sobre bloque-mes (o bloque-año) con conteo de origen mayor que cero (lo que se conoce al predecir), por año de test (año afuera). `coverage_any` en la sección Lectura usa la definición anterior (origen u observado > 0). Anchura relativa = suma de anchuras / suma de predicciones.

- `jackknife (factor)` y `dispersion interanual` (solo serie inversa, bloque-mes): factor +/- z * error estándar jackknife (z = 1,28), y cuantiles 10 % y 90 % de los factores de cada año de entrenamiento. Solo describen la incertidumbre del factor, no el ruido del conteo del mes de test.
- `conformal (residuos relativos)` (los dos sentidos, bloque-mes y bloque-año): dentro del entrenamiento de cada partición externa se corre el año afuera interno (6 meses de separación, con el `k` ya elegido para esa partición) y se juntan los residuos relativos `obs / pred` fuera de muestra sobre bloque-meses con origen > 0 (`obs = 0` da residuo 0). Las predicciones de hasta 5 focos (bloque-mes) o 10 (bloque-año), 0 incluido, usan un intervalo aditivo: cuantiles conformales de `obs - pred` de esas filas internas (umbral fijo de antemano, no ajustado con ningún año de test). El resto se estratifica en 5 clases de conteo predicho, con bordes por cuantiles de la predicción fuera de muestra de entrenamiento (clases con menos de 30 residuos se funden con la vecina). El intervalo es `pred * [q10, q90]` de la clase, con la corrección conformal de muestra finita (rangos ceil(0,9 (n+1)) y floor(0,1 (n+1))). Bloque-año no suma cotas de bloque-mes: se calibra con residuos de totales bloque-año de los mismos años internos, con sus propias clases. Nada se ajusta con los años de test externos. Los modelos internos usan un año menos de entrenamiento que el modelo externo, lo que tiende a ensanchar un poco.

### VIIRS (S-NPP) -> MODIS-equivalente, block-month

| Año | conformal (residuos relativos) cobertura | conformal (residuos relativos) anchura |
|---|---|---|
| 2012 | 79.9 % | 0.59 |
| 2013 | 83.3 % | 0.57 |
| 2014 | 77.1 % | 0.64 |
| 2015 | 77.3 % | 0.61 |
| 2016 | 78.3 % | 0.57 |
| 2017 | 81.6 % | 0.58 |
| 2018 | 84.9 % | 0.60 |
| 2019 | 82.6 % | 0.63 |
| 2020 | 84.6 % | 0.55 |
| 2021 | 78.9 % | 0.59 |
| 2022 | 80.8 % | 0.54 |
| 2023 | 79.0 % | 0.60 |
| 2024 | 77.7 % | 0.62 |
| 2025 | 76.5 % | 0.60 |
| todos | 80.2 % | 0.59 |

### VIIRS (S-NPP) -> MODIS-equivalente, block-year

| Año | conformal (residuos relativos) cobertura | conformal (residuos relativos) anchura |
|---|---|---|
| 2012 | 86.6 % | 0.36 |
| 2013 | 83.3 % | 0.35 |
| 2014 | 78.8 % | 0.36 |
| 2015 | 69.7 % | 0.35 |
| 2016 | 78.8 % | 0.33 |
| 2017 | 86.4 % | 0.35 |
| 2018 | 89.1 % | 0.37 |
| 2019 | 89.4 % | 0.37 |
| 2020 | 80.6 % | 0.33 |
| 2021 | 76.9 % | 0.35 |
| 2022 | 76.1 % | 0.33 |
| 2023 | 85.3 % | 0.38 |
| 2024 | 80.3 % | 0.39 |
| 2025 | 67.2 % | 0.38 |
| todos | 80.6 % | 0.35 |

### MODIS -> VIIRS-equivalente (serie inversa), block-month

| Año | jackknife (factor) cobertura | jackknife (factor) anchura | dispersion interanual cobertura | dispersion interanual anchura | conformal (residuos relativos) cobertura | conformal (residuos relativos) anchura |
|---|---|---|---|---|---|---|
| 2012 | 29.6 % | 0.29 | 68.0 % | 0.73 | 83.8 % | 0.63 |
| 2013 | 33.2 % | 0.31 | 69.7 % | 0.68 | 82.4 % | 0.63 |
| 2014 | 26.1 % | 0.29 | 60.4 % | 0.64 | 80.0 % | 0.68 |
| 2015 | 33.3 % | 0.29 | 64.7 % | 0.68 | 74.5 % | 0.65 |
| 2016 | 26.9 % | 0.29 | 62.3 % | 0.66 | 74.7 % | 0.61 |
| 2017 | 33.5 % | 0.30 | 70.8 % | 0.77 | 81.2 % | 0.64 |
| 2018 | 33.8 % | 0.27 | 71.3 % | 0.74 | 85.4 % | 0.66 |
| 2019 | 26.3 % | 0.26 | 68.9 % | 0.65 | 85.3 % | 0.67 |
| 2020 | 45.1 % | 0.34 | 73.7 % | 0.74 | 80.4 % | 0.58 |
| 2021 | 36.2 % | 0.33 | 65.8 % | 0.74 | 80.7 % | 0.62 |
| 2022 | 37.0 % | 0.37 | 65.2 % | 0.76 | 76.7 % | 0.57 |
| 2023 | 30.0 % | 0.26 | 61.8 % | 0.81 | 80.8 % | 0.62 |
| 2024 | 25.5 % | 0.25 | 60.3 % | 0.72 | 77.8 % | 0.63 |
| 2025 | 27.8 % | 0.28 | 61.7 % | 0.70 | 77.3 % | 0.62 |
| todos | 31.8 % | 0.30 | 66.1 % | 0.72 | 80.1 % | 0.62 |

### MODIS -> VIIRS-equivalente (serie inversa), block-year

| Año | conformal (residuos relativos) cobertura | conformal (residuos relativos) anchura |
|---|---|---|
| 2012 | 79.0 % | 0.37 |
| 2013 | 87.5 % | 0.38 |
| 2014 | 75.4 % | 0.38 |
| 2015 | 81.0 % | 0.39 |
| 2016 | 87.1 % | 0.39 |
| 2017 | 85.2 % | 0.38 |
| 2018 | 81.7 % | 0.37 |
| 2019 | 82.0 % | 0.40 |
| 2020 | 84.1 % | 0.34 |
| 2021 | 83.6 % | 0.35 |
| 2022 | 73.3 % | 0.34 |
| 2023 | 82.8 % | 0.39 |
| 2024 | 74.2 % | 0.39 |
| 2025 | 72.1 % | 0.37 |
| todos | 80.7 % | 0.37 |

### Cobertura conformal por tamaño predicho (año afuera, años de test juntos)

Clases fijas de la predicción (solo para informar, no se ajusta nada con ellas); `n` = bloque-meses (o bloque-años) con origen > 0.

VIIRS (S-NPP) -> MODIS-equivalente, block-month:

| Predicción | n | Cobertura | Anchura |
|---|---|---|---|
| = 0 | 0 | - | - |
| (0, 1] | 1529 | 96.2 % | 6.06 |
| (1, 5] | 1815 | 66.8 % | 1.67 |
| (5, 20] | 2250 | 80.1 % | 1.56 |
| (20, 100] | 2058 | 80.1 % | 0.81 |
| (100, 500] | 1085 | 77.3 % | 0.52 |
| > 500 | 392 | 89.0 % | 0.49 |

VIIRS (S-NPP) -> MODIS-equivalente, block-year:

| Predicción | n | Cobertura | Anchura |
|---|---|---|---|
| = 0 | 0 | - | - |
| (0, 10] | 197 | 81.2 % | 1.45 |
| (10, 50] | 147 | 79.6 % | 1.12 |
| (50, 200] | 138 | 79.7 % | 0.97 |
| (200, 1000] | 240 | 80.4 % | 0.47 |
| (1000, 5000] | 175 | 80.0 % | 0.31 |
| > 5000 | 27 | 92.6 % | 0.30 |

MODIS -> VIIRS-equivalente (serie inversa), block-month:

| Predicción | n | Cobertura | Anchura |
|---|---|---|---|
| = 0 | 0 | - | - |
| (0, 1] | 1 | 100.0 % | 22.10 |
| (1, 5] | 675 | 80.1 % | 5.53 |
| (5, 20] | 1541 | 79.1 % | 2.56 |
| (20, 100] | 2289 | 79.8 % | 1.37 |
| (100, 500] | 1891 | 79.6 % | 0.77 |
| > 500 | 1130 | 82.7 % | 0.52 |

MODIS -> VIIRS-equivalente (serie inversa), block-year:

| Predicción | n | Cobertura | Anchura |
|---|---|---|---|
| = 0 | 0 | - | - |
| (0, 10] | 69 | 81.2 % | 6.63 |
| (10, 50] | 136 | 77.9 % | 3.25 |
| (50, 200] | 89 | 76.4 % | 1.29 |
| (200, 1000] | 192 | 82.8 % | 0.74 |
| (1000, 5000] | 215 | 80.5 % | 0.41 |
| > 5000 | 158 | 82.9 % | 0.33 |

### Lectura

- MODIS -> VIIRS-equivalente (serie inversa), block-month: cobertura 80.1 % (dentro de 75-85 %), anchura 0.62; con origen u observado > 0 (definición anterior): 65.3 %. Fuera del alcance del factor (origen = 0 y observado > 0): 1702 filas, 0.3 % de las detecciones del objetivo; factor e intervalo predicen 0 ahí.
- VIIRS (S-NPP) -> MODIS-equivalente, block-month: cobertura 80.2 % (dentro de 75-85 %), anchura 0.59; con origen u observado > 0 (definición anterior): 79.3 %. Fuera del alcance del factor (origen = 0 y observado > 0): 100 filas, 0.0 % de las detecciones del objetivo; factor e intervalo predicen 0 ahí.
- MODIS -> VIIRS-equivalente (serie inversa), block-year: cobertura 80.7 % (dentro de 75-85 %), anchura 0.37; con origen u observado > 0 (definición anterior): 74.9 %. Fuera del alcance del factor (origen = 0 y observado > 0): 66 filas, 0.0 % de las detecciones del objetivo; factor e intervalo predicen 0 ahí.
- VIIRS (S-NPP) -> MODIS-equivalente, block-year: cobertura 80.6 % (dentro de 75-85 %), anchura 0.35; con origen u observado > 0 (definición anterior): 80.5 %. Fuera del alcance del factor (origen = 0 y observado > 0): 1 filas, 0.0 % de las detecciones del objetivo; factor e intervalo predicen 0 ahí.

Todas las combinaciones sentido x nivel caen en 75-85 %: sí.

Las filas con origen = 0 y observado > 0 no se cubren por construcción (el factor no tiene qué multiplicar): el otro sensor ve focos donde este no marcó ninguno. Su conteo y su parte de las detecciones se informan arriba y no entran en la cobertura de cabecera, que usa solo filas definidas por el origen, conocido al predecir. La cobertura por año varía más en bloque-año (pocas filas por año de test). Los residuos de entrenamiento se tratan como intercambiables con los del año de test: si la relación cambia con el tiempo (por ejemplo la deriva de Terra, sin verificar), la cobertura de un año puede quedar por debajo.

## Variantes: Terra solo y NOAA-20 -> S-NPP (año afuera)

| Par | Método | Sesgo b-mes | WAPE b-mes | WAPE b-año |
|---|---|---|---|---|
| S-NPP -> Terra | SA2.2 factor | +1.3 % | 29.2 % | 16.9 % |
| S-NPP -> Terra | SA2.3 cuantiles | +9.7 % | 35.7 % | 19.5 % |
| Terra -> S-NPP | SA2.2 factor | -0.3 % | 29.5 % | 16.2 % |
| Terra -> S-NPP | SA2.3 cuantiles | -4.3 % | 32.9 % | 17.5 % |
| NOAA-20 -> S-NPP | SA2.2 factor | -0.3 % | 11.5 % | 5.1 % |
| NOAA-20 -> S-NPP | SA2.3 cuantiles | +0.2 % | 13.0 % | 6.6 % |

## Estabilidad

Cocientes de sumas nacionales por año con el conteo por defecto (grilla de 0,1°). `Meses` = meses completos usados (los parciales están excluidos). Sin ajuste por época: es la tabla pedida por el diseño para decidir si hace falta. La tabla por bloque no se incluye en esta corrida.

### MODIS / S-NPP por año

| Año | Meses | MODIS/S-NPP | Día | Noche | Terra/S-NPP | Aqua/S-NPP |
|---|---|---|---|---|---|---|
| 2012 | 11 | 0.320 | 0.378 | 0.154 | 0.112 | 0.209 |
| 2013 | 12 | 0.300 | 0.373 | 0.138 | 0.111 | 0.189 |
| 2014 | 12 | 0.318 | 0.380 | 0.166 | 0.126 | 0.193 |
| 2015 | 12 | 0.312 | 0.364 | 0.146 | 0.111 | 0.201 |
| 2016 | 12 | 0.323 | 0.393 | 0.146 | 0.112 | 0.212 |
| 2017 | 12 | 0.318 | 0.381 | 0.157 | 0.118 | 0.200 |
| 2018 | 12 | 0.302 | 0.353 | 0.147 | 0.106 | 0.196 |
| 2019 | 12 | 0.319 | 0.379 | 0.134 | 0.110 | 0.208 |
| 2020 | 12 | 0.284 | 0.332 | 0.143 | 0.097 | 0.186 |
| 2021 | 12 | 0.303 | 0.354 | 0.133 | 0.107 | 0.196 |
| 2022 | 12 | 0.262 | 0.317 | 0.141 | 0.092 | 0.170 |
| 2023 | 12 | 0.300 | 0.368 | 0.155 | 0.112 | 0.188 |
| 2024 | 12 | 0.338 | 0.404 | 0.161 | 0.105 | 0.233 |
| 2025 | 12 | 0.294 | 0.347 | 0.155 | 0.085 | 0.209 |

### NOAA-20 / S-NPP por año (control sin MODIS)

| Año | Meses | NOAA-20/S-NPP | Día | Noche |
|---|---|---|---|---|
| 2018 | 8 | 0.9594 | 0.9593 | 0.9602 |
| 2019 | 12 | 0.9836 | 0.9995 | 0.9348 |
| 2020 | 12 | 0.9751 | 0.9817 | 0.9557 |
| 2021 | 12 | 1.0057 | 1.0086 | 0.9960 |
| 2022 | 12 | 0.9884 | 0.9733 | 1.0213 |
| 2023 | 12 | 0.9497 | 0.9404 | 0.9695 |
| 2024 | 12 | 1.0321 | 1.0301 | 1.0374 |
| 2025 | 12 | 0.9930 | 0.9900 | 1.0008 |

### Terra / Aqua por año

| Año | Meses | Terra/Aqua | Día | Noche |
|---|---|---|---|---|
| 2003 | 12 | 0.520 | 0.434 | 1.558 |
| 2004 | 12 | 0.558 | 0.467 | 1.779 |
| 2005 | 12 | 0.598 | 0.499 | 1.905 |
| 2006 | 12 | 0.560 | 0.474 | 1.832 |
| 2007 | 12 | 0.527 | 0.432 | 1.827 |
| 2008 | 12 | 0.543 | 0.452 | 1.734 |
| 2009 | 12 | 0.562 | 0.450 | 1.686 |
| 2010 | 12 | 0.591 | 0.485 | 1.793 |
| 2011 | 12 | 0.594 | 0.493 | 1.733 |
| 2012 | 12 | 0.561 | 0.459 | 1.874 |
| 2013 | 12 | 0.584 | 0.470 | 1.962 |
| 2014 | 12 | 0.651 | 0.543 | 1.727 |
| 2015 | 12 | 0.552 | 0.468 | 1.831 |
| 2016 | 12 | 0.528 | 0.443 | 1.549 |
| 2017 | 12 | 0.592 | 0.489 | 1.753 |
| 2018 | 12 | 0.543 | 0.443 | 2.133 |
| 2019 | 12 | 0.531 | 0.454 | 1.821 |
| 2020 | 12 | 0.522 | 0.427 | 1.774 |
| 2021 | 12 | 0.547 | 0.464 | 2.054 |
| 2022 | 12 | 0.541 | 0.413 | 1.757 |
| 2023 | 12 | 0.593 | 0.463 | 1.896 |
| 2024 | 12 | 0.451 | 0.337 | 2.373 |
| 2025 | 12 | 0.407 | 0.263 | 3.350 |

### Hora media de adquisición (UTC) por satélite y año

Detecciones tras el filtro por defecto, desde `acq_datetime`. Las horas de noche posteriores a las 12:00 se promedian como horas negativas para no cortar en la medianoche.

| Año | terra D | terra N | aqua D | aqua N | snpp D | snpp N | noaa20 D | noaa20 N |
|---|---|---|---|---|---|---|---|---|
| 2000 | 14:41 | 03:27 | - | - | - | - | - | - |
| 2001 | 14:31 | 03:21 | - | - | - | - | - | - |
| 2002 | 14:25 | 03:07 | 18:05 | 05:30 | - | - | - | - |
| 2003 | 14:22 | 03:02 | 17:58 | 05:27 | - | - | - | - |
| 2004 | 14:20 | 02:52 | 17:56 | 05:27 | - | - | - | - |
| 2005 | 14:20 | 02:55 | 17:57 | 05:24 | - | - | - | - |
| 2006 | 14:18 | 02:54 | 17:57 | 05:25 | - | - | - | - |
| 2007 | 14:22 | 02:52 | 18:00 | 05:29 | - | - | - | - |
| 2008 | 14:19 | 02:53 | 18:00 | 05:26 | - | - | - | - |
| 2009 | 14:23 | 02:56 | 18:04 | 05:31 | - | - | - | - |
| 2010 | 14:21 | 02:55 | 18:01 | 05:29 | - | - | - | - |
| 2011 | 14:21 | 02:54 | 18:00 | 05:28 | - | - | - | - |
| 2012 | 14:20 | 02:52 | 17:57 | 05:27 | 17:49 | 05:10 | - | - |
| 2013 | 14:20 | 02:56 | 18:00 | 05:30 | 17:56 | 05:19 | - | - |
| 2014 | 14:22 | 02:57 | 17:58 | 05:27 | 17:58 | 05:20 | - | - |
| 2015 | 14:20 | 03:02 | 18:02 | 05:28 | 17:59 | 05:18 | - | - |
| 2016 | 14:22 | 03:04 | 18:01 | 05:21 | 17:55 | 05:11 | - | - |
| 2017 | 14:23 | 03:03 | 18:02 | 05:30 | 17:56 | 05:12 | - | - |
| 2018 | 14:22 | 03:01 | 18:01 | 05:27 | 17:54 | 05:12 | 17:53 | 05:12 |
| 2019 | 14:21 | 02:59 | 17:59 | 05:27 | 17:53 | 05:14 | 17:54 | 05:15 |
| 2020 | 14:18 | 02:51 | 17:56 | 05:22 | 17:50 | 05:09 | 17:48 | 05:08 |
| 2021 | 14:16 | 02:51 | 17:58 | 05:24 | 17:52 | 05:10 | 17:53 | 05:11 |
| 2022 | 14:06 | 02:38 | 18:02 | 05:22 | 17:51 | 05:10 | 17:52 | 05:11 |
| 2023 | 13:55 | 02:27 | 18:13 | 05:35 | 17:53 | 05:10 | 17:50 | 05:07 |
| 2024 | 13:36 | 02:09 | 18:36 | 06:04 | 17:53 | 05:12 | 17:51 | 05:11 |
| 2025 | 13:15 | 01:48 | 19:08 | 06:35 | 17:57 | 05:17 | 17:53 | 05:13 |

### Con y sin filtro de `type`

Cociente MODIS/S-NPP desde las detecciones, con el filtro por defecto (`type` = 0) y sin filtro de `type` (`types=(0,1,2,3)`, con `type` faltante incluido; mismos filtros de confianza). El mes parcial 2012-01 está fuera. Fracción con `type` distinto de 0 = 1 - conteo con filtro / conteo sin filtro.

| Año | MODIS con filtro | MODIS sin filtro | MODIS type != 0 | MODIS/S-NPP con filtro | MODIS/S-NPP sin filtro | S-NPP type != 0 |
|---|---|---|---|---|---|---|
| 2000 | 6732 | 6752 | 0.3 % | - | - | - |
| 2001 | 29995 | 30231 | 0.8 % | - | - | - |
| 2002 | 57491 | 57857 | 0.6 % | - | - | - |
| 2003 | 110975 | 112140 | 1.0 % | - | - | - |
| 2004 | 94954 | 95369 | 0.4 % | - | - | - |
| 2005 | 67113 | 68337 | 1.8 % | - | - | - |
| 2006 | 79808 | 80302 | 0.6 % | - | - | - |
| 2007 | 73982 | 75044 | 1.4 % | - | - | - |
| 2008 | 98975 | 99330 | 0.4 % | - | - | - |
| 2009 | 78036 | 78386 | 0.4 % | - | - | - |
| 2010 | 59424 | 60057 | 1.1 % | - | - | - |
| 2011 | 72924 | 73420 | 0.7 % | - | - | - |
| 2012 | 52608 | 53196 | 1.1 % | 0.320 | 0.314 | 3.2 % |
| 2013 | 63106 | 63483 | 0.6 % | 0.300 | 0.292 | 3.3 % |
| 2014 | 34538 | 35048 | 1.5 % | 0.318 | 0.305 | 5.5 % |
| 2015 | 42498 | 42906 | 1.0 % | 0.312 | 0.303 | 3.6 % |
| 2016 | 52693 | 52932 | 0.5 % | 0.323 | 0.318 | 2.2 % |
| 2017 | 57317 | 57601 | 0.5 % | 0.318 | 0.311 | 2.6 % |
| 2018 | 49992 | 52550 | 4.9 % | 0.302 | 0.308 | 3.0 % |
| 2019 | 45668 | 48031 | 4.9 % | 0.319 | 0.324 | 3.4 % |
| 2020 | 113716 | 116336 | 2.3 % | 0.284 | 0.285 | 1.7 % |
| 2021 | 51590 | 53691 | 3.9 % | 0.303 | 0.300 | 4.7 % |
| 2022 | 71024 | 72901 | 2.6 % | 0.262 | 0.260 | 3.1 % |
| 2023 | 44095 | 45687 | 3.5 % | 0.300 | 0.296 | 4.6 % |
| 2024 | 45453 | 47594 | 4.5 % | 0.338 | 0.338 | 4.3 % |
| 2025 | 43860 | 45675 | 4.0 % | 0.294 | 0.294 | 4.0 % |

## Notas

- Qué causa cada diferencia entre años (versión de MODIS, tipo de fuente, deriva orbital) está **sin verificar**: las tablas solo describen.
- La serie inversa estima cuántos focos habría registrado VIIRS en un bloque y mes; no ubica focos individuales. Se llama 'estimado', nunca 'detectado'.
- No hay ajuste por época: si la tabla de estabilidad muestra un escalón con el control NOAA-20/S-NPP plano, el diseño pide ajustar por época y retomar SA2.8.
