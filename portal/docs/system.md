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
cargar) o **respuesta** (te oí). Si no comunica nada de eso, no se anima. Un portal de trabajo se
usa cientos de veces al día: lo frecuente se siente inmediato, lo excepcional se anima.

### 3.1 Tokens
| Token | Valor | Uso |
|---|---|---|
| `--duracion-rapida` | 120ms | Hover, press, salida de vistas. |
| `--duracion-base` | 180ms | Menús, popovers, salida de modales. |
| `--duracion-pagina` | 200ms | Fundido entre pantallas. |
| `--duracion-lenta` | 240ms | Entrada de modales y paneles, elementos compartidos, indicador de navegación. |
| `--escalon` | 40ms | Retraso entre los elementos de una entrada escalonada. |
| `--curva-salida` | `cubic-bezier(.23,1,.32,1)` | Entradas, interacción y elementos compartidos (`ease-salida`). |
| `--curva-movimiento` | `cubic-bezier(.77,0,.175,1)` | Desplazamientos largos en pantalla (`ease-movimiento`). |

### 3.2 Recursos disponibles
- **Transición entre pantallas:** `<ViewTransition update={{ navegacion: 'pagina', default: 'none' }}>`
  en `AppShell`. **Solo anima las navegaciones etiquetadas** con `NAVEGACION` (`src/lib/transiciones.ts`):
  `<Link transitionTypes={NAVEGACION}>` o `router.push(url, { transitionTypes: NAVEGACION })`.
  Refrescos, filtros, orden, paginación y la carga tras el esqueleto son silenciosos. La vista que
  sale se va en 120ms y la nueva aparece en 200ms. La barra lateral ni se pinta ni bloquea clics.
- **Navegación jerárquica:** `ADELANTE` (fila de una lista → su detalle) y `ATRAS` (migas de pan)
  hacen entrar la vista nueva 16px desde el lado al que se avanza, con fundido, en 240ms; la vieja
  solo se desvanece. Con movimiento reducido quedan en el fundido.
- **Cambio de tema** (`ThemeToggle`): View Transition con tipo `tema`; la vista nueva se revela con
  un `clip-path: circle()` que crece desde el clic en 400ms (excepción a la escala de duraciones:
  cambio poco frecuente y de pantalla completa). Con teclado (flechas del grupo de radios), sin View
  Transitions o con movimiento reducido, el cambio es inmediato.
- **Elementos compartidos** (sin tipo, también con Atrás): el resaltado de la navegación se desliza
  (`indicador`) y el número de causa viaja de la lista al detalle (`texto-compartido`, en
  `NumeroCausaCompartido`). Un nombre de transición solo puede estar montado una vez.
- **Entrada escalonada** `.entrada-escalonada`: solo en vistas que se ven una vez por sesión (login).
  Nunca en navegación repetida ni en listas que se paginan.
- **Componentes de movimiento adoptados** (sección 6): paso del asistente con dirección
  (`TransitionPanel`, 240ms entrada / 160ms salida), fondo deslizante de los filtros de /lotes
  (`AnimatedBackground`, resorte sin rebote; salta si se activó con teclado), brillo en "Cargando…" y
  "Buscando…" (`TextoCargando`; en los esqueletos aparece tras 400ms para no parpadear en cargas
  rápidas), barra de lectura en el detalle de causa (`ProgresoLectura`), trazo en el borde de "Lotes
  en curso" (`TrazoEnCurso`: tres vueltas de 8s y se retira; solo con un lote EN_CURSO y el servidor
  procesando) y subrayado que crece en las migas con hover o foco (`EnlaceSubrayado`, de Skiper UI).
- **Animaciones:** `animate-aparecer`, `animate-subir`, `animate-latido` (una onda por latido real,
  reiniciada con `key`) y `animate-barrido` (carga indeterminada, pausada cuando no se usa).
- **Modal** (`Dialog`): `.dialogo-animado` anima la entrada y la salida (más corta; requiere `overlay`).
  Las paletas que se abren por teclado (Ctrl+K) usan `animado={false}`.
- **Paneles con `hidden`:** `.panel-desplegable`.
- **Cifras:** `NumeroAnimado` cuenta desde la cifra visible hasta la nueva (máx. 400ms; se puede
  interrumpir). Nunca cuenta desde cero en la carga.
- **Avisos que aparecen después de cargar:** `.despliegue` (con `useHidratado` para no animar los
  que ya estaban).
- **Botón `cargando`:** el spinner reemplaza la etiqueta sin cambiar el ancho; usa `aria-disabled`
  para que el foco no salga expulsado.

### 3.3 Reglas
- Anima solo `transform`/`translate`/`scale`, `opacity` y `clip-path`. Para progreso usa `scaleX`.
  **Excepción documentada:** `height` con `interpolate-size` en despliegues (`.despliegue`) y en
  "Ver más" (`.texto-plegable`), a 240ms, nunca en listas.
  **Excepción documentada:** el brillo de `TextoCargando` anima `background-position` en bucle; solo
  existe mientras algo carga, sobre texto corto, y desaparece con movimiento reducido.
  **Excepción documentada:** el trazo de `TrazoEnCurso` anima `offset-distance` (tres vueltas y se
  retira); no se muestra con movimiento reducido.
  **Excepción documentada:** las barras de Bklit crecen animando el tamaño del rect (400ms, una sola
  vez al entrar en pantalla); con movimiento reducido no crecen.
- Las salidas son más cortas que las entradas. Un clic no tiene impulso: sin rebotes.
- **No animes lo que dispara el teclado ni lo de alta frecuencia:** escribir, moverse con flechas,
  atajos (1–4, Ctrl+K), cada fila al paginar, refrescos de fondo.
- `prefers-reduced-motion`: se conserva el fundido (opacidad) y se quita todo desplazamiento;
  los elementos compartidos saltan a su sitio, sin retrasos ni ondas. Todo funciona igual sin
  movimiento.

### 3.4 Atajos de teclado (WCAG 2.1.4)
- Globales solo con modificador: **Ctrl/⌘+K** (buscar causa), **Ctrl+Enter** (guardar revisión).
- Teclas sueltas (**1–4** en la revisión) solo con el foco dentro de su formulario y fuera de
  campos de texto.

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
| on-nav/85 / nav (menú) | 7.10:1 | 8.78:1 |
| on-nav/80 / botón de búsqueda | 5.82:1 | 7.12:1 |
| on-nav/70 / nav (kbd, pie del login) | 4.86:1 | 5.85:1 |
| info-fg / info-soft | 6.55:1 | 9.28:1 |
| progreso-fg / soft | 7.87:1 | 8.55:1 |
| exito-fg / soft | 6.35:1 | 9.04:1 |
| peligro-fg / soft | 6.50:1 | 9.00:1 |
| atencion-fg / soft | 7.28:1 | 9.72:1 |
| neutral-fg / soft | 8.30:1 | 9.21:1 |

## 6. Componentes de registros (shadcn, motion-primitives, Bklit, Skiper UI)

Se instalan con la CLI de shadcn y la configuración de `components.json`:

```bash
npx shadcn@latest add @motion-primitives/<nombre>   # https://motion-primitives.com/c/{name}.json
npx shadcn@latest add @bklit/<nombre>               # gráficos — https://ui.bklit.com/r/{name}.json
npx shadcn@latest add @skiper-ui/<nombre>           # https://skiper-ui.com/r/{name}.json
```

- **Puente de colores** (`globals.css`, sección 3b): `background`, `foreground`, `card`, `popover`, `border`, `ring`, `chart-1…5` y el resto apuntan a tokens Espoir. Los componentes heredan identidad y tema sin editarlos.
- **No puenteados:** `muted` y `accent`, porque Espoir los usa con otro significado. Al adoptar un componente, cambiar `bg-muted` y `bg-accent` por `bg-surface-2`.
- **`dark:`** sigue el tema del portal (`data-theme` o la preferencia del sistema), no la clase `.dark`.
- **`cn`** (`lib/utils.ts`) usa clsx y tailwind-merge, y conoce `text-titulo`, `text-display` y `text-rotulo`. El código propio sigue usando `cx`.
- **No ejecutar `shadcn init` de nuevo.** En Windows sobrescribe `components/ui/Button.tsx` (mismo nombre que `button.tsx` sin distinguir mayúsculas), cambia la fuente a Geist y mezcla sus colores. Restaurar desde `proyectos/coordinacion/respaldos` si ocurre.
- **Instalados y adaptados:** motion-primitives en `src/components/registro/motion/` (colores
  Espoir, `motion/react`, sin efectos con setState); Bklit en `src/components/charts/` (su estructura
  original: con `-p` se rompen sus importaciones relativas). Su CSS no se usa: las variables
  `--chart-*` y los colores del tooltip salen del puente. Cifras y fechas en `es-EC`. ESLint relaja
  solo reglas de hooks y TypeScript en esas carpetas; la barrera de color sigue activa.
- **Al reinstalar** un componente con `shadcn add`, revisar `git status`: Bklit sobrescribe
  `lib/utils.ts` (restaurar el `cn` extendido) y trae CSS propio que no se usa.
- **Gráficos** (`inicio/PanoramaCartera.tsx`): una sola serie y un solo tono (`--chart-1`), cifras
  junto a las barras en tinta (nunca del color de la serie), tooltip en español sin rebote, y los
  datos en una tabla desplegable "Ver datos" (el contenedor del gráfico es `aria-hidden`: Bklit pinta
  ejes y tooltip fuera del SVG). Se montan al entrar en pantalla. Las barras horizontales
  sirven para categorías de nombre largo. En Bklit, una capa propia no debe tener prop `dataKey`:
  la cuenta como serie y estrecha las barras. Datos: vistas `v_resumen_etapas_actuales` y
  `v_actividad_diaria` (migraciones 009 y 010; solo cuenta consultas con resultado).
- **Cada componente que se adopte** pasa por la revisión de movimiento (sección 3) y de accesibilidad antes de usarse en una pantalla. Licencia de Skiper UI gratuita: exige atribución, que va en el archivo.
