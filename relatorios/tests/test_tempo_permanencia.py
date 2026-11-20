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
from participantes.relatorios import tempo_permanencia_desligamentos_mensal
from participantes.tests.test_models import novo_participante
from relatorios.services import consultar_desligamentos_motivo_fmr, consultar_tempo_permanencia_fmr


class TempoPermanenciaFMRTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="tempo_fmr_ficticio")
        cls.grupo = Group.objects.get(name="Equipe")
        cls.usuario.groups.add(cls.grupo)
        cls.motivo = MotivoDesligamento.objects.get(descricao="Desistência")
        cls.url = reverse("relatorios:fmr")

    def setUp(self):
        self.client.force_login(self.usuario)

    def consultar(self, **extras):
        return consultar_tempo_permanencia_fmr(**({"usuario": self.usuario, "ano": 2024, "mes": 2} | extras))

    def quantidades(self, dados):
        return [linha["quantidade"] for linha in dados["linhas"]]

    def pessoa(self, entrada):
        pessoa = novo_participante()
        pessoa.save()
        if entrada is not None:
            Movimentacao.objects.create(participante=pessoa, tipo="entrada", data=entrada, usuario=self.usuario)
        return pessoa

    def mover(self, pessoa, tipo, dia):
        return movimentar_participante(usuario=self.usuario, participante_id=pessoa.pk, tipo=tipo,
            data=dia, motivo_id=self.motivo.pk if tipo == "desligamento" else None)

    def sair(self, entrada, saida):
        pessoa = self.pessoa(entrada)
        self.mover(pessoa, "desligamento", saida)
        return pessoa

    def test_limites_exatos_e_dia_seguinte_sem_sobreposicao(self):
        for entrada, saida in ((date(2023, 8, 29), date(2024, 2, 29)),
                              (date(2023, 8, 28), date(2024, 2, 29)),
                              (date(2023, 2, 28), date(2024, 2, 28)),
                              (date(2023, 2, 27), date(2024, 2, 28)),
                              (date(2021, 2, 28), date(2024, 2, 28)),
                              (date(2021, 2, 27), date(2024, 2, 28))):
            self.sair(entrada, saida)
        dados = self.consultar()
        self.assertEqual(self.quantidades(dados), [1, 2, 2, 1])
        self.assertEqual(sum(self.quantidades(dados)), dados["total_desligamentos"])
        motivos = consultar_desligamentos_motivo_fmr(usuario=self.usuario, ano=2024, mes=2)
        self.assertEqual(dados["total"], motivos["total"])

    def test_meses_de_calendario_fim_de_mes_e_aniversario_bissexto(self):
        self.sair(date(2023, 8, 31), date(2024, 2, 29))
        self.sair(date(2023, 8, 31), date(2024, 3, 1))
        self.sair(date(2020, 2, 29), date(2021, 2, 28))
        self.sair(date(2020, 2, 29), date(2021, 3, 1))
        self.assertEqual(self.quantidades(self.consultar()), [1, 0, 0, 0])
        self.assertEqual(self.quantidades(self.consultar(mes=3)), [0, 1, 0, 0])
        self.assertEqual(self.quantidades(self.consultar(ano=2021)), [0, 1, 0, 0])
        self.assertEqual(self.quantidades(self.consultar(ano=2021, mes=3)), [0, 0, 1, 0])

    def test_ciclos_e_eventos_no_mesmo_dia_usam_inicio_anterior_a_cada_saida(self):
        pessoa = self.sair(date(2010, 1, 1), date(2024, 2, 1))
        self.mover(pessoa, "reativacao", date(2024, 2, 1))
        self.mover(pessoa, "desligamento", date(2024, 2, 1))
        self.mover(pessoa, "reativacao", date(2024, 2, 1))
        dados = self.consultar()
        self.assertEqual(self.quantidades(dados), [1, 0, 0, 1])
        self.assertEqual(dados["total"], 2)

    def test_afastamento_e_retorno_nao_reiniciam_vinculo(self):
        pessoa = self.pessoa(date(2020, 1, 1))
        self.mover(pessoa, "afastamento", date(2024, 1, 10))
        self.mover(pessoa, "retorno", date(2024, 2, 1))
        self.mover(pessoa, "desligamento", date(2024, 2, 28))
        self.assertEqual(self.quantidades(self.consultar()), [0, 0, 0, 1])

    def test_mes_de_saida_inclusivo_e_estado_atual_nao_reclassifica_passado(self):
        for saida in (date(2024, 1, 31), date(2024, 2, 1), date(2024, 2, 29), date(2024, 3, 1)):
            pessoa = self.sair(date(2024, 1, 1), saida)
            self.mover(pessoa, "reativacao", date(2024, 4, 1))
        self.assertEqual(self.consultar()["total"], 2)
        self.assertEqual(self.consultar(mes=1)["total"], 1)
        self.assertEqual(self.consultar(mes=3)["total"], 1)
        self.assertEqual(self.consultar(mes=4)["total"], 0)

    def test_saida_sem_inicio_nao_presume_data_nem_totais_parciais(self):
        pessoa = self.pessoa(None)
        Movimentacao.objects.create(participante=pessoa, tipo="desligamento", data=date(2024, 2, 1),
            usuario=self.usuario, motivo=self.motivo, motivo_descricao=self.motivo.descricao)
        self.sair(date(2024, 1, 1), date(2024, 2, 1))
        dados = self.consultar()
        self.assertEqual(dados["total_desligamentos"], 2)
        self.assertEqual(dados["sem_periodo"], 1)
        self.assertEqual(self.quantidades(dados), [None] * 4)
        self.assertIsNone(dados["total"])
        self.assertEqual(dados["pendencia"]["codigo"], "VINCULO")

    def test_duas_saidas_sem_reativacao_nao_reusam_a_mesma_entrada(self):
        pessoa = self.sair(date(2024, 1, 1), date(2024, 2, 1))
        Movimentacao.objects.create(participante=pessoa, tipo="desligamento", data=date(2024, 2, 2),
            usuario=self.usuario, motivo=self.motivo, motivo_descricao=self.motivo.descricao)
        dados = self.consultar()
        self.assertEqual(dados["sem_periodo"], 1)
        self.assertIsNone(dados["total"])

    def test_mes_sem_saidas_mostra_quatro_zeros_e_consulta_nao_escreve(self):
        self.pessoa(date(2024, 1, 1))
        with CaptureQueriesContext(connection) as consultas:
            dados = self.consultar()
        self.assertEqual(self.quantidades(dados), [0, 0, 0, 0])
        self.assertEqual(dados["total"], 0)
        self.assertTrue(all(q["sql"].upper().startswith("SELECT") for q in consultas))

    def test_interface_faixas_total_limites_e_pendencia_acessivel(self):
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, 'id="tabela-tempo-permanencia"')
        self.assertContains(resposta, "por tempo de permanência em 02/2024")
        for faixa in ("Até 6 meses", "Entre 6 meses a 1 ano", "Entre 1 ano a 3 anos", "Mais de 3 anos"):
            self.assertContains(resposta, faixa)
        self.assertContains(resposta, "exatamente 6 meses")
        pessoa = self.pessoa(None)
        Movimentacao.objects.create(participante=pessoa, tipo="desligamento", data=date(2024, 2, 1),
            usuario=self.usuario, motivo=self.motivo, motivo_descricao=self.motivo.descricao)
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, 'title="É necessário identificar a entrada')
        self.assertContains(resposta, 'aria-describedby="tempo-pendencia-vinculo"')
        self.assertContains(resposta, "Não calculado")

    def test_permissao_atual_exigida_na_fonte_e_consumidor(self):
        self.consultar()
        self.grupo.permissions.remove(Permission.objects.get(content_type__app_label="participantes", codename="view_participante"))
        with self.assertRaises(PermissionDenied):
            tempo_permanencia_desligamentos_mensal(usuario=self.usuario, ano=2024, mes=2)
        with patch("relatorios.integracoes.participantes.consultar_tempo_permanencia_desligamentos") as fonte:
            dados = self.consultar()
        fonte.assert_not_called()
        self.assertIsNone(dados["total"])
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Seu perfil não possui permissão para consultar o tempo de permanência")
        self.assertNotContains(resposta, 'id="tabela-tempo-permanencia"')

    def test_independente_de_permissoes_de_atividades(self):
        self.grupo.permissions.remove(*Permission.objects.filter(content_type__app_label="atividades"))
        self.assertContains(self.client.get(self.url, {"mes": "2024-02"}), 'id="tabela-tempo-permanencia"')

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
            tempo_permanencia_desligamentos_mensal(usuario=self.usuario, ano=2024, mes=2)
        with self.assertRaises(PermissionDenied):
            self.consultar(usuario=AnonymousUser())
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_periodo_validado_e_limites_de_ano(self):
        for consulta in (self.consultar, tempo_permanencia_desligamentos_mensal):
            for ano, mes in ((True, 2), (2024, False), (0, 1), (10000, 1), (2024, 0), (2024, 13), ("2024", 2)):
                with self.subTest(ano=ano, mes=mes), self.assertRaises(ValidationError):
                    consulta(usuario=self.usuario, ano=ano, mes=mes)
        for ano, mes in ((1, 1), (9999, 12)):
            self.assertEqual(self.consultar(ano=ano, mes=mes)["total"], 0)
        with patch("relatorios.services.consultar_tempo_permanencia_fmr") as servico:
            resposta = self.client.get(self.url, {"mes": "2024-13"})
        servico.assert_not_called()
        self.assertNotContains(resposta, 'id="tempo-permanencia"')
