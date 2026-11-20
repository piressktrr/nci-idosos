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
from participantes.movimentacoes import movimentar_participante, salvar_motivo
from participantes.relatorios import desligamentos_por_motivo_mensal
from participantes.tests.test_models import novo_participante
from relatorios.services import consultar_desligamentos_motivo_fmr, consultar_movimentacao_etaria_fmr


class DesligamentosMotivoFMRTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Os casos abaixo também precisam cobrir instalações com catálogo vazio.
        MotivoDesligamento.objects.all().delete()
        cls.usuario = get_user_model().objects.create_user(username="motivos_fmr_ficticio")
        cls.grupo = Group.objects.get(name="Equipe")
        cls.usuario.groups.add(cls.grupo)
        cls.admin = get_user_model().objects.create_user(username="admin_motivos_ficticio")
        cls.admin.groups.add(Group.objects.get(name="Administrador"))
        cls.url = reverse("relatorios:fmr")

    def setUp(self):
        self.client.force_login(self.usuario)

    def consultar(self, **extras):
        return consultar_desligamentos_motivo_fmr(**({"usuario": self.usuario, "ano": 2024, "mes": 2} | extras))

    def pessoa(self, **extras):
        pessoa = novo_participante(**extras)
        pessoa.save()
        Movimentacao.objects.create(participante=pessoa, usuario=self.usuario, tipo="entrada", data=date(2023, 1, 1))
        return pessoa

    def motivo(self, descricao="Motivo fictício A"):
        return salvar_motivo(usuario=self.admin, descricao=descricao)

    def mover(self, pessoa, tipo="desligamento", dia=date(2024, 2, 1), motivo=None):
        return movimentar_participante(usuario=self.usuario, participante_id=pessoa.pk, tipo=tipo,
            data=dia, motivo_id=motivo.pk if motivo else None)

    def test_agrupa_saidas_por_motivo_e_total_confere_com_rf05(self):
        a, b = self.motivo(), self.motivo("Motivo fictício B")
        for motivo in (a, a, b):
            self.mover(self.pessoa(), motivo=motivo)
        dados = self.consultar()
        self.assertEqual([(r["descricao"], r["quantidade"]) for r in dados["linhas"]],
                         [(a.descricao, 2), (b.descricao, 1)])
        self.assertEqual(dados["total"], sum(r["quantidade"] for r in dados["linhas"]))
        self.assertEqual(dados["total"], consultar_movimentacao_etaria_fmr(usuario=self.usuario, ano=2024, mes=2)["totais"]["sairam"])

    def test_data_efetiva_limites_inclusivos_bissexto_e_exclusao_de_outros_meses(self):
        motivo = self.motivo()
        for dia in (date(2024, 1, 31), date(2024, 2, 1), date(2024, 2, 29), date(2024, 3, 1)):
            self.mover(self.pessoa(), dia=dia, motivo=motivo)
        self.assertEqual(self.consultar()["total"], 2)
        self.assertEqual(self.consultar(mes=1)["total"], 1)
        self.assertEqual(self.consultar(mes=3)["total"], 1)
        self.assertEqual(self.consultar(ano=2023)["total"], 0)

    def test_multiplas_saidas_contam_eventos_e_retorno_nao_apaga_saida(self):
        pessoa, motivo = self.pessoa(), self.motivo()
        self.mover(pessoa, motivo=motivo)
        self.mover(pessoa, "reativacao", date(2024, 2, 2))
        self.mover(pessoa, dia=date(2024, 2, 3), motivo=motivo)
        self.mover(pessoa, "reativacao", date(2024, 3, 1))
        self.assertEqual(self.consultar()["total"], 2)
        self.assertEqual(self.consultar(mes=3)["total"], 0)

    def test_afastamento_retorno_e_entrada_nao_sao_desligamentos(self):
        pessoa = self.pessoa()
        self.mover(pessoa, "afastamento")
        self.mover(pessoa, "retorno", date(2024, 2, 2))
        self.assertEqual(self.consultar()["total"], 0)

    def test_renomear_e_desativar_motivo_preserva_descricoes_historicas(self):
        motivo = self.motivo("Descrição antiga fictícia")
        self.mover(self.pessoa(), motivo=motivo)
        motivo = salvar_motivo(usuario=self.admin, motivo_id=motivo.pk, descricao="Descrição nova fictícia")
        self.mover(self.pessoa(), motivo=motivo)
        salvar_motivo(usuario=self.admin, motivo_id=motivo.pk, descricao="Descrição atual fictícia", ativo=False)
        dados = self.consultar()
        self.assertEqual([(r["descricao"], r["quantidade"]) for r in dados["linhas"]],
                         [("Descrição antiga fictícia", 1), ("Descrição nova fictícia", 1)])
        self.assertEqual({r["motivo_id"] for r in dados["linhas"]}, {motivo.pk})
        self.assertEqual(dados["total"], 2)

    def test_mes_vazio_catalogo_vazio_e_motivo_sem_uso_nao_inventam_saidas(self):
        self.assertFalse(MotivoDesligamento.objects.exists())
        self.assertEqual(self.consultar()["total"], 0)
        motivo = self.motivo()
        dados = self.consultar()
        self.assertEqual(dados["linhas"], [{"motivo_id": motivo.pk, "descricao": motivo.descricao, "quantidade": 0}])
        self.assertEqual(dados["total"], 0)
        self.assertEqual(dados["pendencias"], [])
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, motivo.descricao)

    def test_inclui_saidas_fora_da_faixa_etaria_sem_ocultar_do_total(self):
        self.mover(self.pessoa(data_nascimento=date(1980, 1, 1)), motivo=self.motivo())
        self.assertEqual(self.consultar()["total"], 1)
        etaria = consultar_movimentacao_etaria_fmr(usuario=self.usuario, ano=2024, mes=2)
        self.assertEqual(etaria["totais"]["sairam"] + etaria["fora_faixas"]["sairam"], 1)

    def test_descricao_historica_ausente_nao_e_substituida_pelo_catalogo_atual(self):
        movimento = self.mover(self.pessoa(), motivo=self.motivo())
        Movimentacao.objects.filter(pk=movimento.pk).update(motivo_descricao="")
        dados = self.consultar()
        self.assertEqual(dados["total"], 1)
        self.assertEqual(dados["linhas"][0]["descricao"], "")
        self.assertEqual(dados["pendencias"][0]["codigo"], "MOTIVO-HISTORICO")
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Descrição histórica ausente")
        self.assertContains(resposta, 'title="É necessário conferir a descrição do motivo')
        self.assertContains(resposta, 'tabindex="0"')

    def test_interface_real_escapa_descricao_e_consulta_nao_escreve(self):
        motivo = self.motivo("<script>motivo fictício</script>")
        self.mover(self.pessoa(), motivo=motivo)
        with CaptureQueriesContext(connection) as consultas:
            dados = self.consultar()
        self.assertEqual(dados["total"], 1)
        self.assertTrue(all(q["sql"].upper().startswith("SELECT") for q in consultas))
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, 'id="tabela-desligamentos-motivo"')
        self.assertContains(resposta, "Desligamentos do mês 02/2024")
        self.assertContains(resposta, "&lt;script&gt;motivo fictício&lt;/script&gt;")
        self.assertNotContains(resposta, "<script>motivo fictício</script>")

    def test_permissao_atual_na_fonte_e_consumidor_sem_expor_numeros(self):
        self.consultar()
        permissao = Permission.objects.get(content_type__app_label="participantes", codename="view_participante")
        self.grupo.permissions.remove(permissao)
        with self.assertRaises(PermissionDenied):
            desligamentos_por_motivo_mensal(usuario=self.usuario, ano=2024, mes=2)
        with patch("relatorios.integracoes.participantes.consultar_desligamentos_por_motivo") as fonte:
            dados = self.consultar()
        fonte.assert_not_called()
        self.assertIsNone(dados["total"])
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Seu perfil não possui permissão para consultar os desligamentos por motivo.")
        self.assertNotContains(resposta, 'id="tabela-desligamentos-motivo"')

    def test_secao_independe_de_permissoes_de_atividades(self):
        self.grupo.permissions.remove(*Permission.objects.filter(content_type__app_label="atividades"))
        self.assertContains(self.client.get(self.url, {"mes": "2024-02"}), 'id="tabela-desligamentos-motivo"')

    def test_login_perfil_conta_ativa_e_apenas_get(self):
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
            desligamentos_por_motivo_mensal(usuario=self.usuario, ano=2024, mes=2)
        with self.assertRaises(PermissionDenied):
            self.consultar(usuario=AnonymousUser())
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_validacao_do_periodo_nas_duas_fronteiras_e_formulario(self):
        for consulta in (self.consultar, desligamentos_por_motivo_mensal):
            for ano, mes in ((True, 2), (2024, False), (0, 1), (10000, 1), (2024, 0), (2024, 13), ("2024", 2)):
                with self.subTest(consulta=consulta, ano=ano, mes=mes), self.assertRaises(ValidationError):
                    consulta(usuario=self.usuario, ano=ano, mes=mes)
        for ano, mes in ((1, 1), (9999, 12)):
            self.assertEqual(self.consultar(ano=ano, mes=mes)["total"], 0)
        with patch("relatorios.services.consultar_desligamentos_motivo_fmr") as servico:
            resposta = self.client.get(self.url, {"mes": "2024-13"})
        servico.assert_not_called()
        self.assertNotContains(resposta, 'id="desligamentos-motivo"')
