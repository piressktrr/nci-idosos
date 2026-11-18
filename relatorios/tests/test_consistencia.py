from copy import deepcopy
from datetime import date, time

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from atividades.models import Atividade, Aula, Frequencia, Inscricao
from participantes.models import Movimentacao
from participantes.tests.test_models import novo_participante
from relatorios.consistencia import verificar_consistencia


class ConsistenciaTests(SimpleTestCase):
    def setUp(self):
        self.dados = {
            "permanentes": {"total": 1},
            "movimentacao_etaria": {"linhas": [
                {"faixa": "60–64", "sexo": "Feminino", "vieram_mes_anterior": 1,
                 "ingressaram": 0, "reativados": 1, "sairam": 1, "permanecem": 1}]},
            "tempo_permanencia": {"total_desligamentos": 2, "total": 2, "linhas": [{"quantidade": 2}]},
            "desligamentos_motivo": {"total": 2, "linhas": [{"quantidade": 2}]},
            "situacao_social": {"linhas": [
                {"codigo": "moram_sozinhos", "quantidade": 1},
                {"codigo": "moram_sozinhos_com_apoio", "quantidade": 1}]},
            "perfil_demografico": {"blocos_pendentes": [
                {"codigo": codigo, "titulo": titulo, "total": None}
                for codigo, titulo in (("REGIAO", "Região"), ("GENERO", "Gênero"), ("RACA-COR", "Sexo por raça/cor"))
            ]},
        }

    def campos(self):
        return [aviso["campo"] for aviso in verificar_consistencia(self.dados)]

    def test_saldo_com_reativacao_e_limites_iguais_sem_divergencia(self):
        self.assertEqual(self.campos(), [])

    def test_divergencias_independentes_com_valores_e_sem_mudar_indicadores(self):
        self.dados["movimentacao_etaria"]["linhas"][0]["permanecem"] = 2
        self.dados["tempo_permanencia"]["linhas"][0]["quantidade"] = 3
        self.dados["desligamentos_motivo"]["linhas"][0]["quantidade"] = 0
        self.dados["situacao_social"]["linhas"][0]["quantidade"] = 2
        self.dados["situacao_social"]["linhas"][1]["quantidade"] = 3
        for bloco in self.dados["perfil_demografico"]["blocos_pendentes"]:
            bloco["total"] = 0
        anterior = deepcopy(self.dados)
        self.assertCountEqual(self.campos(), [
            "Movimentação · 60–64 · Feminino", "Saídas por motivo", "Saídas por tempo de permanência",
            "Pessoas que moram sozinhas", "Apoio da família ou comunidade", "Região", "Gênero", "Sexo por raça/cor",
        ])
        self.assertEqual(self.dados, anterior)

    def test_falta_de_historico_nao_invalida_conferencias_independentes(self):
        self.dados["permanentes"]["total"] = None
        self.dados["tempo_permanencia"].update(total=None, linhas=[{"quantidade": None}])
        self.dados["desligamentos_motivo"]["total"] = 0
        self.dados["situacao_social"]["linhas"][0]["quantidade"] = 0
        self.assertCountEqual(self.campos(), ["Saídas por motivo", "Apoio da família ou comunidade"])

    def test_permanentes_negativos(self):
        self.dados["permanentes"]["total"] = -1
        self.assertIn("Permanentes", self.campos())


@override_settings(NCI_PARTICIPANTES_PROVIDER="participantes.provedor.ProvedorParticipantes")
class ConsistenciaNaTelaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="consistencia_ficticia")
        cls.equipe = Group.objects.get(name="Equipe")
        cls.usuario.groups.add(cls.equipe)
        cls.usuario.user_permissions.add(*Permission.objects.filter(content_type__app_label="atividades",
            codename__in=("view_atividade", "view_aula", "view_frequencia")))
        pessoa = novo_participante()
        pessoa.save()
        dia = date(2024, 2, 29)
        Movimentacao.objects.create(participante=pessoa, tipo="entrada", data=dia, usuario=cls.usuario)
        atividade = Atividade.objects.create(nome="Oficina fictícia", monitor="Equipe", local="Sala")
        inscricao = Inscricao.objects.create(atividade=atividade, origem_participante="participantes",
            participante_referencia=str(pessoa.pk), cadastrada_por=cls.usuario)
        for hora in (9, 11):
            aula = Aula.objects.create(atividade=atividade, data=dia, inicio=time(hora), fim=time(hora + 1))
            Frequencia.objects.create(aula=aula, inscricao=inscricao, situacao="presente")

    def consultar(self, mes="2024-02"):
        self.client.force_login(self.usuario)
        return self.client.get(reverse("relatorios:fmr"), {"mes": mes})

    def test_ocorrencias_exibidas_com_data_e_referencia_para_revisao(self):
        resposta = self.consultar()
        self.assertContains(resposta, 'href="#presencas-por-data">Presenças em 29/02/2024')
        self.assertContains(resposta, "A contagem do dia (2) supera o total de permanentes no fechamento (1)")
        self.assertEqual(resposta.context["presencas"]["total_participantes_unicos"], 1)
        self.assertEqual(resposta.context["presencas"]["total_ocorrencias"], 2)
        self.assertEqual(len(resposta.context["avisos_consistencia"]), 1)
        self.assertNotContains(self.consultar("2024-03"), 'id="avisos-consistencia"')

    @override_settings(NCI_FMR_CONTAGEM_DIARIA="participantes_unicos")
    def test_criterio_alternativo_compara_os_individuos_do_dia(self):
        self.assertNotContains(self.consultar(), 'id="avisos-consistencia"')

    def test_retirar_permissao_do_cadastro_oculta_comparacao_com_permanentes(self):
        self.equipe.permissions.remove(Permission.objects.get(content_type__app_label="participantes",
                                                              codename="view_participante"))
        resposta = self.consultar()
        self.assertNotContains(resposta, 'id="avisos-consistencia"')
        self.assertEqual(resposta.context["presencas"]["total_ocorrencias"], 2)
