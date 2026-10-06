/**
 * Tonos semánticos del sistema de diseño.
 * Cada tono existe en globals.css como bg-<tono>-soft, text-<tono>-fg, border-<tono>-border,
 * bg-<tono>-solid y text-<tono>-on-solid. Los mapas de dominio (estado → tono) usan este tipo.
 */
export const TONOS = ['neutral', 'info', 'progreso', 'exito', 'peligro', 'atencion'] as const

export type Tono = (typeof TONOS)[number]
