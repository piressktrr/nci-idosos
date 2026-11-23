from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from participantes.models import Movimentacao, MotivoDesligamento
from participantes.movimentacoes import movimentar_participante
from participantes.relatorios import imigrantes_refugiados_mensal
from participantes.services import cadastrar_participante, corrigir_participante, registrar_situacao_social
from participantes.tests.test_models import dados_participante, novo_participante
from relatorios.services import consultar_perfil_demografico_fmr


class PerfilDemograficoFMRTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="demografico_fmr_ficticio")
        cls.grupo = Group.objects.get(name="Equipe")
        cls.usuario.groups.add(cls.grupo)
        cls.url = reverse("relatorios:fmr")

    def setUp(self):
        self.client.force_login(self.usuario)

    def consultar(self, **extras):
        return consultar_perfil_demografico_fmr(**({"usuario": self.usuario, "ano": 2024, "mes": 2} | extras))

    def pessoa(self, entrada=date(2024, 1, 1)):
        pessoa = novo_participante()
        pessoa.save()
        Movimentacao.objects.create(participante=pessoa, tipo="entrada", data=entrada, usuario=self.usuario)
        return pessoa

    def situacao(self, pessoa, imigrante=True, desde=date(2024, 1, 1)):
        return registrar_situacao_social(usuario=self.usuario, participante_id=pessoa.pk, vigente_desde=desde,
            imigrante_refugiado=imigrante, mora_sozinho=False, tem_apoio=False, possui_deficiencia=False, recebe_bpc=False)

    def mover(self, pessoa, tipo, dia):
        motivo = MotivoDesligamento.objects.get(descricao="Desistência")
        return movimentar_participante(usuario=self.usuario, participante_id=pessoa.pk, tipo=tipo,
            data=dia, motivo_id=motivo.pk if tipo == "desligamento" else None)

    def test_usa_situacao_vigente_no_fechamento_e_nao_a_mais_recente(self):
        pessoa = self.pessoa()
        self.situacao(pessoa)
        self.situacao(pessoa, False, date(2024, 3, 1))
        self.assertEqual(self.consultar()["imigrantes_refugiados"], 1)
        self.assertEqual(self.consultar(mes=3)["imigrantes_refugiados"], 0)
        self.assertEqual(self.consultar()["periodo"]["fim"], date(2024, 2, 29))

    def test_situacao_no_ultimo_dia_inclusive_e_correcao_com_mesma_vigencia(self):
        pessoa = self.pessoa()
        self.situacao(pessoa, True, date(2024, 2, 29))
        self.assertEqual(self.consultar()["imigrantes_refugiados"], 1)
        self.situacao(pessoa, False, date(2024, 2, 29))
        self.assertEqual(self.consultar()["imigrantes_refugiados"], 0)

    def test_populacao_do_fechamento_preserva_mes_antigo_afastado_e_reativado(self):
        saida_futura = self.pessoa()
        self.situacao(saida_futura)
        self.mover(saida_futura, "desligamento", date(2024, 3, 1))
        desligado = self.pessoa()
        self.situacao(desligado)
        self.mover(desligado, "desligamento", date(2024, 2, 29))
        reativado = self.pessoa()
        self.situacao(reativado)
        self.mover(reativado, "desligamento", date(2024, 1, 31))
        self.mover(reativado, "reativacao", date(2024, 2, 29))
        afastado = self.pessoa()
        self.situacao(afastado, False)
        self.mover(afastado, "afastamento", date(2024, 2, 1))
        self.pessoa(entrada=date(2024, 3, 1))  # Não permanece em fevereiro, mesmo sem situação.
        dados = self.consultar()
        self.assertEqual((dados["total_permanentes"], dados["imigrantes_refugiados"], dados["sem_situacao"]), (3, 2, 0))

    def test_falta_de_situacao_nao_e_false_e_situacao_posterior_nao_completa_passado(self):
        self.situacao(self.pessoa())
        self.situacao(self.pessoa(), False, date(2024, 3, 1))
        dados = self.consultar()
        self.assertIsNone(dados["imigrantes_refugiados"])
        self.assertEqual(dados["sem_situacao"], 1)
        self.assertEqual(dados["pendencia_imigrantes"]["codigo"], "IMIGRANTE")
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Participantes sem informação vigente: 1")
        self.assertNotContains(resposta, 'id="quantidade-imigrantes-refugiados"')

    def test_historico_incompleto_ou_status_legado_fica_fora_sem_anular_o_mes(self):
        # Antes: um cadastro Inativo ou sem entrada anulava a contagem (None). Agora ele fica fora do cálculo
        # (listado como pendente na tela) e os cadastros completos continuam contados.
        self.situacao(self.pessoa())
        pessoa = self.pessoa()
        pessoa.status = "inativo"
        pessoa.save(update_fields=["status"])
        self.assertEqual(imigrantes_refugiados_mensal(usuario=self.usuario, ano=2024, mes=2)["total_permanentes"], 1)
        self.assertIsNone(self.consultar()["pendencia_imigrantes"])
        self.assertEqual(self.consultar()["imigrantes_refugiados"], 1)
        pessoa.status = "ativo"
        pessoa.save(update_fields=["status"])
        pessoa.movimentacoes.all().delete()
        self.assertEqual(self.consultar()["imigrantes_refugiados"], 1)

    def test_mes_vazio_e_situacao_negativa_sao_zeros_reais(self):
        self.assertEqual(self.consultar()["imigrantes_refugiados"], 0)
        self.situacao(self.pessoa(), False)
        dados = self.consultar()
        self.assertEqual(dados["imigrantes_refugiados"], 0)
        self.assertIsNone(dados["pendencia_imigrantes"])
        self.assertContains(self.client.get(self.url, {"mes": "2024-02"}), 'id="quantidade-imigrantes-refugiados"')

    def test_estrutura_oficial_de_raca_e_genero_sem_calculo_ou_inferencia(self):
        pessoa = self.pessoa()  # Cadastro atual contém raça e gênero; não substitui vigência.
        self.situacao(pessoa)
        blocos = {bloco["codigo"]: bloco for bloco in self.consultar()["blocos_pendentes"]}
        self.assertEqual(blocos["RACA-COR"]["colunas"], ["Branca", "Preta", "Pardo", "Amarela", "Indígena", "Não informada", "Total"])
        self.assertEqual([linha["rotulo"] for linha in blocos["RACA-COR"]["linhas"]], ["Feminino", "Masculino", "Total"])
        self.assertEqual([linha["rotulo"] for linha in blocos["GENERO"]["linhas"]],
                         ["Cisgênero", "Transgênero", "Agênero", "Não declarado", "Total"])
        for bloco in blocos.values():
            self.assertIsNone(bloco["total"])
            for linha in bloco["linhas"] or []:
                self.assertTrue(all(valor is None for valor in linha["valores"]))
        self.assertIsNone(blocos["REGIAO"]["linhas"])

    def test_interface_exibe_tabelas_oficiais_pendencias_tooltips_e_referencia(self):
        self.pessoa()
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Perfil demográfico dos participantes")
        self.assertContains(resposta, "em 29/02/2024")
        self.assertContains(resposta, 'id="demografico-tabela-RACA-COR"')
        self.assertContains(resposta, 'id="demografico-tabela-GENERO"')
        self.assertContains(resposta, "Agênero")
        self.assertContains(resposta, "Não declarado")
        self.assertContains(resposta, "Não informada")
        self.assertContains(resposta, "Não calculado")
        self.assertContains(resposta, "diferente de zero")
        self.assertContains(resposta, 'title="O NCI decidiu (Q6, 20/11) registrar por ora só o endereço completo')
        self.assertContains(resposta, 'aria-describedby="demografico-pendencia-REGIAO"')
        self.assertContains(resposta, 'tabindex="0"')

    def test_fechamento_le_vigencia_e_preserva_mes_anterior(self):
        entrada = date(2024, 1, 1)
        cadastro = dados_participante(telefone_residencial="", observacao_encaminhamento="")
        pessoa = cadastrar_participante(usuario=self.usuario, data_entrada=entrada, **cadastro)
        corrigir_participante(usuario=self.usuario, participante_id=pessoa.pk, data_entrada=entrada,
            perfil_vigente_desde=date(2024, 3, 1), **(cadastro | {"raca_cor": "preta", "identidade_genero": "agenero"}))
        fevereiro = self.consultar()
        marco = self.consultar(mes=3)
        self.assertEqual(fevereiro["blocos"][0]["linhas"][0]["valores"], [0, 0, 1, 0, 0, 0, 1])
        self.assertEqual(marco["blocos"][0]["linhas"][0]["valores"], [0, 1, 0, 0, 0, 0, 1])
        self.assertEqual(fevereiro["blocos"][1]["linhas"][0]["valores"], [1])
        self.assertEqual(marco["blocos"][1]["linhas"][2]["valores"], [1])
        self.assertEqual([bloco["codigo"] for bloco in marco["blocos_pendentes"]], ["REGIAO"])
        self.mover(pessoa, "desligamento", date(2024, 4, 30))
        self.assertEqual(self.consultar(mes=4)["blocos"][1]["total"], 0)

    def test_origem_retorna_apenas_agregados_e_nenhuma_escrita(self):
        self.situacao(self.pessoa())
        with CaptureQueriesContext(connection) as consultas:
            dados = imigrantes_refugiados_mensal(usuario=self.usuario, ano=2024, mes=2)
        self.assertEqual(dados, {"total_permanentes": 1, "imigrantes_refugiados": 1, "sem_situacao": 0})
        self.assertTrue(all(q["sql"].upper().startswith("SELECT") for q in consultas))

    def test_permissao_atual_na_fonte_e_consumidor_sem_expor_blocos(self):
        self.consultar()
        permissao = Permission.objects.get(content_type__app_label="participantes", codename="view_participante")
        self.grupo.permissions.remove(permissao)
        with self.assertRaises(PermissionDenied):
            imigrantes_refugiados_mensal(usuario=self.usuario, ano=2024, mes=2)
        with patch("relatorios.integracoes.participantes.consultar_imigrantes_refugiados") as fonte:
            dados = self.consultar()
        fonte.assert_not_called()
        self.assertEqual(dados["blocos_pendentes"], [])
        self.assertIsNone(dados["imigrantes_refugiados"])
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Seu perfil não possui permissão para consultar o perfil demográfico")
        self.assertNotContains(resposta, 'id="demografico-tabela-RACA-COR"')

    def test_secao_independente_das_permissoes_de_atividades(self):
        self.grupo.permissions.remove(*Permission.objects.filter(content_type__app_label="atividades"))
        self.assertContains(self.client.get(self.url, {"mes": "2024-02"}), 'id="perfil-demografico"')

    def test_perfil_conta_ativa_login_e_metodo_get(self):
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.usuario.groups.clear()
        with self.assertRaises(PermissionDenied):
            self.consultar()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.usuario.groups.add(self.grupo)
        get_user_model().objects.filter(pk=self.usuario.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.consultar()
        with self.assertRaises(PermissionDenied):
            imigrantes_refugiados_mensal(usuario=self.usuario, ano=2024, mes=2)
        with self.assertRaises(PermissionDenied):
            self.consultar(usuario=AnonymousUser())
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_periodo_validado_limites_e_mes_invalido_sem_consulta(self):
        for consulta in (self.consultar, imigrantes_refugiados_mensal):
            for ano, mes in ((True, 2), (2024, False), (0, 1), (10000, 1), (2024, 0), (2024, 13), ("2024", 2)):
                with self.subTest(ano=ano, mes=mes), self.assertRaises(ValidationError):
                    consulta(usuario=self.usuario, ano=ano, mes=mes)
        for ano, mes in ((1, 1), (9999, 12)):
            self.assertEqual(self.consultar(ano=ano, mes=mes)["imigrantes_refugiados"], 0)
        with patch("relatorios.services.consultar_perfil_demografico_fmr") as servico:
            resposta = self.client.get(self.url, {"mes": "2024-13"})
        servico.assert_not_called()
        self.assertNotContains(resposta, 'id="perfil-demografico"')
