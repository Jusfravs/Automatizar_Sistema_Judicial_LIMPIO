import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

/*
 * Barrera de colores sueltos.
 * Detecta clases de la paleta por defecto de Tailwind (bg-gray-100, hover:text-blue-600…)
 * en cualquier cadena o plantilla, y hex dentro de className.
 * Exige el sufijo numérico: los tonos semánticos (bg-neutral-soft, text-neutral-fg) no disparan.
 */
const PREFIJOS =
  "bg|text|border|ring|from|to|via|divide|outline|fill|stroke|placeholder|decoration|shadow|accent|caret";
const PALETA =
  "slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose";
// Inicio de cadena, espacio, ":" (variantes como hover:) o "!" (important); luego -(x|y|t|r|b|l|s|e)? para border-t-gray-200.
// Sin "/" en el patrón: esquery corta la regex en la primera barra. bg-gray-100/50 cae igual por el lookahead.
const CLASE_PALETA = `(^|[\\s:!])(${PREFIJOS})(-[xytrblse])?-(${PALETA})-\\d{2,3}(?![\\w-])`;
const HEX = "#[0-9a-fA-F]{3,8}(?![\\w-])";
const MENSAJE = "Usa los tokens de globals.css o los componentes de src/components/ui, no colores sueltos.";

const reglaColores = (severidad) => [
  severidad,
  { selector: `Literal[value=/${CLASE_PALETA}/]`, message: MENSAJE },
  { selector: `TemplateElement[value.raw=/${CLASE_PALETA}/]`, message: MENSAJE },
  { selector: `JSXAttribute[name.name='className'] Literal[value=/${HEX}/]`, message: MENSAJE },
  { selector: `JSXAttribute[name.name='className'] TemplateElement[value.raw=/${HEX}/]`, message: MENSAJE },
];

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Pantallas heredadas: aviso mientras dura la migración. Pasa a "error" al cerrar V5.
  {
    files: ["src/app/**/*.{ts,tsx}"],
    rules: { "no-restricted-syntax": reglaColores("warn") },
  },
  // Código nuevo del sistema: ya está limpio, así que la barrera es dura desde ahora.
  {
    files: ["src/components/**/*.{ts,tsx}", "src/lib/**/*.{ts,tsx}"],
    rules: { "no-restricted-syntax": reglaColores("error") },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
