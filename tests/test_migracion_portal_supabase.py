import re
import unittest
from pathlib import Path

from src.catalogo_procesal import ETAPAS, FASES
from src.proveedor_nvidia import VERSION_PROMPT


RAIZ = Path(__file__).resolve().parents[1]
SQL_PORTAL = RAIZ / "migrations" / "supabase" / "002_portal.sql"
SQL_MOTOR = sorted((RAIZ / "migrations" / "postgres").glob("*.sql"))
SQL_SUPABASE = sorted((RAIZ / "migrations" / "supabase").glob("*.sql"))
SQL_ACCESO = RAIZ / "migrations" / "supabase" / "003_acceso_unificado.sql"


class TestMigracionPortalSupabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = SQL_PORTAL.read_text(encoding="utf-8")

    def test_catalogo_de_etapas_coincide_con_el_motor(self):
        etapas = {
            nombre: int(eta_id)
            for eta_id, nombre in re.findall(r"\((\d+), '(\d [A-Z ]+)'\)", self.sql)
        }
        self.assertEqual(etapas, ETAPAS)

    def test_catalogo_de_fases_coincide_con_el_motor(self):
        filas = re.findall(r"\((\d+), (\d+), '([^']+)'\)", self.sql)
        fases = {nombre: int(fas_id) for fas_id, _eta, nombre in filas}
        self.assertEqual(fases, FASES)
        for fas_id, eta_id, nombre in filas:
            self.assertEqual(int(eta_id), int(nombre.split(".")[0]) + 9, nombre)

    def test_version_vigente_coincide_con_el_prompt_de_auditoria(self):
        for archivo in SQL_SUPABASE:
            for constante in re.findall(r"c_version_vigente CONSTANT VARCHAR := '([^']+)'",
                                        archivo.read_text(encoding="utf-8")):
                self.assertEqual(constante, VERSION_PROMPT, archivo.name)

    def test_acceso_unificado_sin_roles_divididos(self):
        sql = SQL_ACCESO.read_text(encoding="utf-8")
        self.assertIn("CHECK (rol IN ('admin', 'usuario'))", sql)
        politicas = re.findall(r"CREATE POLICY (\w+)", sql)
        self.assertTrue(politicas)
        for politica in politicas:
            self.assertNotIn("gestor", politica)
        self.assertNotRegex(sql, r"rol_actual\(\)\)? (NOT )?IN \(")

    def test_todas_las_tablas_del_motor_tienen_rls(self):
        tablas_motor = set()
        for archivo in SQL_MOTOR:
            tablas_motor |= set(re.findall(
                r"CREATE TABLE IF NOT EXISTS (\w+)", archivo.read_text(encoding="utf-8")
            ))
        bloque_rls = self.sql.split("ENABLE ROW LEVEL SECURITY")[0]
        for tabla in tablas_motor:
            self.assertIn("'%s'" % tabla, bloque_rls, tabla)

    def test_todas_las_vistas_del_motor_usan_security_invoker(self):
        vistas = set()
        for archivo in SQL_MOTOR:
            vistas |= set(re.findall(
                r"CREATE OR REPLACE VIEW (\w+)", archivo.read_text(encoding="utf-8")
            ))
        for vista in vistas:
            self.assertIn(
                "ALTER VIEW public.%s SET (security_invoker = on)" % vista, self.sql
            )

    def test_borrado_de_entradas_solo_propias_y_sin_solicitud(self):
        sql = (RAIZ / "migrations" / "supabase" / "004_limpieza_entradas.sql").read_text(
            encoding="utf-8")
        self.assertIn("FOR DELETE TO authenticated", sql)
        self.assertIn("owner_id = (SELECT auth.uid())::TEXT", sql)
        self.assertIn("NOT EXISTS", sql)
        self.assertIn("'entradas'", sql)
        self.assertNotRegex(sql, r"(?i)\bDROP\b")

    def test_anon_no_recibe_privilegios(self):
        self.assertIn("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon", self.sql)
        self.assertNotRegex(self.sql, r"GRANT [^;]* TO [^;]*\banon\b")


if __name__ == "__main__":
    unittest.main()
