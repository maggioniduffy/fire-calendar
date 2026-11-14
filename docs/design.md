# Diseño

Fuente: canvas "Clima Ideas — Main page wireframe" (https://claude.ai/artifact/LPUfQ1KS8iZA9rkipwoi3Y),
artboards "Mockup con datos de ejemplo" (`project/Mockup.dc.html`); los wireframes no son el objetivo. Reglas
comunes con clima-ideas.

## Reglas de UI

- Sin etiquetas, badges ni descripciones secundarias: jerarquía, color y forma explican.
- Nunca blanco ni negro puros: claros con tono crema, oscuros con tono azul.
- Mismo layout en ambos temas: mismas regiones y mismas cajas; solo cambian los tokens.
- Acento reservado para lo que importa (mes actual, anomalía, selección).
- Solo lo que funciona: no se muestran navegación, filtros ni botones sin acción; lo que todavía no está conectado
  queda oculto.
- Contraste mínimo WCAG AA.

## Layout

### Barra superior

Mínimo 56 px, `--surface` con textura. De izquierda a derecha: marca del logo de 28 px (cuadrado redondeado
`--ctrl` con una línea `--on-ctrl` y una línea base `--accent`); nombre de la app; `h1` con el área elegida
("Córdoba"); "NASA Space Apps 2026 · Desafío CONAE" y el autor "Faustino Maggioni Duffy". A la derecha: nota de
datos en mono 12 px `--text-muted` ("FIRMS hasta <fecha>"), selector de idioma y botón de tema de 44 px. Sin
navegación de secciones.

### Panel izquierdo

`aside` de 240 px, una tarjeta:

- **Capas:** casillas de 18 px en filas de 40 px: focos MODIS, focos VIIRS, área seleccionada, localidades.
- **Serie:** control segmentado (Reportada / MODIS-eq / VIIRS-eq) dentro de un contenedor `--raised` con radio
  10 px; botón activo `--ctrl`.
- **Fase ENSO:** control segmentado de 2×2 (Todas / El Niño / La Niña / Neutro) que filtra los meses activos.
- **Período:** dos botones mono de 44 px (2000, 2026).
- Al pie, fijada abajo, una línea de fuentes en 12 px `--text-muted`: "FIRMS MODIS C6.1 y VIIRS 375 m, NASA
  LANCE; ONI NOAA CPC".

### Columna principal

- **Mapa:** tarjeta con flex 1 y mínimo 400 px de alto; mapa base monocromo con el relieve pizarra
  (`--relief-0..3`) y `--water`; focos como marcas `--accent` con contorno `--casing`. Arriba a la derecha, una
  tarjeta superpuesta con el mes elegido en mono 20 px y debajo una línea en 12 px `--text-muted` ("N focos en el
  área"). Abajo a la izquierda, la leyenda, sin borde.
- **Fila de tarjetas** bajo el mapa:
  - **Inspector** (`1 1 300px`): `h2` "Área · mes", rango de fechas en `--text-muted`, y filas de 28 px con la
    etiqueta a la izquierda y el valor mono a la derecha: focos del mes, mediana del mes, anomalía (percentil),
    mes más activo, fase ENSO · ONI, fuente, período del dato. Al pie, un botón primario `--ctrl`.
  - **Calendario** (`1.6 1 420px`): una oración con el hallazgo principal arriba; el heatmap año×mes; y el gráfico
    de la serie contra la climatología: barras en `--text`, banda p25–p75 en `--secondary` con opacidad 0,55 y
    los meses sobre p90 en `--accent` con contorno `--casing`.
  - **Meses más activos** (`1 1 300px`): el conteo en mono `--text-muted` en el título; filas de 48 px con punto,
    mes y lugar, conteo y fecha en mono; la fila elegida sobre `--raised` con el punto en `--accent`.
- **Línea de tiempo** abajo: botones anterior / reproducir / siguiente de 44 px (reproducir sobre `--ctrl`); pista
  2000–2026 con una banda de fase ENSO por año (Niño `--ctrl`, Niña `--border`, Neutro `--bg`), marcas `--accent`
  en los meses más activos y cabezal `--accent` de 5 px. Reproducir avanza mes a mes por el mapa y el inspector.
  Leyenda de Niño / Niña / Neutro.

Sin pestañas Mapa / Dashboard.

## Superficies

- Sin bordes entre regiones. Fondo de página `--bg`, con 8 px de relleno y 8 px entre regiones.
- Cada panel es una tarjeta `--surface` con radio 8 px y relleno 16 px.
- Textura (clase `.tx`): en claro, puntos `radial-gradient(rgba(42,52,59,.09) .9px, transparent 1.3px)` a
  5 × 5 px más un brillo diagonal `linear-gradient(135deg, rgba(255,255,255,.45) 0%, transparent 55%)`; en
  oscuro, ninguno.

## Tokens

Los valores viven en `web/src/theme/tokens.css` y `tokens.ts`; un test verifica que coincidan. Los nombres son los
de clima-ideas.

| Token | Claro | Oscuro | Uso |
|---|---|---|---|
| `--bg` | `#F1EEE6` | `#16212A` | Fondo de página |
| `--surface` | `#F9F7F2` | `#1F2D37` | Tarjetas y barra superior |
| `--raised` | `#EFECE4` | `#2A3A46` | Botones neutros, fila seleccionada |
| `--border` | `#DDD8CD` | `#3E505B` | Trazos finos dentro de gráficos |
| `--text` | `#2A343B` | `#ECE7DC` | Texto |
| `--text-muted` | `#5F6468` | `#A3AEB4` | Texto secundario |
| `--ctrl` | `#3E505B` | `#4D6372` | Control primario |
| `--on-ctrl` | `#F5F2EA` | `#ECE7DC` | Texto sobre `--ctrl` |
| `--accent` | `#8EB8E5` | `#FDDA0D` | Mes actual, anomalía, selección, foco |
| `--secondary` | `#A4AF69` | `#A4AF69` | Banda "normal", climatología |
| `--casing` | `#2A343B` | `#16212A` | Contorno de las marcas de acento |
| `--water` | `#3A6E8F` | `#7FA9C6` | Ríos y lagos en el mapa base |
| `--relief-0` | `#A7AEAF` | `#4E5F6A` | Relieve, bajo |
| `--relief-1` | `#77848A` | `#7D8D96` | Relieve, medio |
| `--relief-2` | `#4A5A64` | `#B3BEC4` | Relieve, alto |
| `--relief-3` | `#2A343B` | `#ECE7DC` | Relieve, cumbres |

Espaciado `--space-1..6` (4, 8, 12, 16, 24, 32 px); radios 4, 8, 12 px.

## Tipografía

IBM Plex Sans 400/500/600 para el cuerpo y los títulos (14 px / 1,4; títulos de tarjeta 14 px / 600, de página
16 px / 600); IBM Plex Mono 400/500 con numerales tabulares solo para números, fechas y unidades (clase `.num`).
Google Fonts en `index.html`.

## Controles

- Objetivos de 44 px, radio 8 px, sin borde. Neutros sobre `--raised`; primario sobre `--ctrl` con `--on-ctrl`.
- Casillas de 18 px con `accent-color: var(--ctrl)`; filas de 40 px.
- Controles segmentados: contenedor `--raised` con radio 10 px, botón activo `--ctrl` con texto `--on-ctrl`.
- Foco visible: anillo de 2 px en `--accent` con 2 px de separación.
- Las marcas de acento en mapa y gráficos llevan contorno `--casing`.

## Tiradores de arrastre

- Hay tiradores para el ancho del panel izquierdo, el alto de la fila de tarjetas y el alto de la línea de tiempo,
  ubicados en los huecos de 8 px entre regiones.
- Arrastrar por debajo del mínimo del panel lo colapsa a 0: el panel queda oculto (`hidden`, fuera del orden de
  tabulación) y el mapa ocupa el espacio. El tirador permanece en el borde para poder arrastrarlo de vuelta.
- Teclado: las flechas redimensionan (16 px), Inicio colapsa, Fin maximiza, Enter o doble clic restablece el
  tamaño por defecto. `aria-valuemin` es 0 y `aria-valuenow` es 0 cuando está colapsado. El mapa conserva al menos
  320 × 200 px.
- Tamaños y estado colapsado se guardan en `localStorage` (`panel-sizes`); las claves inválidas o ausentes vuelven
  al defecto.

## Pantallas angostas

En pantallas de hasta 800 px el panel izquierdo es un cajón. Las tarjetas se apilan debajo del mapa y la página se
desplaza; no hay tiradores. Margen lateral de 16 px y sin desplazamiento horizontal.

## Rampas

- Calendario (conteo): secuencial de un solo tono que crece en luminosidad, validada para daltonismo
  (se define en SA0.4).
- Anomalía: divergente azul (menos que la mediana) / naranja (más), centro neutro `--raised`.
- `--secondary` marca la banda "normal" (p25–p75).
- Fase ENSO (como en la línea de tiempo del mockup): Niño `--ctrl`, Niña `--border`, Neutro `--bg`.
