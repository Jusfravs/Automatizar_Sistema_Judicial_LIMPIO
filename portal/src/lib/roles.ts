export function inicioPorRol(rol: string | null | undefined): string {
  if (rol === 'admin' || rol === 'usuario') {
    return '/lotes'
  }
  return '/sin-acceso'
}

export const ROLES_PORTAL = ['admin', 'usuario'] as const

export function rolEtiqueta(rol: string): string {
  switch (rol) {
    case 'admin':
      return 'Administrador'
    case 'usuario':
      return 'Usuario'
    default:
      return rol
  }
}

export function esRolValido(rol: string): rol is (typeof ROLES_PORTAL)[number] {
  return ROLES_PORTAL.includes(rol as (typeof ROLES_PORTAL)[number])
}