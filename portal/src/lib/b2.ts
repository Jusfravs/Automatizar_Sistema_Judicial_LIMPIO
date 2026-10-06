import { S3Client } from '@aws-sdk/client-s3'

export const B2_PREFIX = 'b2:'
export const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

export function b2Config() {
  const endpoint = process.env.B2_ENDPOINT
  const bucket = process.env.B2_BUCKET
  const keyId = process.env.B2_KEY_ID
  const appKey = process.env.B2_APP_KEY
  if (!endpoint || !bucket || !keyId || !appKey ||
      !/^https:\/\/s3\.[a-z0-9-]+\.backblazeb2\.com\/?$/i.test(endpoint) ||
      !/^[a-z0-9][a-z0-9-]{4,48}[a-z0-9]$/.test(bucket)) {
    throw new Error('B2_NO_CONFIGURADO')
  }
  return {
    bucket,
    client: new S3Client({
      region: 'us-east-1',
      endpoint: endpoint.replace(/\/$/, ''),
      forcePathStyle: true,
      requestChecksumCalculation: 'WHEN_REQUIRED',
      responseChecksumValidation: 'WHEN_REQUIRED',
      credentials: { accessKeyId: keyId, secretAccessKey: appKey },
    }),
  }
}
