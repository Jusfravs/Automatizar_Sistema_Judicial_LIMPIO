import type { NextConfig } from "next"

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
if (!supabaseUrl) {
  throw new Error('Falta NEXT_PUBLIC_SUPABASE_URL: la política de seguridad de contenido la necesita al construir.')
}
const supabaseWss = supabaseUrl.replace('https://', 'wss://')
const b2Endpoint = process.env.NEXT_PUBLIC_LOTE_STORAGE === 'b2'
  ? process.env.B2_ENDPOINT?.replace(/\/$/, '')
  : undefined
if (process.env.NEXT_PUBLIC_LOTE_STORAGE === 'b2' &&
    !/^https:\/\/s3\.[a-z0-9-]+\.backblazeb2\.com$/i.test(b2Endpoint ?? '')) {
  throw new Error('Falta B2_ENDPOINT valido para permitir la subida desde el navegador.')
}

const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'" + (process.env.NODE_ENV === 'development' ? " 'unsafe-eval'" : ''),
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self'",
  `connect-src 'self' ${supabaseUrl} ${supabaseWss}${b2Endpoint ? ` ${b2Endpoint}` : ''}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join('; ')

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // Evita que `next dev` agregue archivos de reglas al repo.
  agentRules: false,
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'Content-Security-Policy', value: csp },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
          { key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains' },
        ],
      },
    ]
  },
}

export default nextConfig
