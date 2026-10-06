export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.18"
  }
  public: {
    Tables: {
      actuaciones: {
        Row: {
          archivo_segmento: string | null
          creado_en: string | null
          detalle: string | null
          fecha: string | null
          id: number
          instancia: string | null
          numero_causa: string | null
          orden: number | null
          tipo_actuacion: string | null
        }
        Insert: {
          archivo_segmento?: string | null
          creado_en?: string | null
          detalle?: string | null
          fecha?: string | null
          id?: number
          instancia?: string | null
          numero_causa?: string | null
          orden?: number | null
          tipo_actuacion?: string | null
        }
        Update: {
          archivo_segmento?: string | null
          creado_en?: string | null
          detalle?: string | null
          fecha?: string | null
          id?: number
          instancia?: string | null
          numero_causa?: string | null
          orden?: number | null
          tipo_actuacion?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "actuaciones_numero_causa_fkey"
            columns: ["numero_causa"]
            isOneToOne: false
            referencedRelation: "expedientes"
            referencedColumns: ["numero_causa"]
          },
          {
            foreignKeyName: "actuaciones_numero_causa_fkey"
            columns: ["numero_causa"]
            isOneToOne: false
            referencedRelation: "v_casos_revision_manual"
            referencedColumns: ["numero_causa"]
          },
          {
            foreignKeyName: "actuaciones_numero_causa_fkey"
            columns: ["numero_causa"]
            isOneToOne: false
            referencedRelation: "v_reporte_ejecutivo"
            referencedColumns: ["numero_causa"]
          },
        ]
      }
      actuaciones_procesales: {
        Row: {
          actuacion_id: string
          archivo_segmento: string | null
          carpeta: string
          contenido_sha256: string
          creado_en: string
          datos_json: Json
          detalle: string
          fecha: string
          numero_causa: string
          titulo: string
        }
        Insert: {
          actuacion_id: string
          archivo_segmento?: string | null
          carpeta: string
          contenido_sha256: string
          creado_en?: string
          datos_json: Json
          detalle: string
          fecha: string
          numero_causa: string
          titulo: string
        }
        Update: {
          actuacion_id?: string
          archivo_segmento?: string | null
          carpeta?: string
          contenido_sha256?: string
          creado_en?: string
          datos_json?: Json
          detalle?: string
          fecha?: string
          numero_causa?: string
          titulo?: string
        }
        Relationships: [
          {
            foreignKeyName: "actuaciones_procesales_numero_causa_fkey"
            columns: ["numero_causa"]
            isOneToOne: false
            referencedRelation: "expedientes"
            referencedColumns: ["numero_causa"]
          },
          {
            foreignKeyName: "actuaciones_procesales_numero_causa_fkey"
            columns: ["numero_causa"]
            isOneToOne: false
            referencedRelation: "v_casos_revision_manual"
            referencedColumns: ["numero_causa"]
          },
          {
            foreignKeyName: "actuaciones_procesales_numero_causa_fkey"
            columns: ["numero_causa"]
            isOneToOne: false
            referencedRelation: "v_reporte_ejecutivo"
            referencedColumns: ["numero_causa"]
          },
        ]
      }
      archivo_historico_objetos: {
        Row: {
          bytes: number
          filas: number
          nombre: string
          registrado_en: string
          sha256: string
        }
        Insert: {
          bytes: number
          filas: number
          nombre: string
          registrado_en?: string
          sha256: string
        }
        Update: {
          bytes?: number
          filas?: number
          nombre?: string
          registrado_en?: string
          sha256?: string
        }
        Relationships: []
      }
      auditorias_ia: {
        Row: {
          consumo_json: Json | null
          creado_en: string
          decision_json: Json | null
          error_codigo: string | null
          estado: string
          huella_contexto: string
          id: number
          modelo: string
          modo: string
          numero_causa: string
        }
        Insert: {
          consumo_json?: Json | null
          creado_en?: string
          decision_json?: Json | null
          error_codigo?: string | null
          estado: string
          huella_contexto: string
          id?: number
          modelo: string
          modo: string
          numero_causa: string
        }
        Update: {
          consumo_json?: Json | null
          creado_en?: string
          decision_json?: Json | null
          error_codigo?: string | null
          estado?: string
          huella_contexto?: string
          id?: number
          modelo?: string
          modo?: string
          numero_causa?: string
        }
        Relationships: [
          {
            foreignKeyName: "auditorias_ia_numero_causa_fkey"
            columns: ["numero_causa"]
            isOneToOne: false
            referencedRelation: "expedientes"
            referencedColumns: ["numero_causa"]
          },
          {
            foreignKeyName: "auditorias_ia_numero_causa_fkey"
            columns: ["numero_causa"]
            isOneToOne: false
            referencedRelation: "v_casos_revision_manual"
            referencedColumns: ["numero_causa"]
          },
          {
            foreignKeyName: "auditorias_ia_numero_causa_fkey"
            columns: ["numero_causa"]
            isOneToOne: false
            referencedRelation: "v_reporte_ejecutivo"
            referencedColumns: ["numero_causa"]
          },
        ]
      }
      catalogo_etapas: {
        Row: {
          eta_id: number
          nombre: string
        }
        Insert: {
          eta_id: number
          nombre: string
        }
        Update: {
          eta_id?: number
          nombre?: string
        }
        Relationships: []
      }
      catalogo_fases: {
        Row: {
          eta_id: number
          fas_id: number
          nombre: string
        }
        Insert: {
          eta_id: number
          fas_id: number
          nombre: string
        }
        Update: {
          eta_id?: number
          fas_id?: number
          nombre?: string
        }
        Relationships: [
          {
            foreignKeyName: "catalogo_fases_eta_id_fkey"
            columns: ["eta_id"]
            isOneToOne: false
            referencedRelation: "catalogo_etapas"
            referencedColumns: ["eta_id"]
          },
        ]
      }
      cola_trabajo: {
        Row: {
          actualizado_en: string
          creado_en: string
          disponible_desde: string
          ejecucion_id: string
          estado: string
          heartbeat_en: string | null
          id: number
          intentos: number
          lease_hasta: string | null
          numero_causa: string
          posicion: number
          prioridad: number
          reservado_en: string | null
          ultimo_error: string | null
          worker_id: string | null
        }
        Insert: {
          actualizado_en?: string
          creado_en?: string
          disponible_desde?: string
          ejecucion_id: string
          estado?: string
          heartbeat_en?: string | null
          id?: number
          intentos?: number
          lease_hasta?: string | null
          numero_causa: string
          posicion: number
          prioridad?: number
          reservado_en?: string | null
          ultimo_error?: string | null
          worker_id?: string | null
        }
        Update: {
          actualizado_en?: string
          creado_en?: string
          disponible_desde?: string
          ejecucion_id?: string
          estado?: string
          heartbeat_en?: string | null
          id?: number
          intentos?: number
          lease_hasta?: string | null
          numero_causa?: string
          posicion?: number
          prioridad?: number
          reservado_en?: string | null
          ultimo_error?: string | null
          worker_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "cola_trabajo_ejecucion_id_fkey"
            columns: ["ejecucion_id"]
            isOneToOne: false
            referencedRelation: "ejecuciones"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "cola_trabajo_ejecucion_id_fkey"
            columns: ["ejecucion_id"]
            isOneToOne: false
            referencedRelation: "v_estado_ejecuciones"
            referencedColumns: ["id"]
          },
        ]
      }
      ejecuciones: {
        Row: {
          config_sha256: string | null
          creado_en: string
          estado: string
          finalizado_en: string | null
          id: string
          iniciado_en: string | null
          perfil: string
          total_esperado: number
          trabajadores_configurados: number
        }
        Insert: {
          config_sha256?: string | null
          creado_en?: string
          estado?: string
          finalizado_en?: string | null
          id: string
          iniciado_en?: string | null
          perfil: string
          total_esperado?: number
          trabajadores_configurados?: number
        }
        Update: {
          config_sha256?: string | null
          creado_en?: string
          estado?: string
          finalizado_en?: string | null
          id?: string
          iniciado_en?: string | null
          perfil?: string
          total_esperado?: number
          trabajadores_configurados?: number
        }
        Relationships: []
      }
      ejecuciones_inferencia: {
        Row: {
          creado_en: string
          estado_json: Json
          huella_contexto: string
          id: number
          numero_causa: string
          version_reglas: string
        }
        Insert: {
          creado_en?: string
          estado_json: Json
          huella_contexto: string
          id?: number
          numero_causa: string
          version_reglas: string
        }
        Update: {
          creado_en?: string
          estado_json?: Json
          huella_contexto?: string
          id?: number
          numero_causa?: string
          version_reglas?: string
        }
        Relationships: [
          {
            foreignKeyName: "ejecuciones_inferencia_numero_causa_fkey"
            columns: ["numero_causa"]
            isOneToOne: false
            referencedRelation: "expedientes"
            referencedColumns: ["numero_causa"]
          },
          {
            foreignKeyName: "ejecuciones_inferencia_numero_causa_fkey"
            columns: ["numero_causa"]
            isOneToOne: false
            referencedRelation: "v_casos_revision_manual"
            referencedColumns: ["numero_causa"]
          },
          {
            foreignKeyName: "ejecuciones_inferencia_numero_causa_fkey"
            columns: ["numero_causa"]
            isOneToOne: false
            referencedRelation: "v_reporte_ejecutivo"
            referencedColumns: ["numero_causa"]
          },
        ]
      }
      eventos_auditoria: {
        Row: {
          creado_en: string | null
          detalle: string | null
          ejecucion_id: string | null
          hash_fuente: string | null
          id: number
          numero_causa: string | null
          origen: string | null
          tipo_evento: string
          worker_id: string | null
        }
        Insert: {
          creado_en?: string | null
          detalle?: string | null
          ejecucion_id?: string | null
          hash_fuente?: string | null
          id?: number
          numero_causa?: string | null
          origen?: string | null
          tipo_evento: string
          worker_id?: string | null
        }
        Update: {
          creado_en?: string | null
          detalle?: string | null
          ejecucion_id?: string | null
          hash_fuente?: string | null
          id?: number
          numero_causa?: string | null
          origen?: string | null
          tipo_evento?: string
          worker_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "eventos_auditoria_ejecucion_id_fkey"
            columns: ["ejecucion_id"]
            isOneToOne: false
            referencedRelation: "ejecuciones"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "eventos_auditoria_ejecucion_id_fkey"
            columns: ["ejecucion_id"]
            isOneToOne: false
            referencedRelation: "v_estado_ejecuciones"
            referencedColumns: ["id"]
          },
        ]
      }
      expedientes: {
        Row: {
          actor: string | null
          actualizado_en: string | null
          archivo_segmento: string | null
          ciudad: string | null
          creado_en: string | null
          datos_json: Json | null
          demandado: string | null
          estado: string | null
          eta_id_etapa_actual: number | null
          eta_id_ultima_etapa: number | null
          etapa_actual: string | null
          fas_id_fase_actual: number | null
          fas_id_ultima_fase: number | null
          fase_actual: string | null
          fecha_fin_ultima_fase: string | null
          fecha_inicio_fase_actual: string | null
          fecha_inicio_juicio: string | null
          fuente_migracion: string | null
          fuente_prioridad: number
          mensaje_especial: string | null
          numero_causa: string
          origen: string | null
          reintentos: number | null
          ruta_html: string | null
          tipo_accion: string | null
          total_actuaciones: number | null
          ultima_etapa: string | null
          ultima_fase: string | null
          version_fuente_en: string | null
        }
        Insert: {
          actor?: string | null
          actualizado_en?: string | null
          archivo_segmento?: string | null
          ciudad?: string | null
          creado_en?: string | null
          datos_json?: Json | null
          demandado?: string | null
          estado?: string | null
          eta_id_etapa_actual?: number | null
          eta_id_ultima_etapa?: number | null
          etapa_actual?: string | null
          fas_id_fase_actual?: number | null
          fas_id_ultima_fase?: number | null
          fase_actual?: string | null
          fecha_fin_ultima_fase?: string | null
          fecha_inicio_fase_actual?: string | null
          fecha_inicio_juicio?: string | null
          fuente_migracion?: string | null
          fuente_prioridad?: number
          mensaje_especial?: string | null
          numero_causa: string
          origen?: string | null
          reintentos?: number | null
          ruta_html?: string | null
          tipo_accion?: string | null
          total_actuaciones?: number | null
          ultima_etapa?: string | null
          ultima_fase?: string | null
          version_fuente_en?: string | null
        }
        Update: {
          actor?: string | null
          actualizado_en?: string | null
          archivo_segmento?: string | null
          ciudad?: string | null
          creado_en?: string | null
          datos_json?: Json | null
          demandado?: string | null
          estado?: string | null
          eta_id_etapa_actual?: number | null
          eta_id_ultima_etapa?: number | null
          etapa_actual?: string | null
          fas_id_fase_actual?: number | null
          fas_id_ultima_fase?: number | null
          fase_actual?: string | null
          fecha_fin_ultima_fase?: string | null
          fecha_inicio_fase_actual?: string | null
          fecha_inicio_juicio?: string | null
          fuente_migracion?: string | null
          fuente_prioridad?: number
          mensaje_especial?: string | null
          numero_causa?: string
          origen?: string | null
          reintentos?: number | null
          ruta_html?: string | null
          tipo_accion?: string | null
          total_actuaciones?: number | null
          ultima_etapa?: string | null
          ultima_fase?: string | null
          version_fuente_en?: string | null
        }
        Relationships: []
      }
      hitos_procesales: {
        Row: {
          actuacion_id: string
          condicion: string
          creado_en: string
          eta_id: number | null
          fas_id: number | null
          fuente: string
          id: number
          numero_causa: string
          version: string
        }
        Insert: {
          actuacion_id: string
          condicion: string
          creado_en?: string
          eta_id?: number | null
          fas_id?: number | null
          fuente: string
          id?: number
          numero_causa: string
          version: string
        }
        Update: {
          actuacion_id?: string
          condicion?: string
          creado_en?: string
          eta_id?: number | null
          fas_id?: number | null
          fuente?: string
          id?: number
          numero_causa?: string
          version?: string
        }
        Relationships: [
          {
            foreignKeyName: "hitos_procesales_actuacion_id_fkey"
            columns: ["actuacion_id"]
            isOneToOne: false
            referencedRelation: "actuaciones_procesales"
            referencedColumns: ["actuacion_id"]
          },
          {
            foreignKeyName: "hitos_procesales_numero_causa_fkey"
            columns: ["numero_causa"]
            isOneToOne: false
            referencedRelation: "expedientes"
            referencedColumns: ["numero_causa"]
          },
          {
            foreignKeyName: "hitos_procesales_numero_causa_fkey"
            columns: ["numero_causa"]
            isOneToOne: false
            referencedRelation: "v_casos_revision_manual"
            referencedColumns: ["numero_causa"]
          },
          {
            foreignKeyName: "hitos_procesales_numero_causa_fkey"
            columns: ["numero_causa"]
            isOneToOne: false
            referencedRelation: "v_reporte_ejecutivo"
            referencedColumns: ["numero_causa"]
          },
        ]
      }
      perfiles: {
        Row: {
          activo: boolean
          creado_en: string
          id: string
          nombre: string
          rol: string
        }
        Insert: {
          activo?: boolean
          creado_en?: string
          id: string
          nombre?: string
          rol: string
        }
        Update: {
          activo?: boolean
          creado_en?: string
          id?: string
          nombre?: string
          rol?: string
        }
        Relationships: []
      }
      resultados_ejecucion: {
        Row: {
          archivo_segmento: string | null
          ciudad: string | null
          creado_en: string
          datos_json: Json
          ejecucion_id: string | null
          estado: string
          fuente_actualizado_en: string | null
          fuente_migracion: string | null
          hash_fuente: string | null
          id: number
          intento: number
          numero_causa: string
          origen: string
          trabajo_id: number | null
          worker_id: string | null
        }
        Insert: {
          archivo_segmento?: string | null
          ciudad?: string | null
          creado_en?: string
          datos_json: Json
          ejecucion_id?: string | null
          estado: string
          fuente_actualizado_en?: string | null
          fuente_migracion?: string | null
          hash_fuente?: string | null
          id?: number
          intento?: number
          numero_causa: string
          origen: string
          trabajo_id?: number | null
          worker_id?: string | null
        }
        Update: {
          archivo_segmento?: string | null
          ciudad?: string | null
          creado_en?: string
          datos_json?: Json
          ejecucion_id?: string | null
          estado?: string
          fuente_actualizado_en?: string | null
          fuente_migracion?: string | null
          hash_fuente?: string | null
          id?: number
          intento?: number
          numero_causa?: string
          origen?: string
          trabajo_id?: number | null
          worker_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "resultados_ejecucion_ejecucion_id_fkey"
            columns: ["ejecucion_id"]
            isOneToOne: false
            referencedRelation: "ejecuciones"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "resultados_ejecucion_ejecucion_id_fkey"
            columns: ["ejecucion_id"]
            isOneToOne: false
            referencedRelation: "v_estado_ejecuciones"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "resultados_ejecucion_trabajo_id_fkey"
            columns: ["trabajo_id"]
            isOneToOne: false
            referencedRelation: "cola_trabajo"
            referencedColumns: ["id"]
          },
        ]
      }
      revisiones_ia: {
        Row: {
          auditoria_id: number
          decision_humana: string | null
          estado: string
          eta_id_manual: number | null
          fas_id_manual: number | null
          id: number
          numero_causa: string
          observacion: string | null
          revisado_en: string | null
          revisado_por: string | null
        }
        Insert: {
          auditoria_id: number
          decision_humana?: string | null
          estado?: string
          eta_id_manual?: number | null
          fas_id_manual?: number | null
          id?: number
          numero_causa: string
          observacion?: string | null
          revisado_en?: string | null
          revisado_por?: string | null
        }
        Update: {
          auditoria_id?: number
          decision_humana?: string | null
          estado?: string
          eta_id_manual?: number | null
          fas_id_manual?: number | null
          id?: number
          numero_causa?: string
          observacion?: string | null
          revisado_en?: string | null
          revisado_por?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "revisiones_ia_auditoria_id_fkey"
            columns: ["auditoria_id"]
            isOneToOne: true
            referencedRelation: "auditorias_ia"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "revisiones_ia_numero_causa_fkey"
            columns: ["numero_causa"]
            isOneToOne: false
            referencedRelation: "expedientes"
            referencedColumns: ["numero_causa"]
          },
          {
            foreignKeyName: "revisiones_ia_numero_causa_fkey"
            columns: ["numero_causa"]
            isOneToOne: false
            referencedRelation: "v_casos_revision_manual"
            referencedColumns: ["numero_causa"]
          },
          {
            foreignKeyName: "revisiones_ia_numero_causa_fkey"
            columns: ["numero_causa"]
            isOneToOne: false
            referencedRelation: "v_reporte_ejecutivo"
            referencedColumns: ["numero_causa"]
          },
        ]
      }
      schema_migrations: {
        Row: {
          aplicada_en: string
          checksum: string
          version: string
        }
        Insert: {
          aplicada_en?: string
          checksum: string
          version: string
        }
        Update: {
          aplicada_en?: string
          checksum?: string
          version?: string
        }
        Relationships: []
      }
      servicio_latido: {
        Row: {
          estado: string
          iniciado_en: string
          latido_en: string
          solicitud_id: string | null
          worker_host: string
        }
        Insert: {
          estado: string
          iniciado_en?: string
          latido_en?: string
          solicitud_id?: string | null
          worker_host: string
        }
        Update: {
          estado?: string
          iniciado_en?: string
          latido_en?: string
          solicitud_id?: string | null
          worker_host?: string
        }
        Relationships: [
          {
            foreignKeyName: "servicio_latido_solicitud_id_fkey"
            columns: ["solicitud_id"]
            isOneToOne: false
            referencedRelation: "solicitudes_lote"
            referencedColumns: ["id"]
          },
        ]
      }
      solicitudes_lote: {
        Row: {
          actualizado_en: string
          archivo_nombre: string
          archivo_ruta: string
          cancelar: boolean
          continuar: boolean
          creado_en: string
          ejecucion_id: string | null
          estado: string
          filtros: Json
          finalizado_en: string | null
          hoja: string | null
          id: string
          mensaje: string | null
          modo: string
          parametro: string | null
          perfil: string | null
          resultado_ruta: string | null
          solicitado_por: string
          tomado_en: string | null
          trabajadores: number
          worker_host: string | null
        }
        Insert: {
          actualizado_en?: string
          archivo_nombre: string
          archivo_ruta: string
          cancelar?: boolean
          continuar?: boolean
          creado_en?: string
          ejecucion_id?: string | null
          estado?: string
          filtros?: Json
          finalizado_en?: string | null
          hoja?: string | null
          id?: string
          mensaje?: string | null
          modo: string
          parametro?: string | null
          perfil?: string | null
          resultado_ruta?: string | null
          solicitado_por?: string
          tomado_en?: string | null
          trabajadores?: number
          worker_host?: string | null
        }
        Update: {
          actualizado_en?: string
          archivo_nombre?: string
          archivo_ruta?: string
          cancelar?: boolean
          continuar?: boolean
          creado_en?: string
          ejecucion_id?: string | null
          estado?: string
          filtros?: Json
          finalizado_en?: string | null
          hoja?: string | null
          id?: string
          mensaje?: string | null
          modo?: string
          parametro?: string | null
          perfil?: string | null
          resultado_ruta?: string | null
          solicitado_por?: string
          tomado_en?: string | null
          trabajadores?: number
          worker_host?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "solicitudes_lote_ejecucion_id_fkey"
            columns: ["ejecucion_id"]
            isOneToOne: false
            referencedRelation: "ejecuciones"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "solicitudes_lote_ejecucion_id_fkey"
            columns: ["ejecucion_id"]
            isOneToOne: false
            referencedRelation: "v_estado_ejecuciones"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Views: {
      v_casos_revision_manual: {
        Row: {
          actor: string | null
          actualizado_en: string | null
          ciudad: string | null
          demandado: string | null
          fecha_fin_ultima_fase: string | null
          mensaje_especial: string | null
          numero_causa: string | null
          total_actuaciones: number | null
          ultima_fase: string | null
        }
        Insert: {
          actor?: string | null
          actualizado_en?: string | null
          ciudad?: string | null
          demandado?: string | null
          fecha_fin_ultima_fase?: string | null
          mensaje_especial?: string | null
          numero_causa?: string | null
          total_actuaciones?: number | null
          ultima_fase?: string | null
        }
        Update: {
          actor?: string | null
          actualizado_en?: string | null
          ciudad?: string | null
          demandado?: string | null
          fecha_fin_ultima_fase?: string | null
          mensaje_especial?: string | null
          numero_causa?: string | null
          total_actuaciones?: number | null
          ultima_fase?: string | null
        }
        Relationships: []
      }
      v_cola_trabajo: {
        Row: {
          actualizado_en: string | null
          ejecucion_id: string | null
          estado: string | null
          heartbeat_en: string | null
          intentos: number | null
          lease_hasta: string | null
          numero_causa: string | null
          posicion: number | null
          reservado_en: string | null
          ultimo_error: string | null
          worker_id: string | null
        }
        Insert: {
          actualizado_en?: string | null
          ejecucion_id?: string | null
          estado?: string | null
          heartbeat_en?: string | null
          intentos?: number | null
          lease_hasta?: string | null
          numero_causa?: string | null
          posicion?: number | null
          reservado_en?: string | null
          ultimo_error?: string | null
          worker_id?: string | null
        }
        Update: {
          actualizado_en?: string | null
          ejecucion_id?: string | null
          estado?: string | null
          heartbeat_en?: string | null
          intentos?: number | null
          lease_hasta?: string | null
          numero_causa?: string | null
          posicion?: number | null
          reservado_en?: string | null
          ultimo_error?: string | null
          worker_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "cola_trabajo_ejecucion_id_fkey"
            columns: ["ejecucion_id"]
            isOneToOne: false
            referencedRelation: "ejecuciones"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "cola_trabajo_ejecucion_id_fkey"
            columns: ["ejecucion_id"]
            isOneToOne: false
            referencedRelation: "v_estado_ejecuciones"
            referencedColumns: ["id"]
          },
        ]
      }
      v_estado_ejecuciones: {
        Row: {
          atendidos: number | null
          creado_en: string | null
          en_proceso: number | null
          errores_finales: number | null
          estado: string | null
          finalizado_en: string | null
          id: string | null
          iniciado_en: string | null
          pendientes: number | null
          perfil: string | null
          total_esperado: number | null
          trabajadores_configurados: number | null
        }
        Relationships: []
      }
      v_reporte_ejecutivo: {
        Row: {
          actor: string | null
          actualizado_en: string | null
          ciudad: string | null
          demandado: string | null
          estado: string | null
          eta_id_etapa_actual: number | null
          eta_id_ultima_etapa: number | null
          etapa_actual: string | null
          fas_id_fase_actual: number | null
          fas_id_ultima_fase: number | null
          fase_actual: string | null
          fecha_fin_ultima_fase: string | null
          fecha_inicio_fase_actual: string | null
          fecha_inicio_juicio: string | null
          mensaje_especial: string | null
          numero_causa: string | null
          tipo_accion: string | null
          total_actuaciones: number | null
          ultima_etapa: string | null
          ultima_fase: string | null
        }
        Insert: {
          actor?: string | null
          actualizado_en?: string | null
          ciudad?: string | null
          demandado?: string | null
          estado?: string | null
          eta_id_etapa_actual?: number | null
          eta_id_ultima_etapa?: number | null
          etapa_actual?: string | null
          fas_id_fase_actual?: number | null
          fas_id_ultima_fase?: number | null
          fase_actual?: string | null
          fecha_fin_ultima_fase?: string | null
          fecha_inicio_fase_actual?: string | null
          fecha_inicio_juicio?: string | null
          mensaje_especial?: string | null
          numero_causa?: string | null
          tipo_accion?: string | null
          total_actuaciones?: number | null
          ultima_etapa?: string | null
          ultima_fase?: string | null
        }
        Update: {
          actor?: string | null
          actualizado_en?: string | null
          ciudad?: string | null
          demandado?: string | null
          estado?: string | null
          eta_id_etapa_actual?: number | null
          eta_id_ultima_etapa?: number | null
          etapa_actual?: string | null
          fas_id_fase_actual?: number | null
          fas_id_ultima_fase?: number | null
          fase_actual?: string | null
          fecha_fin_ultima_fase?: string | null
          fecha_inicio_fase_actual?: string | null
          fecha_inicio_juicio?: string | null
          mensaje_especial?: string | null
          numero_causa?: string | null
          tipo_accion?: string | null
          total_actuaciones?: number | null
          ultima_etapa?: string | null
          ultima_fase?: string | null
        }
        Relationships: []
      }
      v_resumen_fases: {
        Row: {
          etapa: string | null
          fase: string | null
          porcentaje: number | null
          total_casos: number | null
        }
        Relationships: []
      }
      v_trabajadores_activos: {
        Row: {
          activo_desde: string | null
          ejecucion_id: string | null
          lease_hasta: string | null
          trabajos_activos: number | null
          ultimo_heartbeat: string | null
          worker_id: string | null
        }
        Relationships: [
          {
            foreignKeyName: "cola_trabajo_ejecucion_id_fkey"
            columns: ["ejecucion_id"]
            isOneToOne: false
            referencedRelation: "ejecuciones"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "cola_trabajo_ejecucion_id_fkey"
            columns: ["ejecucion_id"]
            isOneToOne: false
            referencedRelation: "v_estado_ejecuciones"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Functions: {
      cancelar_solicitud: { Args: { p_id: string }; Returns: string }
      registrar_revision: {
        Args: {
          p_auditoria_id: number
          p_decision: string
          p_eta_id?: number
          p_fas_id?: number
          p_observacion?: string
        }
        Returns: string
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends (DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never) = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends (PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never) = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {},
  },
} as const
