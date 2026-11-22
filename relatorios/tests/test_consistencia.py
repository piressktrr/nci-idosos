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
            "perfil_demografico": {"blocos": [
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
        for bloco in self.dados["perfil_demografico"]["blocos"]:
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


class ConsistenciaPortalEFaixasTests(SimpleTestCase):
    """RN-FMR-01 na forma do portal (Q4) e tabela etária + fora das faixas = totais dos outros blocos."""

    def setUp(self):
        zeros = dict.fromkeys(("vieram_mes_anterior", "ingressaram", "reativados", "ingressaram_portal",
                               "sairam", "permanecem"), 0)
        self.dados = {
            "permanentes": {"total": 3, "cadastros_pendentes": []},
            "movimentacao_etaria": {
                "linhas": [{"faixa": "60–64", "sexo": "Feminino", "vieram_mes_anterior": 2, "ingressaram": 0,
                            "reativados": 1, "ingressaram_portal": 1, "sairam": 1, "permanecem": 2}],
                "totais": {**zeros, "vieram_mes_anterior": 2, "reativados": 1, "ingressaram_portal": 1,
                           "sairam": 1, "permanecem": 2},
                "fora_faixas": {**zeros, "vieram_mes_anterior": 1, "ingressaram": 1, "ingressaram_portal": 1,
                                "sairam": 1, "permanecem": 1},
            },
            "ingressantes_encaminhamento": {"total_ingressantes": 1},
            "tempo_permanencia": {"total_desligamentos": 2, "total": 2, "linhas": [{"quantidade": 2}]},
            "desligamentos_motivo": {"total": 2, "linhas": [{"quantidade": 2}]},
            "situacao_social": {"linhas": []},
            "perfil_demografico": {"blocos": []},
        }

    def campos(self):
        return [aviso["campo"] for aviso in verificar_consistencia(self.dados)]

    def test_tabela_mais_menores_de_60_confere_com_os_outros_blocos(self):
        self.assertEqual(self.campos(), [])

    def test_menores_de_60_esquecidos_geram_aviso_em_cada_total(self):
        fora = self.dados["movimentacao_etaria"]["fora_faixas"]
        fora.update(permanecem=0, sairam=0, ingressaram=0, ingressaram_portal=0)
        avisos = verificar_consistencia(self.dados)
        self.assertCountEqual([a["campo"] for a in avisos], [
            "Movimentação · total de Permanecem", "Movimentação · total de Saíram",
            "Movimentação · total de Ingressaram"])
        self.assertIn("A tabela por faixa (2) mais os menores de 60 anos (0) somam 2", avisos[0]["mensagem"])

    def test_cadastros_pendentes_aparecem_como_explicacao_possivel(self):
        self.dados["desligamentos_motivo"]["total"] = 3
        self.dados["permanentes"]["cadastros_pendentes"] = [{"nome": "Ficticio", "motivo": "sem entrada"}]
        aviso = verificar_consistencia(self.dados)[0]
        self.assertEqual(aviso["campo"], "Movimentação · total de Saíram")
        self.assertIn("1 cadastro(s) fora do cálculo", aviso["mensagem"])

    def test_equacao_do_portal_com_reativados_em_ingressaram(self):
        linha = self.dados["movimentacao_etaria"]["linhas"][0]
        linha["permanecem"] = 1  # vieram 2 + ingressaram (portal) 1 − saíram 1 = 2, não 1
        avisos = verificar_consistencia(self.dados)
        self.assertIn("vieram + ingressaram (portal) − saíram = 2 + 1 − 1 = 2", avisos[0]["mensagem"])

    def test_ingressaram_portal_diferente_da_soma_gera_aviso(self):
        self.dados["movimentacao_etaria"]["linhas"][0]["ingressaram_portal"] = 0
        mensagens = [a["mensagem"] for a in verificar_consistencia(self.dados)]
        self.assertTrue(any("deve ser ingressaram + reativados = 1" in m for m in mensagens), mensagens)

    def test_valores_ausentes_nao_geram_conferencia(self):
        self.dados["movimentacao_etaria"]["totais"] = dict.fromkeys(self.dados["movimentacao_etaria"]["totais"])
        self.dados["ingressantes_encaminhamento"] = {}
        self.dados["permanentes"]["total"] = None
        self.dados["desligamentos_motivo"]["total"] = 99
        self.assertNotIn("Movimentação · total de Saíram", self.campos())

    def test_categorias_repartem_aulas_e_presencas_do_mes(self):
        self.dados["indicadores"] = [{"codigo": "aulas_realizadas", "valor": 3}, {"codigo": "participacoes", "valor": 5}]
        self.dados["categorias_atividades"] = {"total_aulas": 3, "total_participacoes": 5}
        self.assertEqual(self.campos(), [])
        self.dados["categorias_atividades"] = {"total_aulas": 2, "total_participacoes": 5}
        self.assertEqual(self.campos(), ["Aulas por categoria"])
        self.dados["categorias_atividades"] = {"total_aulas": None, "total_participacoes": None}
        self.assertEqual(self.campos(), [])


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class MenoresDe60NaTelaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from participantes.models import PerfilDemografico
        cls.usuario = get_user_model().objects.create_user(username="menores_60_ficticio")
        cls.usuario.groups.add(Group.objects.get(name="Equipe"))
        for nascimento in (date(1950, 1, 1), date(1990, 1, 1), date(1985, 6, 1)):
            pessoa = novo_participante(data_nascimento=nascimento)
            pessoa.save()
            Movimentacao.objects.create(participante=pessoa, tipo="entrada", data=date(2024, 1, 10), usuario=cls.usuario)
            PerfilDemografico.objects.create(participante=pessoa, vigente_desde=date(2024, 1, 10), sexo="F",
                                             raca_cor="parda", identidade_genero="cisgenero")

    def test_aviso_explicito_e_ninguem_sai_dos_outros_blocos(self):
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("relatorios:fmr"), {"mes": "2024-02"})
        self.assertContains(resposta, "2 participante(s) do mês com menos de 60 anos em 01/02/2024")
        self.assertContains(resposta, "provável erro na data de nascimento")
        contexto = resposta.context
        self.assertEqual(contexto["permanentes"]["total"], 3)
        self.assertEqual(contexto["movimentacao_etaria"]["totais"]["permanecem"], 1)
        self.assertEqual(contexto["movimentacao_etaria"]["fora_faixas"]["permanecem"], 2)
        self.assertEqual(contexto["perfil_demografico"]["blocos"][0]["total"], 3)
        self.assertNotIn("Movimentação · total de Permanecem",
                         [aviso["campo"] for aviso in contexto["avisos_consistencia"]])
