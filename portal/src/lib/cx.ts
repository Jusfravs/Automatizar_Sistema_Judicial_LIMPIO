export type ClaseOpcional = string | false | null | undefined

/**
 * Une clases de Tailwind ignorando los valores falsos.
 * No resuelve conflictos (no es tailwind-merge): si una clase de `className`
 * choca con una interna del componente, gana la que Tailwind emita después.
 * Para variantes, usa las props del componente en vez de pisar clases.
 */
export function cx(...clases: ClaseOpcional[]): string {
  return clases.filter(Boolean).join(' ')
}
