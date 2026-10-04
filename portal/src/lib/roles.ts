export function inicioPorRol(rol: string | null | undefined): string {
  switch (rol) {
    case 'gestor_lotes':
      return '/lotes'
    case 'gestor_casos':
      return '/casos'
    case 'admin':
      return '/lotes'
    default:
      return '/sin-acceso'
  }
}

export const ROLES_LOTES = ['gestor_lotes', 'admin']
export const ROLES_CASOS = ['gestor_casos', 'admin']