"""Leitura da DATABASE_URL da hospedagem (config/banco.py). Endereços fictícios."""

from django.test import SimpleTestCase

from config.banco import banco_de_url, banco_local


class BancoDeUrlTests(SimpleTestCase):
    def test_url_completa_com_ssl(self):
        banco = banco_de_url("postgresql://usuario:s%40nha@db.exemplo.test:6543/nci_teste?sslmode=require",
                             conn_max_age=60)
        self.assertEqual(banco["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual((banco["NAME"], banco["USER"], banco["PASSWORD"]), ("nci_teste", "usuario", "s@nha"))
        self.assertEqual((banco["HOST"], banco["PORT"]), ("db.exemplo.test", "6543"))
        self.assertEqual(banco["OPTIONS"], {"sslmode": "require"})
        self.assertEqual(banco["CONN_MAX_AGE"], 60)
        self.assertTrue(banco["CONN_HEALTH_CHECKS"])

    def test_url_do_render_sem_porta_nem_parametros(self):
        banco = banco_de_url("postgres://nci_teste:segredo@dpg-ficticio-a/nci_teste")
        self.assertEqual(banco["PORT"], "5432")
        self.assertNotIn("OPTIONS", banco)
        self.assertEqual(banco["CONN_MAX_AGE"], 0)
        self.assertFalse(banco["CONN_HEALTH_CHECKS"])

    def test_url_invalida(self):
        for url in ("mysql://u:s@h/banco", "postgresql://u:s@h"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                banco_de_url(url)

    def test_banco_local_pelas_variaveis_postgres(self):
        banco = banco_local({"POSTGRES_DB": "nci_dev", "POSTGRES_USER": "nci", "POSTGRES_PASSWORD": "x"})
        self.assertEqual((banco["HOST"], banco["PORT"]), ("127.0.0.1", "5433"))
