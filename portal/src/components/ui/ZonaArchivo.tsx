'use client'

import { useRef, useState, type DragEvent } from 'react'
import { cx } from '@/lib/cx'
import { FOCO } from './estilos'

export type ZonaArchivoProps = {
  /** id del <input type="file"> real; enlázalo con Field/label como cualquier control. */
  id: string
  archivo: File | null
  /** Se llama al elegir o soltar un archivo (o con null si se suelta algo vacío). */
  alCambiar: (archivo: File | null) => void
  accept?: string
  required?: boolean
  disabled?: boolean
  'aria-invalid'?: boolean | undefined
  'aria-describedby'?: string | undefined
  /** Texto de ayuda visible dentro de la zona. Ej.: "Solo .xlsx, máximo 20 MB". */
  indicacion?: string
}

function formatearTamano(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(2)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`
}

/**
 * Zona de arrastre sobre un <input type="file"> real: el input sigue siendo el control
 * (teclado, lectores de pantalla, `required`), la zona solo amplía el área de soltar.
 */
export function ZonaArchivo({
  id,
  archivo,
  alCambiar,
  accept,
  required,
  disabled,
  indicacion,
  ...aria
}: ZonaArchivoProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [encima, setEncima] = useState(false)

  function alSoltar(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault()
    setEncima(false)
    if (disabled) return
    const lista = e.dataTransfer.files
    // Se copia al input para que el formulario y `required` vean el mismo archivo.
    if (inputRef.current && lista.length > 0) inputRef.current.files = lista
    alCambiar(lista[0] ?? null)
  }

  return (
    <label
      htmlFor={id}
      onDragOver={(e) => {
        e.preventDefault()
        if (!disabled) setEncima(true)
      }}
      onDragLeave={() => setEncima(false)}
      onDrop={alSoltar}
      className={cx(
        'flex cursor-pointer flex-col items-center gap-1 rounded-tarjeta border-2 border-dashed px-6 py-8 text-center transition-colors',
        'has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-focus',
        encima ? 'border-primary bg-surface-2' : 'border-strong bg-surface hover:bg-surface-2',
        aria['aria-invalid'] && 'border-peligro-solid',
        disabled && 'cursor-not-allowed opacity-70',
      )}
    >
      <input
        ref={inputRef}
        id={id}
        type="file"
        accept={accept}
        required={required}
        disabled={disabled}
        onChange={(e) => alCambiar(e.target.files?.[0] ?? null)}
        className={cx('sr-only', FOCO)}
        {...aria}
      />
      {archivo ? (
        <>
          <span className="max-w-full truncate text-sm font-semibold text-fg">{archivo.name}</span>
          <span className="text-xs tabular-nums text-muted">
            {formatearTamano(archivo.size)} · <span className="font-medium text-primary underline">Cambiar archivo</span>
          </span>
        </>
      ) : (
        <>
          <span className="text-sm font-semibold text-fg">
            Arrastra el Excel aquí o <span className="text-primary underline">elige un archivo</span>
          </span>
          {indicacion ? <span className="text-xs text-muted">{indicacion}</span> : null}
        </>
      )}
    </label>
  )
}
