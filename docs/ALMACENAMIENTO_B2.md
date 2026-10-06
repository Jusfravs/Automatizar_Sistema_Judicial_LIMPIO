# Almacenamiento de lotes en Backblaze B2

## Estado y alcance

La integración está preparada y desactivada por defecto. Al activarla, las entradas y
los resultados **nuevos** usan B2. Las rutas antiguas siguen en Supabase Storage y
continúan funcionando. Los 65 objetos del archivo histórico permanecen en el bucket
privado de Supabase; no se borran ni trasladan automáticamente.

Medición del 6 de octubre de 2026: PostgreSQL 288 MB de 500 MB; Supabase Storage
511 MB de 1 GB, de los cuales 487 MB son archivo histórico y 24 MB son lotes.
La cifra de Storage mide este proyecto; la cuota gratuita se comparte entre los
proyectos de la organización.
Un lote con el Excel grande consumió 11,5 MB de entrada y 10,6 MB de resultado.
Con archivos así, los ~489 MB restantes alcanzarían para unos 22 lotes.

B2 resuelve el crecimiento de **archivos de lotes**. No cambia el límite de 500 MB
de PostgreSQL, por lo que se debe medir también el crecimiento de
`actuaciones_procesales` y `actuaciones` antes de llegar al 80 %.
Con el entorno del motor cargado, `python -m scripts.medir_almacenamiento_supabase`
devuelve los porcentajes y marca alerta a partir del 75 %.

## Preparación de B2

1. Crear una cuenta Backblaze B2 y un bucket **privado** dedicado al portal.
   Anotar el endpoint S3 de la región, con formato
   `https://s3.REGION.backblazeb2.com`.
2. Crear una **Application Key** limitada a ese bucket, con permisos de lectura,
   escritura, listado y borrado. Guardar Key ID y Application Key en un lugar seguro; la
   clave secreta solo se muestra una vez. No usar la clave maestra.
3. Configurar CORS del bucket para el origen exacto
   `https://portal-gestion-judicial.vercel.app`, método `PUT` y encabezado
   `Content-Type`. Para probar desde localhost, agregar temporalmente ese origen
   de forma explícita. No habilitar acceso público al bucket.

   Configuración S3 compatible de ejemplo:

   ```json
   {
     "CORSRules": [{
       "AllowedOrigins": ["https://portal-gestion-judicial.vercel.app"],
       "AllowedMethods": ["PUT"],
       "AllowedHeaders": ["content-type"],
       "MaxAgeSeconds": 3600
     }]
   }
   ```
4. Instalar dependencias Python del motor, incluida `boto3`, antes de reiniciarlo.

## Activación en orden

1. Aplicar `migrations/supabase/006_b2_lotes.sql` en PostgreSQL. Conserva las
   rutas anteriores y permite la nueva ruta vinculada al usuario y al ID del lote.
2. En la cuenta Windows que ejecuta el motor, ejecutar
   `scripts/windows/Configurar-B2Portal.ps1`. Solicita endpoint, bucket, Key ID y
   Application Key sin imprimir la clave. El script comprueba escritura, lectura y
   borrado con un objeto temporal antes de cifrar los cuatro valores en el almacén
   local. Si la prueba falla, las credenciales existentes permanecen intactas.
3. Reiniciar el motor para que cargue las variables nuevas.
4. En Vercel, configurar `B2_ENDPOINT`, `B2_BUCKET`, `B2_KEY_ID` y `B2_APP_KEY`
   como variables **privadas** del servidor. Configurar
   `NEXT_PUBLIC_LOTE_STORAGE=b2` para la compilación del portal y desplegar.
   Ninguna clave B2 debe tener prefijo `NEXT_PUBLIC_`.
5. Crear un lote pequeño de prueba; verificar su ruta `b2:entradas/...`, el
   resultado `b2:resultados/...` y la descarga desde el portal. Verificar también
   la descarga de un lote anterior en Supabase.

El navegador recibe una URL firmada de cinco minutos para subir el Excel directo
al bucket; Vercel no recibe el archivo. Para descargar, el servidor verifica la
sesión y el acceso al lote, y firma un enlace de un minuto. Si la inserción del
lote falla, el portal intenta borrar el archivo huérfano. Backblaze conserva
versiones: esta limpieza elimina la versión concreta para que un objeto oculto
no siga consumiendo cuota. No se aplica a lotes registrados.

## Límites y seguimiento

Backblaze anuncia 10 GB iniciales gratuitos. El saldo de B2 no reinicia cada mes:
los archivos permanecen hasta que se retiren. Revisar el uso de B2 y PostgreSQL
regularmente. Definir una política de conservación de entradas y resultados con
la responsable del archivo judicial antes de automatizar cualquier borrado.
Esta integración no borra archivos existentes.

Fuentes: [precios B2](https://www.backblaze.com/cloud-storage/pricing),
[API S3 y enlaces firmados](https://www.backblaze.com/docs/cloud-storage-s3-compatible-api),
[CORS](https://www.backblaze.com/docs/cloud-storage-cross-origin-resource-sharing-rules),
[cuotas de Supabase](https://supabase.com/docs/guides/platform/billing-on-supabase).
