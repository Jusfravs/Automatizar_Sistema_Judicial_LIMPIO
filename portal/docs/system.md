# Sistema de diseño "Espoir institucional"

Referencia del portal de Gestión Judicial. La fuente de verdad de los valores es
`src/app/globals.css`; este documento explica cómo usarlos. Si cambias un token, actualiza aquí la
sección afectada y la tabla de contraste.

Principio rector: **un portal de justicia transmite seriedad, claridad y confianza**. El diseño es
sobrio. El color señala estado, no decora. El movimiento informa, nunca entretiene.

## 1. Tokens

Están organizados en tres capas. Las pantallas solo consumen las dos últimas.

| Capa | Prefijo | Uso |
|---|---|---|
| Primitivos | `--espoir-*` | Colores de marca. Nunca se usan directamente en componentes. |
| Semánticos | `--bg`, `--fg`, `--primary`, `--<tono>-*` | Cambian con el tema. Son los que consumen las pantallas. |
| Componente | `--control-*`, `--nav-*`, `--tabla-*` | Ajustes finos derivados de los semánticos. |

En Tailwind se exponen como `bg-surface`, `text-muted`, `border-strong`,
`bg-<tono>-soft`/`text-<tono>-fg`, `rounded-control|tarjeta|modal`, `shadow-tarjeta|elevada|overlay`.

**Barrera de color:** ESLint marca como error las clases de la paleta por defecto de Tailwind
(`bg-gray-100`…) y los hex dentro de `className`. Si necesitas un color nuevo, créalo como token.

### Tonos de estado
`neutral`, `info`, `progreso`, `exito`, `peligro`, `atencion`. Cada uno trae `soft` (fondo),
`fg` (texto), `border`, `solid` (relleno fuerte) y `on-solid`. Los mapas de dominio
(estado → tono) usan el tipo `Tono` de `src/lib/tonos.ts`.

- El ámbar (`--accent`) solo se usa como **relleno**, nunca como texto.
- El color nunca es la única señal. Va acompañado de texto, icono o peso.

## 2. Tipografía

| Rol | Familia | Uso |
|---|---|---|
| Interfaz | **Public Sans** (400–700) | Texto, controles y tablas. Es sobria, de lectura institucional (USWDS) y tiene cifras tabulares. |
| Títulos | **Source Serif 4** (variable con eje óptico) | `h1` de cada pantalla, la marca y los encabezados de login y errores. |
| Identificadores | **Geist Mono** | Números de causa, parámetros e IDs. |

### 2.1 Escala
| Clase | Tamaño / interlineado | Uso |
|---|---|---|
| `text-display` | 40px / 1.05, tracking −0.025em | Cifras protagonistas (KPI, % de un lote). |
| `text-titulo` | 28px / 1.2, tracking −0.012em | `h1` de pantalla (`PageHeader`). |
| `text-lg`, `text-base` | Escala de Tailwind | Títulos de modal y de tarjeta. |
| `text-sm` | 14px | Texto corrido, controles y celdas. Es el tamaño base de la interfaz. |
| `text-rotulo` | 11px, versalitas, +0.06em | Cabeceras de tabla y rótulos. |

### 2.2 Reglas
- Todas las cifras van con `tabular-nums` para que alineen en columnas y no "bailen" al cambiar.
- `text-balance` en títulos y `text-pretty` en descripciones.
- Usa como máximo dos pesos por bloque: `font-medium` para énfasis y `font-semibold` para títulos.

### 2.3 Títulos que son identificadores
Un título que es un número de causa o un ID va en **mono, no en serif**
(`PageHeader tituloMono`).

## 3. Movimiento

El movimiento comunica **continuidad** (es lo mismo y se movió), **llegada** (el dato acaba de
cargar) o **respuesta** (te oí). Si no comunica nada de eso, no se anima.

### 3.1 Tokens
| Token | Valor | Uso |
|---|---|---|
| `--duracion-rapida` | 120ms | Hover, press, salida de vistas. |
| `--duracion-base` | 180ms | Menús, popovers, salida de modales. |
| `--duracion-pagina` | 200ms | Fundido entre pantallas. |
| `--duracion-lenta` | 240ms | Entrada de modales y paneles, entradas de contenido. |
| `--duracion-movimiento` | 360ms | Elementos compartidos y el indicador de navegación. |
| `--escalon` | 40ms | Retraso entre los elementos de una entrada escalonada. |
| `--curva-salida` | `cubic-bezier(.23,1,.32,1)` | Entradas e interacción (`ease-salida`). |
| `--curva-movimiento` | `cubic-bezier(.77,0,.175,1)` | Desplazamientos en pantalla (`ease-movimiento`). |
| `--curva-muelle` | `linear(...)`, 1 % de rebote | Cosas que se "asientan" (`ease-muelle`). |

### 3.2 Recursos disponibles
- **Transición entre pantallas:** `<ViewTransition update="pagina">` en `AppShell`. La vista que
  sale se va en 120ms y la que entra aparece en 200ms. La barra lateral no se anima.
- **Entrada escalonada:** `.entrada-pagina` (en el shell) hace subir 6px las secciones de cada
  pantalla nueva, con 40ms entre cada una y un máximo de 6 escalones. `.entrada-escalonada` hace
  lo mismo con los hijos de cualquier lista. Solo corre al montar; un refresco no la repite.
- **Animaciones:** `animate-aparecer`, `animate-subir`, `animate-latido` (onda de estado vivo) y
  `animate-barrido` (carga indeterminada).
- **Modal** (`Dialog`): `.dialogo-animado` anima la entrada y también la salida, que es más corta.
- **Paneles con `hidden`:** `.panel-desplegable`.
- **Cifras:** `NumeroAnimado` cuenta del valor anterior al nuevo cuando cambia (máx. 600ms).
  Nunca cuenta desde cero en la carga.
- **Texto compartido entre pantallas:** clase de transición `texto-compartido`. Evita el escalado
  borroso del texto.
- **Botón `cargando`:** el spinner reemplaza la etiqueta sin cambiar el ancho del botón.

### 3.3 Reglas
- Anima solo `transform`/`translate`/`scale`, `opacity` y `clip-path`. Nunca `width`, `height`,
  `top` ni `left` (para progreso usa `scaleX`).
- Las salidas son más cortas que las entradas.
- No animes acciones de alta frecuencia (teclear, cada fila de una tabla al paginar).
- `prefers-reduced-motion`: `globals.css` anula animaciones, transiciones y View Transitions.
  Todo debe funcionar igual sin movimiento.

## 4. Controles
- El borde de los controles usa `--border-strong` (≥ 3:1). En hover pasa a tinta y el foco usa
  `--focus` con un anillo de 2px.
- **Deshabilitado sin bajar el contraste del texto:** se usa fondo `surface-2` y borde sutil; el
  texto queda en `muted`, que mantiene ≥ 4.5:1.
- Objetivos táctiles de al menos 32px de alto en escritorio (`sm`) y 36px por defecto.

## 5. Contraste (WCAG 2.2 AA, verificado)

| Par | Claro | Oscuro |
|---|---|---|
| fg / bg | 15.74:1 | 15.28:1 |
| muted / surface | 6.36:1 | 6.69:1 |
| muted / surface-2 | 5.65:1 | 5.90:1 |
| primary / surface | 9.18:1 | 7.31:1 |
| on-primary / primary | 9.18:1 | 8.24:1 |
| border-strong / surface (UI ≥ 3:1) | 3.51:1 | 3.23:1 |
| focus / surface-2 (UI ≥ 3:1) | 4.35:1 | (azul claro) |
| on-nav / nav | 9.18:1 | 11.59:1 |
| ámbar (relleno) / nav | 4.59:1 | — |
| info-fg / info-soft | 6.55:1 | 9.28:1 |
| progreso-fg / soft | 7.87:1 | 8.55:1 |
| exito-fg / soft | 6.35:1 | 9.04:1 |
| peligro-fg / soft | 6.50:1 | 9.00:1 |
| atencion-fg / soft | 7.28:1 | 9.72:1 |
| neutral-fg / soft | 8.30:1 | 9.21:1 |
