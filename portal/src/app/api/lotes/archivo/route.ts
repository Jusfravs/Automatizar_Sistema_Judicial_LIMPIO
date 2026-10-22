import { DeleteObjectCommand, GetObjectCommand, HeadObjectCommand, ListObjectVersionsCommand, PutObjectCommand } from '@aws-sdk/client-s3'
import { getSignedUrl } from '@aws-sdk/s3-request-presigner'
import { NextRequest, NextResponse } from 'next/server'
import { b2Config, B2_PREFIX, UUID_RE } from '@/lib/b2'
import { MAX_FILE_SIZE, XLSX_MIME } from '@/lib/lotes'
import { esRolValido } from '@/lib/roles'
import { createClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

function respuestaError(estado: number, codigo: string) {
  return NextResponse.json({ error: codigo }, { status: estado, headers: { 'Cache-Control': 'no-store' } })
}

async function usuarioAutenticado() {
  const supabase = await createClient()
  const { data: { user }, error } = await supabase.auth.getUser()
  if (error || !user) return { supabase, user: null }
  const { data: perfil } = await supabase.from('perfiles')
    .select('rol, activo').eq('id', user.id).single()
  return { supabase, user: perfil?.activo && esRolValido(perfil.rol) ? user : null }
}

export async function POST(request: NextRequest) {
  const { supabase, user } = await usuarioAutenticado()
  if (!user) return respuestaError(401, 'SESION_REQUERIDA')
  let body: { id?: unknown; size?: unknown }
  try { body = await request.json() } catch { return respuestaError(400, 'SOLICITUD_INVALIDA') }
  if (typeof body.id !== 'string' || !UUID_RE.test(body.id) ||
      typeof body.size !== 'number' || !Number.isInteger(body.size) ||
      body.size < 1 || body.size > MAX_FILE_SIZE) {
    return respuestaError(400, 'ARCHIVO_INVALIDO')
  }
  const { data: existente, error: consultaError } = await supabase.from('solicitudes_lote')
    .select('id').eq('id', body.id).maybeSingle()
  if (consultaError) return respuestaError(503, 'CONSULTA_NO_DISPONIBLE')
  if (existente) return respuestaError(409, 'LOTE_YA_REGISTRADO')
  try {
    const { client, bucket } = b2Config()
    const key = `entradas/${user.id}/${body.id}.xlsx`
    const url = await getSignedUrl(client, new PutObjectCommand({
      Bucket: bucket, Key: key, ContentType: XLSX_MIME, ContentLength: body.size,
    }), { expiresIn: 300 })
    return NextResponse.json({ url, ruta: `${B2_PREFIX}${key}` }, { headers: { 'Cache-Control': 'no-store' } })
  } catch {
    return respuestaError(503, 'B2_NO_DISPONIBLE')
  }
}

export async function GET(request: NextRequest) {
  const { supabase, user } = await usuarioAutenticado()
  if (!user) return respuestaError(401, 'SESION_REQUERIDA')
  const id = request.nextUrl.searchParams.get('id')
  if (!id || !UUID_RE.test(id)) return respuestaError(400, 'SOLICITUD_INVALIDA')
  const completo = request.nextUrl.searchParams.get('tipo') === 'completo'
  const { data, error } = await supabase.from('solicitudes_lote')
    .select('resultado_ruta, archivo_ruta, modo').eq('id', id).single()
  const principal = `${B2_PREFIX}resultados/${id}.xlsx`
  // El reporte completo puede existir sin principal (EXCEL_LOTE_NO_DISPONIBLE): basta un lote de B2
  // en «solo» o «lote»; en «pendientes» el principal ya es el completo.
  const disponible = completo
    ? data?.modo !== 'pendientes' && (data?.resultado_ruta === principal || !!data?.archivo_ruta.startsWith(B2_PREFIX))
    : data?.resultado_ruta === principal
  if (error || !data || !disponible) {
    return respuestaError(404, 'RESULTADO_NO_DISPONIBLE')
  }
  try {
    const { client, bucket } = b2Config()
    // El reporte completo (todas las causas del archivo) se publica aparte y es opcional.
    const key = completo ? `resultados/${id}_completo.xlsx` : principal.slice(B2_PREFIX.length)
    if (completo) {
      try {
        await client.send(new HeadObjectCommand({ Bucket: bucket, Key: key }))
      } catch (exc) {
        const estado = (exc as { $metadata?: { httpStatusCode?: number } }).$metadata?.httpStatusCode
        return estado === 404 ? respuestaError(404, 'COMPLETO_NO_DISPONIBLE') : respuestaError(503, 'B2_NO_DISPONIBLE')
      }
    }
    const url = await getSignedUrl(client, new GetObjectCommand({
      Bucket: bucket, Key: key,
    }), { expiresIn: 60 })
    return NextResponse.json({ url }, { headers: { 'Cache-Control': 'no-store' } })
  } catch {
    return respuestaError(503, 'B2_NO_DISPONIBLE')
  }
}

export async function DELETE(request: NextRequest) {
  const { supabase, user } = await usuarioAutenticado()
  if (!user) return respuestaError(401, 'SESION_REQUERIDA')
  let body: { id?: unknown }
  try { body = await request.json() } catch { return respuestaError(400, 'SOLICITUD_INVALIDA') }
  if (typeof body.id !== 'string' || !UUID_RE.test(body.id)) {
    return respuestaError(400, 'SOLICITUD_INVALIDA')
  }
  const { data, error } = await supabase.from('solicitudes_lote')
    .select('id').eq('id', body.id).maybeSingle()
  if (error || data) return respuestaError(409, 'LOTE_YA_REGISTRADO')
  try {
    const { client, bucket } = b2Config()
    const key = `entradas/${user.id}/${body.id}.xlsx`
    const versiones = await client.send(new ListObjectVersionsCommand({
      Bucket: bucket, Prefix: key,
    }))
    if (versiones.IsTruncated) return respuestaError(503, 'B2_DEMASIADAS_VERSIONES')
    const objetos = [...(versiones.Versions ?? []), ...(versiones.DeleteMarkers ?? [])]
      .filter((objeto) => objeto.Key === key && objeto.VersionId)
    for (const objeto of objetos) {
      await client.send(new DeleteObjectCommand({
        Bucket: bucket, Key: key, VersionId: objeto.VersionId,
      }))
    }
    return NextResponse.json({ ok: true }, { headers: { 'Cache-Control': 'no-store' } })
  } catch {
    return respuestaError(503, 'B2_NO_DISPONIBLE')
  }
}
