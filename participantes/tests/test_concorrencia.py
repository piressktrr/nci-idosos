"""RN-PAR-01: dois cadastros simultâneos da mesma pessoa não passam juntos pela checagem de duplicidade.

Usa TransactionTestCase e duas threads (cada uma com a sua conexão), como num duplo clique em "Salvar".
Dados fictícios (RN-SEG-02).
"""

import threading
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TransactionTestCase

from participantes.models import Participante
from participantes.services import cadastrar_participante

DADOS = {
    "nome_completo": "Clara Ficticia Concorrente", "data_nascimento": date(1951, 5, 5), "sexo": "F",
    "raca_cor": "parda", "identidade_genero": "cisgenero", "telefone_celular": "61912345678",
    "telefone_residencial": "", "origem_encaminhamento": "cras", "endereco": "Rua Ficticia, 7",
    "ensino_medio_completo": False, "observacao_encaminhamento": "",
}


class CadastroSimultaneoTests(TransactionTestCase):
    def test_duplo_envio_cria_um_so_cadastro(self):
        usuario = get_user_model().objects.create_user(username="equipe_concorrencia_ficticia")
        usuario.user_permissions.add(Permission.objects.get(codename="add_participante"))
        largada = threading.Barrier(2)
        resultados = []

        def enviar():
            try:
                largada.wait(timeout=10)
                cadastrar_participante(usuario=usuario, data_entrada=date(2024, 1, 10), **DADOS)
                resultados.append("criado")
            except ValidationError as erro:
                resultados.append(erro.error_list[0].code)
            finally:
                connection.close()

        threads = [threading.Thread(target=enviar) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertEqual(sorted(resultados), ["criado", "possivel_duplicado"])
        self.assertEqual(Participante.objects.filter(nome_completo=DADOS["nome_completo"]).count(), 1)
