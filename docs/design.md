# Diseño

Fuente: canvas "Clima Ideas — Main page wireframe" (https://claude.ai/artifact/LPUfQ1KS8iZA9rkipwoi3Y),
artboard Mockup ("Mockup con datos de ejemplo"; los wireframes no son el objetivo). Reglas comunes con clima-ideas.

## Reglas de UI

- Sin etiquetas, badges ni descripciones secundarias: jerarquía, color y forma explican.
- Nunca blanco ni negro puros: claros con tono crema, oscuros con tono azul.
- Mismo layout en ambos temas: mismas regiones y mismas cajas; solo cambian los tokens.
- Acento reservado para lo que importa (mes actual, anomalía, selección).
- Solo lo que funciona: no se muestran navegación, filtros ni botones sin acción.
- Contraste mínimo WCAG AA.

## Layout

Barra superior (mínimo 56 px, `--surface`, con textura): título de la app, "NASA Space Apps 2026 · Desafío
CONAE", autor "Faustino Maggioni Duffy", selector de tema e idioma. Panel izquierdo: área, período, sensor.
Centro: mapa. Inspector derecho: cifras del área (filas etiqueta a la izquierda, valor mono a la derecha; fuente y
período siempre visibles). Franja inferior: calendario año×mes y anomalías. Mismo layout en ambos temas.

Pestañas Mapa / Dashboard en el centro. Dashboard: grilla de gráficos del área (serie mensual, totales por año,
estacionalidad, anomalía, día/noche y FRP, fase ENSO); pasar el cursor por un mes lo resalta en todos los
gráficos y en el calendario.

## Superficies

- Sin bordes entre regiones. Fondo de página `--bg`, con 8 px de relleno y 8 px entre regiones.
- Cada panel es una tarjeta `--surface` con radio 8 px y relleno 16 px.
- Textura (clase `.tx`): en claro, puntos `radial-gradient(rgba(42,52,59,.09) .9px, transparent 1.3px)` a
  5 × 5 px más un brillo diagonal `linear-gradient(135deg, rgba(255,255,255,.45) 0%, transparent 55%)`; en
  oscuro, ninguno.

## Tokens

Los valores viven en `web/src/theme/tokens.css` y `tokens.ts`; un test verifica que coincidan.

| Token | Claro | Oscuro | Uso |
|---|---|---|---|
| `--bg` | `#F1EEE6` | `#16212A` | Fondo de página |
| `--surface` | `#F9F7F2` | `#1F2D37` | Tarjetas y barra superior |
| `--raised` | `#EFECE4` | `#2A3A46` | Botones neutros, fila seleccionada |
| `--border` | `#DDD8CD` | `#3E505B` | Trazos finos dentro de gráficos |
| `--text` | `#2A343B` | `#ECE7DC` | Texto |
| `--muted` | `#5F6468` | `#A3AEB4` | Texto secundario |
| `--ctrl` | `#3E505B` | `#4D6372` | Control primario |
| `--onctrl` | `#F5F2EA` | `#ECE7DC` | Texto sobre `--ctrl` |
| `--accent` | `#8EB8E5` | `#FDDA0D` | Mes actual, anomalía, selección, foco |
| `--secondary` | `#A4AF69` | `#A4AF69` | Banda "normal", climatología |
| `--casing` | `#2A343B` | `#16212A` | Contorno de las marcas de acento |

Espaciado `--space-1..6` (4, 8, 12, 16, 24, 32 px); radios 4, 8, 12 px.

## Tipografía

IBM Plex Sans 400/500/600 para el cuerpo y los títulos (14 px / 1,4; títulos de tarjeta 14 px / 600, de página
16 px / 600); IBM Plex Mono 400/500 con numerales tabulares solo para números, fechas y unidades (clase `.num`).
Google Fonts en `index.html`.

## Controles

- Objetivos de 44 px, radio 8 px, sin borde. Neutros sobre `--raised`; primario sobre `--ctrl` con `--onctrl`.
- Foco visible: anillo de 2 px en `--accent` con 2 px de separación.
- Las marcas de acento en mapa y gráficos llevan contorno `--casing`.

## Pantallas angostas

Hasta 800 px el panel izquierdo es un cajón y las tarjetas se apilan debajo del mapa; la página se desplaza.
Margen lateral de 16 px y sin desplazamiento horizontal.

## Rampas

- Calendario (conteo): secuencial de un solo tono que crece en luminosidad, validada para daltonismo
  (se define en SA0.4).
- Anomalía: divergente azul (menos que la mediana) / naranja (más), centro neutro `--raised`.
- `--secondary` marca la banda "normal" (p25–p75).
- Fase ENSO: Niña azul, Niño naranja, Neutro `--raised`; tonos apagados para que no compitan con el calendario.
