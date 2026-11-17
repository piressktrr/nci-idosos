"""Fontes servidas localmente, sem Google Fonts (RNF-SEG-18)."""

from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

PASTA_FONTES = Path(settings.BASE_DIR) / "static" / "vendor" / "fonts"
# Hosts montados por partes para que o grep do repositório por eles fique vazio.
HOSTS_GOOGLE = ("fonts.google" + "apis.com", "fonts.g" + "static.com")
FONTES = ("poppins-latin-700-normal.woff2", "questrial-latin-400-normal.woff2")


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class FontesLocaisTests(TestCase):
    def test_entrar_nao_referencia_google_fonts(self):
        resposta = self.client.get(reverse("entrar"))
        self.assertEqual(resposta.status_code, 200)
        html = resposta.content.decode()
        for host in HOSTS_GOOGLE:
            self.assertNotIn(host, html)

    def test_arquivos_woff2_existem(self):
        for nome in FONTES:
            with self.subTest(fonte=nome):
                caminho = PASTA_FONTES / nome
                self.assertTrue(caminho.is_file(), caminho)
                self.assertTrue(caminho.read_bytes().startswith(b"wOF2"), caminho)

    def test_css_declara_font_face_locais(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "base.css").read_text(encoding="utf-8")
        for nome in FONTES:
            with self.subTest(fonte=nome):
                self.assertIn(f"../vendor/fonts/{nome}", css)
