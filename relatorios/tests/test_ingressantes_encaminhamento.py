from datetime import date
from importlib import import_module
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from participantes.models import Movimentacao, MotivoDesligamento
from participantes.movimentacoes import movimentar_participante
from participantes.relatorios import ingressantes_por_encaminhamento_mensal
from participantes.services import CAMPOS_CADASTRO, cadastrar_participante, corrigir_participante
from participantes.tests.test_models import novo_participante
from participantes.tests.test_services import DADOS
from relatorios.services import consultar_ingressantes_encaminhamento_fmr, consultar_movimentacao_etaria_fmr


class IngressantesEncaminhamentoFMRTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="encaminhamento_fmr_ficticio")
        cls.grupo = Group.objects.get(name="Equipe")
        cls.usuario.groups.add(cls.grupo)
        cls.url = reverse("relatorios:fmr")

    def setUp(self):
        self.client.force_login(self.usuario)

    def pessoa(self, origem="cras", entrada=date(2024, 2, 1)):
        self.sequencia = getattr(self, "sequencia", 0) + 1
        return cadastrar_participante(usuario=self.usuario, data_entrada=entrada,
            **(DADOS | {"nome_completo": f"Pessoa Fictícia Encaminhamento {self.sequencia}",
                        "origem_encaminhamento": origem}))

    def consultar(self, **extras):
        return consultar_ingressantes_encaminhamento_fmr(**({"usuario": self.usuario, "ano": 2024, "mes": 2} | extras))

    def contagens(self, dados):
        return {linha["codigo"]: linha["quantidade"] for linha in dados["linhas"]}

    def corrigir_origem(self, pessoa, origem):
        dados = {campo: getattr(pessoa, campo) for campo in CAMPOS_CADASTRO}
        return corrigir_participante(usuario=self.usuario, participante_id=pessoa.pk,
            data_entrada=pessoa.data_entrada, **(dados | {"origem_encaminhamento": origem}))

    def test_conta_por_origem_separa_outra_origem_e_confere_com_ingressos_rf05(self):
        for origem in ("cras", "cras", "creas", "rede", "outra"):
            self.pessoa(origem)
        dados = self.consultar()
        self.assertEqual(self.contagens(dados), {"cras": 2, "creas": 1, "rede": 1})
        self.assertEqual(dados["total"], 4)
        self.assertEqual(dados["outras_origens"], 1)
        self.assertEqual(dados["sem_origem"], 0)
        self.assertEqual(dados["total_ingressantes"], 5)
        etaria = consultar_movimentacao_etaria_fmr(usuario=self.usuario, ano=2024, mes=2)
        self.assertEqual(dados["total_ingressantes"], etaria["totais"]["ingressaram"])

    def test_correcao_do_cadastro_nao_reclassifica_ingresso_original(self):
        pessoa = self.pessoa()
        self.corrigir_origem(pessoa, "creas")
        pessoa.refresh_from_db()
        self.assertEqual(pessoa.origem_encaminhamento, "creas")
        self.assertEqual(pessoa.movimentacoes.get(tipo="entrada").origem_entrada, "cras")
        self.assertEqual(self.contagens(self.consultar()), {"cras": 1, "creas": 0, "rede": 0})

    def test_intervalo_inclusivo_bissexto_usa_entrada_e_nao_data_do_cadastro(self):
        for entrada in (date(2024, 1, 31), date(2024, 2, 1), date(2024, 2, 29), date(2024, 3, 1)):
            self.pessoa(entrada=entrada)
        self.assertEqual(self.consultar()["total_ingressantes"], 2)
        self.assertEqual(self.consultar(mes=1)["total_ingressantes"], 1)
        self.assertEqual(self.consultar(mes=3)["total_ingressantes"], 1)
        self.assertEqual(self.consultar(ano=2023)["total_ingressantes"], 0)

    def test_saida_posterior_nao_apaga_ingresso_reativacao_e_afastamento_nao_criam_outro(self):
        pessoa = self.pessoa()
        motivo = MotivoDesligamento.objects.get(descricao="Desistência")
        for tipo, dia in (("desligamento", 2), ("reativacao", 3), ("afastamento", 4), ("retorno", 5), ("desligamento", 6)):
            movimentar_participante(usuario=self.usuario, participante_id=pessoa.pk, tipo=tipo,
                data=date(2024, 2, dia), motivo_id=motivo.pk if tipo == "desligamento" else None)
        self.assertEqual(self.consultar()["total_ingressantes"], 1)
        movimentar_participante(usuario=self.usuario, participante_id=pessoa.pk, tipo="reativacao", data=date(2024, 3, 1))
        self.assertEqual(self.consultar(mes=3)["total_ingressantes"], 0)

    def test_sem_origem_historica_nao_presume_valor_atual_nem_zero(self):
        pessoa = novo_participante(origem_encaminhamento="cras")
        pessoa.save()
        Movimentacao.objects.create(participante=pessoa, tipo="entrada", data=date(2024, 2, 1), usuario=self.usuario)
        dados = self.consultar()
        self.assertEqual(dados["total_ingressantes"], 1)
        self.assertEqual(dados["sem_origem"], 1)
        self.assertIsNone(dados["total"])
        self.assertTrue(all(linha["quantidade"] is None for linha in dados["linhas"]))
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Há ingressantes sem origem histórica do encaminhamento.")
        self.assertContains(resposta, 'title="A origem precisa estar registrada na entrada')
        self.assertNotContains(resposta, 'id="tabela-ingressantes-encaminhamento"')

    def test_cadastro_sem_entrada_nao_vira_mes_vazio(self):
        pessoa = novo_participante()
        pessoa.save()
        self.assertIsNone(ingressantes_por_encaminhamento_mensal(usuario=self.usuario, ano=2024, mes=2))
        dados = self.consultar()
        self.assertIsNone(dados["total"])
        self.assertEqual(dados["pendencias"][0]["codigo"], "ENTRADA")
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Faltam datas de entrada")
        self.assertNotContains(resposta, "Total de novos ingressantes no mês:")

    def test_migration_recupera_original_auditado_e_preserva_desconhecido_e_snapshot_existente(self):
        pessoa = self.pessoa()
        self.corrigir_origem(pessoa, "creas")
        entrada = pessoa.movimentacoes.get(tipo="entrada")
        Movimentacao.objects.filter(pk=entrada.pk).update(origem_entrada="")
        sem_prova = novo_participante(origem_encaminhamento="rede")
        sem_prova.save()
        legado = Movimentacao.objects.create(participante=sem_prova, tipo="entrada", data=date(2024, 2, 1), usuario=self.usuario)
        migration = import_module("participantes.migrations.0011_origem_entrada_fmr")
        migration.recuperar_origem_auditada(apps, connection.schema_editor())
        entrada.refresh_from_db()
        legado.refresh_from_db()
        self.assertEqual(entrada.origem_entrada, "cras")
        self.assertEqual(legado.origem_entrada, "")
        Movimentacao.objects.filter(pk=entrada.pk).update(origem_entrada="outra")
        migration.recuperar_origem_auditada(apps, connection.schema_editor())
        entrada.refresh_from_db()
        self.assertEqual(entrada.origem_entrada, "outra")

    def test_banco_rejeita_origem_invalida_ou_em_evento_que_nao_e_entrada(self):
        pessoa = self.pessoa()
        entrada = pessoa.movimentacoes.get(tipo="entrada")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Movimentacao.objects.filter(pk=entrada.pk).update(origem_entrada="invalida")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Movimentacao.objects.create(participante=pessoa, tipo="afastamento", data=date(2024, 2, 2),
                                       usuario=self.usuario, origem_entrada="cras")

    def test_mes_vazio_mostra_tres_zeros_e_consulta_nao_escreve(self):
        with CaptureQueriesContext(connection) as consultas:
            dados = self.consultar()
        self.assertEqual(self.contagens(dados), {"cras": 0, "creas": 0, "rede": 0})
        self.assertEqual((dados["total"], dados["outras_origens"], dados["total_ingressantes"]), (0, 0, 0))
        self.assertTrue(all(q["sql"].upper().startswith("SELECT") for q in consultas))
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, 'id="tabela-ingressantes-encaminhamento"')
        self.assertContains(resposta, "Encaminhamentos dos ingressantes do mês 02/2024")
        self.assertContains(resposta, "Outros serviços da rede socioassistencial")
        secao = resposta.content.decode().split('aria-labelledby="ingressantes-encaminhamento"')[1].split("</section>")[0]
        self.assertNotIn("Total encaminhado pela rede", secao)
        self.assertNotIn("Total de novos ingressantes", secao)
        self.assertContains(resposta, "Correções posteriores no cadastro não alteram")

    def test_permissao_atual_exigida_na_fonte_e_consumidor(self):
        self.consultar()
        permissao = Permission.objects.get(content_type__app_label="participantes", codename="view_participante")
        self.grupo.permissions.remove(permissao)
        with self.assertRaises(PermissionDenied):
            ingressantes_por_encaminhamento_mensal(usuario=self.usuario, ano=2024, mes=2)
        with patch("relatorios.integracoes.participantes.consultar_ingressantes_encaminhamento") as fonte:
            dados = self.consultar()
        fonte.assert_not_called()
        self.assertIsNone(dados["total"])
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Seu perfil não possui permissão para consultar os ingressantes por encaminhamento.")
        self.assertNotContains(resposta, 'id="tabela-ingressantes-encaminhamento"')

    def test_secao_independe_de_permissoes_de_atividades(self):
        self.grupo.permissions.remove(*Permission.objects.filter(content_type__app_label="atividades"))
        self.assertContains(self.client.get(self.url, {"mes": "2024-02"}), 'id="tabela-ingressantes-encaminhamento"')

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
            ingressantes_por_encaminhamento_mensal(usuario=self.usuario, ano=2024, mes=2)
        with self.assertRaises(PermissionDenied):
            self.consultar(usuario=AnonymousUser())
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_periodo_validado_no_servico_e_na_fonte_e_formulario_invalido(self):
        for consulta in (self.consultar, ingressantes_por_encaminhamento_mensal):
            for ano, mes in ((True, 2), (2024, False), (0, 1), (10000, 1), (2024, 0), (2024, 13), (2024, "2")):
                with self.subTest(ano=ano, mes=mes), self.assertRaises(ValidationError):
                    consulta(usuario=self.usuario, ano=ano, mes=mes)
        for ano, mes in ((1, 1), (9999, 12)):
            self.assertEqual(self.consultar(ano=ano, mes=mes)["total_ingressantes"], 0)
        with patch("relatorios.services.consultar_ingressantes_encaminhamento_fmr") as servico:
            resposta = self.client.get(self.url, {"mes": "2024-13"})
        servico.assert_not_called()
        self.assertNotContains(resposta, 'id="ingressantes-encaminhamento"')
