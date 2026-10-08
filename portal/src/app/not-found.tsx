import { PantallaEstado } from '@/components/PantallaEstado'
import { ButtonLink } from '@/components/ui/ButtonLink'
import { IconoBrujula } from '@/components/ui/iconos'

export default function PaginaNoEncontrada() {
  return (
    <PantallaEstado
      Icono={IconoBrujula}
      codigo="Error 404"
      titulo="Esta página no existe"
      acciones={<ButtonLink href="/">Ir al portal</ButtonLink>}
    >
      <p>Puede que el enlace esté mal escrito o que la página se haya movido.</p>
    </PantallaEstado>
  )
}
