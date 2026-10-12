import { clsx, type ClassValue } from 'clsx'
import { extendTailwindMerge } from 'tailwind-merge'

/**
 * `cn` para componentes de registros shadcn (motion-primitives, Bklit, Skiper UI): une clases y
 * resuelve conflictos de Tailwind. Se le enseñan los tamaños de texto propios del sistema
 * (text-titulo, text-display, text-rotulo) para que no los confunda con colores (text-fg…).
 * El código propio del portal sigue usando `cx` (src/lib/cx.ts), que no resuelve conflictos.
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      'font-size': [{ text: ['titulo', 'display', 'rotulo'] }],
    },
  },
})

export function cn(...entradas: ClassValue[]) {
  return twMerge(clsx(entradas))
}
