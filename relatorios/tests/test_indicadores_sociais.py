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
from participantes.relatorios import indicadores_sociais_mensal
from participantes.services import registrar_situacao_social
from participantes.tests.test_models import novo_participante
from relatorios.services import consultar_indicadores_sociais_fmr


class IndicadoresSociaisFMRTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="sociais_fmr_ficticio")
        cls.grupo = Group.objects.get(name="Equipe")
        cls.usuario.groups.add(cls.grupo)
        cls.url = reverse("relatorios:fmr")

    def setUp(self):
        self.client.force_login(self.usuario)

    def consultar(self, **extras):
        return consultar_indicadores_sociais_fmr(**({"usuario": self.usuario, "ano": 2024, "mes": 2} | extras))

    def contagens(self, dados):
        return {linha["codigo"]: linha["quantidade"] for linha in dados["linhas"]}

    def pessoa(self, entrada=date(2024, 1, 1)):
        pessoa = novo_participante()
        pessoa.save()
        Movimentacao.objects.create(participante=pessoa, tipo="entrada", data=entrada, usuario=self.usuario)
        return pessoa

    def situacao(self, pessoa, sozinho=True, apoio=True, deficiencia=True, bpc=True, desde=date(2024, 1, 1)):
        return registrar_situacao_social(usuario=self.usuario, participante_id=pessoa.pk, vigente_desde=desde,
            mora_sozinho=sozinho, tem_apoio=apoio, possui_deficiencia=deficiencia, recebe_bpc=bpc, imigrante_refugiado=False)

    def mover(self, pessoa, tipo, dia):
        motivo = MotivoDesligamento.objects.get(descricao="Desistência")
        return movimentar_participante(usuario=self.usuario, participante_id=pessoa.pk, tipo=tipo,
            data=dia, motivo_id=motivo.pk if tipo == "desligamento" else None)

    def test_quatro_indicadores_e_apoio_restrito_a_quem_mora_sozinho(self):
        for sozinho, apoio, deficiencia, bpc in ((True, True, True, False), (True, False, False, True),
                                               (False, True, True, True), (False, False, False, False)):
            self.situacao(self.pessoa(), sozinho, apoio, deficiencia, bpc)
        dados = self.consultar()
        self.assertEqual(self.contagens(dados), {"moram_sozinhos": 2, "moram_sozinhos_com_apoio": 1,
            "possuem_deficiencia": 2, "recebem_bpc": 2})
        self.assertEqual(dados["total_permanentes"], 4)
        self.assertIsNone(dados["pendencia"])
        self.assertLessEqual(self.contagens(dados)["moram_sozinhos_com_apoio"], self.contagens(dados)["moram_sozinhos"])
        self.assertLessEqual(self.contagens(dados)["moram_sozinhos"], dados["total_permanentes"])

    def test_alteracao_futura_nao_modifica_fechamento_anterior(self):
        pessoa = self.pessoa()
        self.situacao(pessoa)
        self.situacao(pessoa, False, False, False, False, date(2024, 3, 1))
        self.assertEqual(list(self.contagens(self.consultar()).values()), [1, 1, 1, 1])
        self.assertEqual(list(self.contagens(self.consultar(mes=3)).values()), [0, 0, 0, 0])

    def test_ultimo_dia_bissexto_inclusivo_e_correcao_na_mesma_vigencia(self):
        pessoa = self.pessoa()
        self.situacao(pessoa, desde=date(2024, 2, 29))
        self.assertEqual(list(self.contagens(self.consultar()).values()), [1, 1, 1, 1])
        self.situacao(pessoa, False, False, False, False, date(2024, 2, 29))
        self.assertEqual(list(self.contagens(self.consultar()).values()), [0, 0, 0, 0])

    def test_populacao_historica_afastados_retornos_e_ciclos_nao_duplicam_pessoas(self):
        saida_futura = self.pessoa()
        self.situacao(saida_futura)
        self.mover(saida_futura, "desligamento", date(2024, 3, 1))
        desligado = self.pessoa()
        self.situacao(desligado)
        self.mover(desligado, "desligamento", date(2024, 2, 29))
        reativado = self.pessoa()
        self.situacao(reativado)
        for tipo, dia in (("desligamento", 1), ("reativacao", 2), ("desligamento", 3), ("reativacao", 29)):
            self.mover(reativado, tipo, date(2024, 2, dia))
        afastado = self.pessoa()
        self.situacao(afastado)
        self.mover(afastado, "afastamento", date(2024, 2, 10))
        self.pessoa(entrada=date(2024, 3, 1))  # Não exige situação de quem ainda não ingressou.
        dados = self.consultar()
        self.assertEqual(dados["total_permanentes"], 3)
        self.assertEqual(list(self.contagens(dados).values()), [3, 3, 3, 3])

    def test_situacao_ausente_ou_posterior_nao_e_zero_nem_total_parcial(self):
        self.situacao(self.pessoa())
        self.situacao(self.pessoa(), desde=date(2024, 3, 1))
        fonte = indicadores_sociais_mensal(usuario=self.usuario, ano=2024, mes=2)
        self.assertEqual(fonte["total_permanentes"], 2)
        self.assertEqual(fonte["sem_situacao"], 1)
        self.assertTrue(all(valor is None for valor in fonte["totais"].values()))
        dados = self.consultar()
        self.assertEqual(dados["linhas"], [])
        self.assertEqual(dados["pendencia"]["codigo"], "SITUACAO")
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Participantes sem situação social vigente: 1")
        self.assertNotContains(resposta, 'id="tabela-indicadores-sociais"')

    def test_cadastro_pendente_fica_fora_sem_anular_o_mes(self):
        # Antes: um cadastro Inativo ou sem entrada anulava os indicadores do mês (None). Agora ele fica fora do
        # cálculo (listado como pendente na tela) e os cadastros completos continuam contados.
        completo = self.pessoa()
        self.situacao(completo)
        pessoa = self.pessoa()
        pessoa.status = "inativo"
        pessoa.save(update_fields=["status"])
        fonte = indicadores_sociais_mensal(usuario=self.usuario, ano=2024, mes=2)
        self.assertEqual(fonte["total_permanentes"], 1)
        self.assertIsNone(self.consultar()["pendencia"])
        self.assertEqual(list(self.contagens(self.consultar()).values()), [1, 1, 1, 1])
        pessoa.status = "ativo"
        pessoa.save(update_fields=["status"])
        pessoa.movimentacoes.all().delete()
        self.assertEqual(list(self.contagens(self.consultar()).values()), [1, 1, 1, 1])
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, 'id="tabela-indicadores-sociais"')
        self.assertContains(resposta, "1 cadastro(s) fora do cálculo deste FMR")

    def test_mes_vazio_e_situacao_negativa_tem_zeros_reais(self):
        dados = self.consultar()
        self.assertEqual(list(self.contagens(dados).values()), [0, 0, 0, 0])
        self.assertIsNone(dados["pendencia"])
        self.situacao(self.pessoa(), False, False, False, False)
        dados = self.consultar()
        self.assertEqual(list(self.contagens(dados).values()), [0, 0, 0, 0])
        self.assertEqual(dados["total_permanentes"], 1)

    def test_interface_quatro_indicadores_referencia_e_tooltip_de_pendencia(self):
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, 'id="tabela-indicadores-sociais"')
        self.assertContains(resposta, "Situação social no fechamento de 02/2024")
        self.assertContains(resposta, "em 29/02/2024")
        self.assertContains(resposta, "Pessoas que moram sozinhas")
        self.assertContains(resposta, "Dessas pessoas, quantas contam com apoio da família/comunidade")
        self.assertContains(resposta, "Pessoas que possuem deficiência")
        self.assertContains(resposta, "Pessoas que recebem BPC")
        self.assertContains(resposta, "não devem ser somados")
        self.pessoa()
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, 'title="Precisamos de situação social com vigência')
        self.assertContains(resposta, 'aria-describedby="social-pendencia-SITUACAO"')
        self.assertContains(resposta, 'tabindex="0"')

    def test_origem_devolve_apenas_agregados_e_consulta_nao_escreve(self):
        self.situacao(self.pessoa())
        with CaptureQueriesContext(connection) as consultas:
            dados = indicadores_sociais_mensal(usuario=self.usuario, ano=2024, mes=2)
        self.assertEqual(dados, {"total_permanentes": 1, "sem_situacao": 0,
            "totais": {"moram_sozinhos": 1, "moram_sozinhos_com_apoio": 1, "possuem_deficiencia": 1, "recebem_bpc": 1}})
        self.assertTrue(all(q["sql"].upper().startswith("SELECT") for q in consultas))

    def test_permissao_atual_na_fonte_e_consumidor_sem_numeros(self):
        self.consultar()
        permissao = Permission.objects.get(content_type__app_label="participantes", codename="view_participante")
        self.grupo.permissions.remove(permissao)
        with self.assertRaises(PermissionDenied):
            indicadores_sociais_mensal(usuario=self.usuario, ano=2024, mes=2)
        with patch("relatorios.integracoes.participantes.consultar_indicadores_sociais") as fonte:
            dados = self.consultar()
        fonte.assert_not_called()
        self.assertEqual(dados["linhas"], [])
        self.assertIsNone(dados["total_permanentes"])
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Seu perfil não possui permissão para consultar os indicadores de situação social.")
        self.assertNotContains(resposta, 'id="tabela-indicadores-sociais"')

    def test_secao_independe_das_permissoes_de_atividades(self):
        self.grupo.permissions.remove(*Permission.objects.filter(content_type__app_label="atividades"))
        self.assertContains(self.client.get(self.url, {"mes": "2024-02"}), 'id="tabela-indicadores-sociais"')

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
            indicadores_sociais_mensal(usuario=self.usuario, ano=2024, mes=2)
        with self.assertRaises(PermissionDenied):
            self.consultar(usuario=AnonymousUser())
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_validacao_periodo_limites_e_mes_invalido_sem_consulta(self):
        for consulta in (self.consultar, indicadores_sociais_mensal):
            for ano, mes in ((True, 2), (2024, False), (0, 1), (10000, 1), (2024, 0), (2024, 13), (2024, "2")):
                with self.subTest(ano=ano, mes=mes), self.assertRaises(ValidationError):
                    consulta(usuario=self.usuario, ano=ano, mes=mes)
        for ano, mes in ((1, 1), (9999, 12)):
            self.assertEqual(list(self.contagens(self.consultar(ano=ano, mes=mes)).values()), [0, 0, 0, 0])
        with patch("relatorios.services.consultar_indicadores_sociais_fmr") as servico:
            resposta = self.client.get(self.url, {"mes": "2024-13"})
        servico.assert_not_called()
        self.assertNotContains(resposta, 'id="indicadores-sociais"')
