"""RNF-SEG-05 / LGPD: relatórios de erro (e-mail aos ADMINS) sem senha, cookies nem dados pessoais."""

import sys

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.views.debug import ExceptionReporter, get_default_exception_reporter_filter

from core.relatorio_erros import FiltroRelatorioErros

SENHA = "Senha-Ficticia-Secreta-2026"
SESSAO = "sessao-ficticia-abc123"
NOME = "Maria Ficticia Sigilosa"


def _relatorio():
    request = RequestFactory().post("/colaboradores/novo/", {"senha": SENHA, "confirmacao_senha": SENHA,
                                                              "nome_completo": NOME})
    request.COOKIES = {"sessionid": SESSAO, "csrftoken": "csrf-ficticio"}
    request.META["HTTP_COOKIE"] = f"sessionid={SESSAO}"

    def falha(senha):  # variável local com nome sensível, como nos serviços de colaboradores
        raise RuntimeError("falha fictícia")

    try:
        falha(SENHA)
    except RuntimeError:
        return ExceptionReporter(request, *sys.exc_info()).get_traceback_text()


@override_settings(DEBUG=False, DEFAULT_EXCEPTION_REPORTER_FILTER="core.relatorio_erros.FiltroRelatorioErros")
class RelatorioDeErrosTests(SimpleTestCase):
    def test_filtro_configurado(self):
        self.assertIsInstance(get_default_exception_reporter_filter(), FiltroRelatorioErros)

    def test_relatorio_nao_leva_senha_sessao_nem_dados_pessoais(self):
        texto = _relatorio()
        self.assertNotIn(SENHA, texto)
        self.assertNotIn(SESSAO, texto)
        self.assertNotIn(NOME, texto)
        self.assertIn("nome_completo", texto)  # o nome do campo continua, só o valor é escondido
        self.assertIn("falha fictícia", texto)

    @override_settings(DEBUG=True)
    def test_em_desenvolvimento_o_relatorio_fica_completo(self):
        self.assertIn(NOME, _relatorio())
