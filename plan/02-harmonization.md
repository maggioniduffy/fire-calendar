# Fase 2 — Armonización MODIS–VIIRS

Estado: activa (SA2.6, SA2.8, SA2.9 y SA2.10 postergadas) · Depende de: 1 · Refs: `docs/validation.md`

## Pregunta

¿Cómo convertir 2000–hoy en una sola serie donde el sensor de origen ya no importe, en las dos escalas y sin
cortarse cuando MODIS deje de operar?

## Enfoque

Solapamiento 2012–hoy: los dos sensores miden lo mismo. VIIRS ve más focos chicos por su resolución (375 m vs.
1 km), y los horarios de paso difieren. Con ese período se calibra en los dos sentidos:

- **Hacia MODIS:** VIIRS → "MODIS-equivalente". Serie larga y comparable con la literatura.
- **Hacia VIIRS (serie inversa):** MODIS → "VIIRS-equivalente" para 2000–2011. Estima cuántos focos habría
  registrado VIIRS en un área y período, con incertidumbre; no ubica focos individuales que MODIS no detectó.
  En la UI dice "estimado", nunca "detectado".
- **Continuidad:** cuando MODIS se apague, cada año nuevo de VIIRS (S-NPP, NOAA-20, NOAA-21 y siguientes JPSS,
  sin verificar fechas) entra a las dos series con la calibración congelada.

Supervisado, no aprendizaje por refuerzo: hay pares observados (MODIS y VIIRS, misma celda y día) y no hay
agente, entorno ni recompensa.

## Diseño de los baselines (decidido 2026-11-14, con consulta al asesor)

Todo lo de abajo es diseño; los supuestos sobre los datos quedan "sin verificar" hasta la primera corrida real.

- **Escalas:** MODIS = Terra + Aqua; VIIRS = S-NPP solo. NOAA-20 nunca se suma a S-NPP: entra por un factor de
  transferencia NOAA-20→S-NPP ajustado desde 2018-05, que se encadena para la continuidad. Se excluyen los meses
  parciales 2012-01 y 2018-04. Día y noche se ajustan por separado y se suman. Los meses con solo Terra (antes
  de Aqua) necesitan un factor Terra-solo.
- **Conteo:** el que muestra el calendario: detecciones tras `FilterConfig`, tal como salen de la grilla de 0,1°.
  La tabla de celdas de 1 km por día (SA2.1, par Aqua ~ S-NPP) queda para LightGBM y como diagnóstico. Todos
  los métodos se evalúan sobre el mismo conteo.
- **Región:** bloques de 2,5° lat/lon (origen −90/−180, anidan con las dos grillas, sin datos nuevos).
- **Unidad:** se ajusta sobre sumas por región × mes del año × día/noche; se evalúa por región-mes de cada año
  de test y por total región-año.
- **Estimador (SA2.2):** cociente de sumas, con encogimiento hacia el factor nacional del mismo mes y día/noche:
  `f = (M + k·f_nacional) / (V + k)`, con `k` elegido dentro del entrenamiento. Intervalos a partir de la
  dispersión de los factores año afuera, no de la varianza de Poisson.
- **Métricas** (las mismas para ML después), por año de test, región y sentido: sesgo relativo (Σpred/Σobs − 1),
  WAPE, MAE, devianza de Poisson media y, en la serie inversa, cobertura del intervalo.
- **Ajuste de cuantiles (SA2.3):** sobre totales región-mes, juntando los meses del año; cero va a cero y se
  ajustan solo los positivos; por encima del máximo de entrenamiento, cociente constante. No es aditivo, así que
  no se aplica celda por celda: sirve para ver si el cociente depende del nivel de actividad.
- **Estabilidad (versión MODIS y deriva orbital):** año y `version` no entran al baseline. Con la primera corrida
  se publica una tabla: factor por año (nacional y por bloque, por día/noche y por Terra y Aqua), NOAA-20/S-NPP
  por año como control sin MODIS, Terra/Aqua por año, hora media de adquisición por satélite y año, y el control
  de origen móvil. Si aparece un escalón en 2018 o 2023 con el control VIIRS plano, se ajusta por época y la
  serie inversa se calibra solo con 2012–2017 (misma `version` que 2000–2011), y se retoma SA2.8.

- **Hallazgo 2026-11-14 (`docs/research/data-sources.md`):** desde 2018 MODIS marca más focos como `type` 2
  (fuente fija), así que el filtro `type == 0` saca 3–4 puntos más que antes. La tabla de estabilidad se calcula
  con y sin el filtro de `type` para medir cuánto del escalón viene de ahí.

- **Primera corrida (2026-11-14, [reports/02/baselines.md](../reports/02/baselines.md)):** el factor de escala
  (SA2.2) le gana al ajuste de cuantiles (SA2.3) en los dos sentidos: WAPE bloque-mes con año afuera 17,2 % vs.
  19,4 % (VIIRS→MODIS) y 17,9 % vs. 19,4 % (MODIS→VIIRS); el control de origen móvil coincide. Factor nacional
  VIIRS→MODIS 0,302 (día 0,360, noche 0,147). Sin escalón claro en 2018 ni en 2023: el filtro de `type` mueve el
  cociente 2018 de 0,308 a 0,302. Abierto: (1) los intervalos de la serie inversa cubren 26 % (jackknife) y 54 %
  (dispersión interanual) contra un nominal de 80 %; hacen falta intervalos que incluyan el ruido del conteo
  antes de SA2.11; (2) en 2024–2025 el cociente Terra/Aqua cae (0,59 → 0,41) y la hora media de paso de Terra se
  adelanta (13:55 → 13:15 UTC de día) mientras S-NPP y NOAA-20 quedan fijos: compatible con deriva orbital de
  Terra, sin verificar la causa. La serie MODIS total (Terra + Aqua) no muestra escalón en esos años.

## Diseño de LightGBM (SA2.4 y SA2.7, decidido 2026-11-14 antes de correr, con consulta al asesor)

- **Unidad:** celda de 0,1° × mes × día/noche, solo filas con algún sensor activo; las predicciones se suman a
  bloque-mes para evaluar igual que SA2.2. Segundo candidato barato: LightGBM directo sobre bloque-mes, muy
  regularizado, para separar cuánto aporta la resolución y cuánto las variables. Celda-día descartada (horarios
  de paso distintos y poca coincidencia a 1 km). Medido en 2020: 52.316 filas activas; 17 % de las detecciones
  S-NPP caen en filas sin MODIS.
- **Base:** el baseline entra como offset, `init_score = log(f_bloque × fuente + ε)`, con la fuente suavizada en
  3×3 para las filas sin fuente. Con cero árboles el modelo reproduce SA2.2; se verifica que los totales por
  bloque coincidan con SA2.2 dentro de ~1 %. El factor usado en las filas de entrenamiento sale de un año afuera
  interno (fuera de muestra), nunca ajustado sobre esas mismas filas.
- **Variables:** conteos y FRP de la fuente por satélite y día/noche, FRP por detección, proporción día/noche,
  conteo de la fuente en 3×3, total de la fuente en el bloque, mes del año. Con y sin proporción Terra/Aqua
  (Terra cambia en 2024–2025 y Aqua no existe antes de 2002-07). Lat/lon solo en una ablación. Fuera: año,
  `version`, mes anterior. Toda variable de SA2.7 tiene que existir en 2000–2011 (solo MODIS). Sin cobertura del
  suelo (SA0.8 pendiente) ni ángulo de escaneo (no hay `scan`).
- **Hiperparámetros:** grilla chica elegida dentro de cada entrenamiento externo por WAPE bloque-mes con año
  afuera interno; pocos hilos, menos de 4 GB.
- **Intervalos:** el mismo esquema conformal anidado del baseline aplicado a la predicción puntual, para comparar
  cobertura y ancho con SA2.2. LightGBM por cuantiles solo como diagnóstico a nivel bloque-mes.
- **Criterio de publicación (fijado antes de la corrida), por sentido; LightGBM se publica solo si cumple todo:**
  WAPE bloque-mes con año afuera al menos 1 punto menor que SA2.2 y bloque-año no mayor; menor WAPE bloque-mes
  en al menos 10 de 14 años de test; mejora del mismo signo con origen móvil; |sesgo| total no peor que el de
  SA2.2 + 0,5 puntos y el peor año no peor; devianza de Poisson bloque-mes no peor; en SA2.7, cobertura
  80 ± 5 % y ancho no mayor; el intervalo bootstrap pareado (por año y bloque) de la diferencia de WAPE excluye
  cero. Si no, el informe dice "no supera al factor" y se publica SA2.2.

## Tareas

| ID | Tarea | Agente | Hecho cuando |
|---|---|---|---|
| SA2.1 | VIIRS reagrupado a celdas de 1 km por día (una detección por celda), pares de pasos similares (Aqua ~ S-NPP) | Sonnet | Unit: N detecciones en una celda cuentan como 1. Hecho ✅ (2026-11-14; en 2020, de 71.819 celdas-día de Aqua solo 29.937 tienen S-NPP en la misma celda de 0,01°: la coincidencia exacta a 1 km es baja y SA2.4/SA2.7 van a necesitar vecindad) |
| SA2.2 | Baseline: factor de escala MODIS/VIIRS por región y mes del año, en los dos sentidos | Sonnet | Unit con datos sintéticos de factor conocido. Hecho ✅ (2026-11-14; [reports/02/baselines.md](../reports/02/baselines.md)) |
| SA2.3 | Ajuste de cuantiles por región | Sonnet | Unit: recupera la distribución objetivo en sintético. Hecho ✅ (2026-11-14; pierde contra SA2.2 en los dos sentidos) |
| SA2.4 | LightGBM hacia MODIS: conteo MODIS-equivalente desde conteos VIIRS por confianza, FRP, día/noche, mes, latitud, cobertura del suelo | Sonnet implementa, opencode entrena | Error por año de test vs. SA2.2 y SA2.3 |
| SA2.5 | Validación año afuera con separación y selección anidada (`docs/validation.md`) | Sonnet | Unit: ningún día de test en entrenamiento. Hecho ✅ (2026-11-14; año afuera con separación y origen móvil) |
| SA2.6 | (postergado) Efecto de la deriva orbital de Terra y Aqua en los años recientes (sin verificar magnitud) | opencode | `reports/02/SA2.6.md` con cifras |
| SA2.7 | Serie inversa: LightGBM con objetivo Poisson o Tweedie que estima conteos VIIRS por celda y día desde conteo y FRP de MODIS, (sin ángulo de escaneo: el archivo standard no trae `scan`), día/noche, mes, cobertura del suelo y focos de días vecinos; intervalos por regresión cuantílica | Sonnet implementa, opencode entrena | Error y cobertura de intervalos por año de test vs. SA2.2 inverso |
| SA2.8 | (postergado) Validación hacia atrás: entrenar con 2016 en adelante y evaluar en 2012–2015, para simular estimar el pasado y ver si la relación cambia con el tiempo | Sonnet | Tabla de error por región y año; unit: ningún año de test en entrenamiento |
| SA2.9 | (postergado) Áreas quemadas MCD64A1 (2000–) como variable de SA2.7 para fuegos que MODIS no marcó como foco; Landsat solo si SA0.8 confirma acceso y cobertura | Sonnet escribe, opencode corre | Error de SA2.7 con y sin la variable |
| SA2.10 | (postergado) Continuidad post-MODIS: calibración congelada con versión y fecha; ingesta de un año VIIRS nuevo actualiza las dos series sin recalibrar | Sonnet | Unit: agregar un año no cambia los valores previos |
| SA2.11 | Serie final en dos escalas (MODIS-eq y VIIRS-eq) con banda de incertidumbre; manifiesto con método, versión de calibración, fuente y período | Sonnet | Capa publicada + e2e de carga |

## Entregable

Tabla de error por método, sentido y región, incluida la validación hacia atrás. Se publica el método que gane en
test; si LightGBM no supera al factor de escala, se informa así y se usa el factor. Tendencia observada
2000–hoy por región con su intervalo; ninguna proyección de décadas (requiere escenarios climáticos, fuera de
alcance).
