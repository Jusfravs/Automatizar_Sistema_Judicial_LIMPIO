'use client'

import { useMemo, useRef } from 'react'
import { useInView, useReducedMotion } from 'motion/react'
import { BarChart } from '@/components/charts/bar-chart'
import { Bar } from '@/components/charts/bar'
import { BarXAxis } from '@/components/charts/bar-x-axis'
import { BarYAxis } from '@/components/charts/bar-y-axis'
import { useChart } from '@/components/charts/chart-context'
import { intFmt } from '@/components/charts/chart-formatters'
import { Grid } from '@/components/charts/grid'
import { ChartTooltip, TooltipContent } from '@/components/charts/tooltip'
import { Card, CardBody, CardHeader } from '@/components/ui'
import { FOCO } from '@/components/ui/estilos'
import { cx } from '@/lib/cx'

/** `orden` 1–6 es el número procesal; ≥ 100, una etapa del catálogo sin número (va al final, sin prefijo). */
export type EtapaResumen = { orden: number; corta: string; nombre: string; causas: number }
export type DiaActividad = { dia: string; causas: number }

const COLOR = 'var(--chart-1)'
// Las barras crecen una sola vez, al entrar en pantalla (dato que llega), y en poco tiempo: Inicio
// se visita muchas veces al día. Curva de salida del sistema, sin arranque lento.
const DURACION_MS = 400
const ENTRADA = { type: 'tween', duration: DURACION_MS / 1000, ease: [0.23, 1, 0.32, 1] } as const

const fechaLarga = new Intl.DateTimeFormat('es-EC', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' })
const fechaCorta = new Intl.DateTimeFormat('es-EC', { day: 'numeric', month: 'short', timeZone: 'UTC' })

/**
 * Cifras junto a las barras (etiquetado directo): sin eje de valores, cada barra lleva su número.
 * Si dos etiquetas no caben, se conserva la mayor; el valor exacto de todas sigue en el tooltip y en
 * la tabla para lectores de pantalla. Texto en tinta atenuada, nunca del color de la serie.
 */
// La prop no se llama `dataKey`: Bklit cuenta como serie a todo hijo con `dataKey` y estrecharía las barras.
function EtiquetasValor({ clave }: { clave: string }) {
  // Aparecen cuando las barras terminan de crecer (isLoaded), no antes.
  const { data, barScale, bandWidth, barXAccessor, yScale, orientation, isLoaded } = useChart()
  if (!barScale || !bandWidth || !barXAccessor) return null
  const horizontal = orientation === 'horizontal'

  const candidatas = data.flatMap((d, i) => {
    const valor = d[clave]
    if (typeof valor !== 'number' || valor <= 0) return []
    const centro = (barScale(barXAccessor(d)) ?? 0) + bandWidth / 2
    const fin = yScale(valor) ?? 0
    return [{ i, valor, texto: intFmt(valor), centro, fin }]
  })

  // En columnas, las etiquetas comparten fila: se descartan las que pisarían a una mayor.
  const visibles = horizontal
    ? candidatas
    : [...candidatas]
        .sort((a, b) => b.valor - a.valor)
        .reduce<typeof candidatas>((aceptadas, c) => {
          const ancho = c.texto.length * 6.5 + 6
          const choca = aceptadas.some((a) => Math.abs(a.centro - c.centro) < (ancho + a.texto.length * 6.5 + 6) / 2)
          return choca ? aceptadas : [...aceptadas, c]
        }, [])

  return (
    <g
      className="fill-fg text-xs font-medium tabular-nums transition-opacity duration-(--duracion-lenta) ease-salida"
      style={{ opacity: isLoaded ? 1 : 0 }}
    >
      {visibles.map((c) =>
        horizontal ? (
          // El margen derecho del gráfico reserva el espacio de la cifra tras la barra más larga.
          <text key={c.i} x={c.fin + 6} y={c.centro} dominantBaseline="central">
            {c.texto}
          </text>
        ) : (
          <text key={c.i} x={c.centro} y={c.fin - 6} textAnchor="middle">
            {c.texto}
          </text>
        ),
      )}
    </g>
  )
}

/**
 * Datos del gráfico en una tabla desplegable. El gráfico es aria-hidden: esta es la vía para lectores
 * de pantalla y para quien usa teclado (los tooltips solo responden al puntero) o necesita el valor
 * exacto de una cifra que no cupo en el gráfico.
 */
function TablaDatos({
  titulo,
  columnas,
  filas,
  nota,
}: {
  titulo: string
  columnas: [string, string]
  filas: [string, number][]
  nota?: string
}) {
  return (
    <details className="text-sm">
      <summary className={cx('w-fit cursor-pointer rounded-control font-medium text-primary', FOCO)}>Ver datos</summary>
      <table className="mt-2 w-full text-left">
        <caption className="sr-only">{titulo}</caption>
        <thead>
          <tr className="border-b border-subtle text-rotulo text-muted">
            <th scope="col" className="py-1.5 font-medium">{columnas[0]}</th>
            <th scope="col" className="py-1.5 text-right font-medium">{columnas[1]}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-subtle">
          {filas.map(([etiqueta, valor]) => (
            <tr key={etiqueta}>
              <th scope="row" className="py-1.5 font-normal text-fg">{etiqueta}</th>
              <td className="py-1.5 text-right tabular-nums text-fg">{intFmt(valor)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {nota ? <p className="mt-2 text-xs text-muted">{nota}</p> : null}
    </details>
  )
}

/** Reserva el alto del gráfico y lo monta al entrar en pantalla: en móvil, el crecimiento se ve. */
function useVisible() {
  const ref = useRef<HTMLDivElement>(null)
  const visible = useInView(ref, { once: true, margin: '0px 0px -15% 0px' })
  return { ref, visible }
}

function GraficoEtapas({ etapas, sinEtapa }: { etapas: EtapaResumen[]; sinEtapa: number }) {
  const reducido = useReducedMotion() ?? false
  const { ref, visible } = useVisible()
  const datos = useMemo(() => etapas.map((e) => ({ etapa: e.orden < 100 ? `${e.orden} ${e.corta}` : e.corta, causas: e.causas, nombre: e.nombre })), [etapas])
  const total = etapas.reduce((s, e) => s + e.causas, 0)
  // Margen derecho: lo justo para la cifra más larga tras su barra.
  const margenDerecho = intFmt(Math.max(0, ...etapas.map((e) => e.causas))).length * 7 + 12

  return (
    <Card className="flex flex-col">
      <CardHeader
        nivel={3}
        titulo="Causas por etapa procesal"
        descripcion={`Etapa actual de ${intFmt(total)} ${total === 1 ? 'causa' : 'causas'}, en orden del proceso`}
      />
      <CardBody className="flex flex-1 flex-col gap-3">
        {total === 0 ? (
          <p className="text-sm text-muted">Aún no hay causas con etapa procesal.</p>
        ) : (
          // aria-hidden en el contenedor: Bklit monta ejes y tooltip fuera del SVG. Los datos están en la tabla.
          <div ref={ref} aria-hidden="true" className="isolate aspect-[3/2] w-full sm:aspect-[16/9]">
          {visible ? (
            <BarChart
              data={datos}
              xDataKey="etapa"
              orientation="horizontal"
              aspectRatio="auto"
              className="h-full"
              barGap={0.45}
              margin={{ top: 4, right: margenDerecho, bottom: 4, left: 112 }}
              animationDuration={reducido ? 0 : DURACION_MS}
              enterTransition={ENTRADA}
            >
              <Grid horizontal={false} vertical numTicksColumns={4} />
              <Bar dataKey="causas" fill={COLOR} lineCap={4} animate={!reducido} fadedOpacity={0.6} />
              <EtiquetasValor clave="causas" />
              <BarYAxis />
              <ChartTooltip
                showCrosshair={false}
                showDatePill={false}
                damping={0}
                showDots={false}
                content={({ point }) => (
                  <TooltipContent title={String(point.nombre)} rows={[{ color: COLOR, label: 'Causas', value: Number(point.causas) }]} />
                )}
              />
            </BarChart>
          ) : null}
          </div>
        )}
        {sinEtapa > 0 ? (
          <p className="mt-auto text-xs text-muted">
            {intFmt(sinEtapa)} {sinEtapa === 1 ? 'causa' : 'causas'} sin etapa (revisión manual, excluidas o sin datos) no
            {sinEtapa === 1 ? ' aparece' : ' aparecen'} en el gráfico.
          </p>
        ) : null}
        <TablaDatos
          titulo="Causas por etapa procesal"
          columnas={['Etapa', 'Causas']}
          filas={[...etapas.map((e): [string, number] => [e.orden < 100 ? `${e.orden}. ${e.nombre}` : e.nombre, e.causas]), ['Sin etapa', sinEtapa]]}
        />
      </CardBody>
    </Card>
  )
}

function GraficoActividad({ dias }: { dias: DiaActividad[] }) {
  const reducido = useReducedMotion() ?? false
  const { ref, visible } = useVisible()
  const datos = useMemo(
    () => dias.map((d) => ({ dia: fechaCorta.format(new Date(`${d.dia}T00:00:00Z`)), causas: d.causas, fecha: d.dia })),
    [dias],
  )
  const conActividad = dias.filter((d) => d.causas > 0).length
  const vacio = conActividad === 0

  return (
    <Card className="flex flex-col">
      <CardHeader
        nivel={3}
        titulo="Causas consultadas por día"
        descripcion={
          vacio
            ? 'Últimos 30 días'
            : `Últimos 30 días · ${conActividad} ${conActividad === 1 ? 'día' : 'días'} con consultas`
        }
      />
      <CardBody className="flex flex-1 flex-col gap-3">
        {vacio ? (
          <p className="text-sm text-muted">No hubo consultas en los últimos 30 días.</p>
        ) : (
          <div ref={ref} aria-hidden="true" className="isolate aspect-[3/2] w-full sm:aspect-[16/9]">
            {visible ? (
              <BarChart
                data={datos}
                xDataKey="dia"
                aspectRatio="auto"
                className="h-full"
                barGap={0.25}
                margin={{ top: 24, right: 20, bottom: 28, left: 20 }}
                animationDuration={reducido ? 0 : DURACION_MS}
                enterTransition={ENTRADA}
              >
                <Grid horizontal numTicksRows={3} />
                <Bar dataKey="causas" fill={COLOR} lineCap={2} animate={!reducido} fadedOpacity={0.6} />
                <EtiquetasValor clave="causas" />
                <BarXAxis maxLabels={5} />
                <ChartTooltip
                  showCrosshair={false}
                  showDatePill={false}
                  damping={0}
                  showDots={false}
                  content={({ point }) => (
                    <TooltipContent
                      title={fechaLarga.format(new Date(`${String(point.fecha)}T00:00:00Z`))}
                      rows={[{ color: COLOR, label: 'Causas consultadas', value: Number(point.causas) }]}
                    />
                  )}
                />
              </BarChart>
            ) : null}
          </div>
        )}
        <p className="mt-auto text-xs text-muted">
          Consultas con resultado; los intentos con error no cuentan. Una causa consultada varias veces el mismo día
          cuenta una vez.
        </p>
        {vacio ? null : (
          <TablaDatos
            titulo="Causas consultadas por día, días con actividad"
            nota={`Los otros ${30 - conActividad} días del periodo no tuvieron consultas.`}
            columnas={['Día', 'Causas']}
            filas={dias
              .filter((d) => d.causas > 0)
              .map((d): [string, number] => [fechaLarga.format(new Date(`${d.dia}T00:00:00Z`)), d.causas])}
          />
        )}
      </CardBody>
    </Card>
  )
}

/** "Panorama de la cartera": dónde están las causas y cuándo se trabajaron. */
export function PanoramaCartera({
  etapas,
  sinEtapa,
  dias,
}: {
  etapas: EtapaResumen[]
  sinEtapa: number
  dias: DiaActividad[]
}) {
  return (
    <section aria-labelledby="panorama-titulo" className="space-y-3">
      <h2 id="panorama-titulo" className="text-lg font-semibold text-fg">
        Panorama de la cartera
      </h2>
      <div className="grid gap-3 sm:gap-4 lg:grid-cols-2">
        <GraficoEtapas etapas={etapas} sinEtapa={sinEtapa} />
        <GraficoActividad dias={dias} />
      </div>
    </section>
  )
}
