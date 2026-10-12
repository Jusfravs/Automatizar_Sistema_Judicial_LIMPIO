/**
 * Puente para componentes de registros shadcn (p. ej. Skiper UI), que importan `cn` de aquí.
 * Reutiliza `cx` del sistema: une clases sin resolver conflictos (no es tailwind-merge).
 */
export { cx as cn } from '@/lib/cx'
