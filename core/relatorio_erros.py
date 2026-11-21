"""Relatórios de erro sem dados pessoais nem credenciais (RNF-SEG-05, LGPD).

Com DEBUG=False, os erros 500 vão por e-mail aos ADMINS (LOGGING em config/settings.py). O filtro padrão do Django
só esconde configurações com nomes como PASSWORD/SECRET e os campos marcados com `sensitive_post_parameters`. Aqui
quase todo formulário carrega dado pessoal (cadastro de participantes, senhas de colaboradores), então o filtro
esconde **todos** os campos enviados, todos os cookies (inclusive `sessionid` e `csrftoken`) e as variáveis locais
cujo nome indique senha, token ou sessão.
"""

import re

from django.views.debug import SafeExceptionReporterFilter

SENSIVEIS = re.compile(r"API|AUTH|TOKEN|KEY|SECRET|PASS|SIGNATURE|COOKIE|SESSION|CSRF|SENHA", flags=re.IGNORECASE)


class FiltroRelatorioErros(SafeExceptionReporterFilter):
    hidden_settings = SENSIVEIS

    def _tudo_oculto(self, multivaluedict):
        return self._cleanse_multivaluedict(multivaluedict, "__ALL__")

    def get_post_parameters(self, request):
        if request is None:
            return {}
        return self._tudo_oculto(request.POST) if self.is_active(request) else request.POST

    def get_cleansed_multivaluedict(self, request, multivaluedict):
        return self._tudo_oculto(multivaluedict) if self.is_active(request) else multivaluedict

    def get_safe_cookies(self, request):
        cookies = getattr(request, "COOKIES", {})
        if not self.is_active(request):
            return dict(cookies)
        return dict.fromkeys(cookies, self.cleansed_substitute)

    def get_traceback_frame_variables(self, request, tb_frame):
        variaveis = super().get_traceback_frame_variables(request, tb_frame)
        if not self.is_active(request):
            return variaveis
        return [(nome, self.cleansed_substitute if SENSIVEIS.search(nome) else valor) for nome, valor in variaveis]
