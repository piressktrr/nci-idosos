from datetime import date, time
from html.parser import HTMLParser
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import QueryDict
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Atividade, Aula, Inscricao, Frequencia, RegistroLancamentoFrequencia
from .services import registrar_frequencias


class RadiosMarcados(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.dados = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("type") == "radio" and "checked" in attrs and "disabled" not in attrs:
            self.dados[attrs["name"]] = attrs["value"]


@override_settings(DEBUG=True)
class FrequenciaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="frequencia_ficticia")
        cls.usuario.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="atividades", codename__in=(
                "view_atividade", "view_aula", "view_inscricao", "view_frequencia", "add_frequencia"
            )
        ))
        cls.atividade = Atividade.objects.create(nome="Fictícia", local="Sala", monitor="Fictício")
        cls.outra = Atividade.objects.create(nome="Outra fictícia", local="Sala", monitor="Fictício")
        cls.aula = Aula.objects.create(atividade=cls.atividade, data=date(2024, 2, 29), inicio=time(9), fim=time(10))
        cls.outra_aula = Aula.objects.create(atividade=cls.atividade, data=date(2024, 3, 1), inicio=time(9), fim=time(10))
        cls.inscricoes = [Inscricao.objects.create(
            atividade=cls.atividade, origem_participante="placeholder", participante_referencia=f"demo-{i}", cadastrada_por=cls.usuario
        ) for i in range(1, 4)]
        cls.inscricao_outra = Inscricao.objects.create(atividade=cls.outra, origem_participante="placeholder",
                                                     participante_referencia="demo-1", cadastrada_por=cls.usuario)
        cls.url = reverse("atividades:chamada", args=[cls.atividade.pk, cls.aula.pk])
        cls.post_url = reverse("atividades:lancar_frequencias", args=[cls.atividade.pk, cls.aula.pk])

    def lancar(self, registros=None):
        return registrar_frequencias(usuario=self.usuario, atividade_id=self.atividade.pk, aula_id=self.aula.pk,
                                     registros={self.inscricoes[0].pk: "presente"} if registros is None else registros)

    def campo(self, indice=0):
        return f"registro_{self.inscricoes[indice].pk}"

    def test_tres_situacoes_com_data_de_ocorrencia_e_auditoria(self):
        registros = {item.pk: valor for item, valor in zip(self.inscricoes, Frequencia.Situacao.values)}
        resultado = self.lancar(registros)
        self.assertEqual(len(resultado), 3)
        for frequencia in resultado:
            frequencia.refresh_from_db()
            self.assertEqual(frequencia.aula.data, date(2024, 2, 29))
            self.assertEqual(frequencia.situacao, registros[frequencia.inscricao_id])
            audit = frequencia.registro_lancamento
            self.assertEqual(audit.usuario_id, self.usuario.pk)
            self.assertIsNotNone(audit.registrado_em)
            self.assertEqual(audit.dados["data"], "2024-02-29")
            self.assertEqual(audit.dados["situacao"], frequencia.situacao)

    def test_lancamento_parcial_nao_cria_ausencias_implicitas(self):
        self.lancar()
        self.assertEqual(Frequencia.objects.count(), 1)
        self.assertFalse(Frequencia.objects.filter(inscricao=self.inscricoes[1]).exists())

    def test_mesmo_participante_em_aulas_diferentes_tem_registros_independentes(self):
        self.lancar()
        registrar_frequencias(usuario=self.usuario, atividade_id=self.atividade.pk, aula_id=self.outra_aula.pk,
                              registros={self.inscricoes[0].pk: "ausente"})
        self.assertEqual(Frequencia.objects.count(), 2)

    def test_lote_invalido_nao_grava_nenhum_registro(self):
        for registros in ({}, [], {True: "presente"}, {"1": "presente"},
                          {self.inscricoes[0].pk: "presente", self.inscricoes[1].pk: "invalida"}):
            with self.subTest(registros=registros), self.assertRaises(ValidationError):
                self.lancar(registros)
        self.assertFalse(Frequencia.objects.exists())

    def test_inscricao_forjada_ou_de_outra_atividade_rejeita_lote(self):
        for identificador in (999999, self.inscricao_outra.pk):
            with self.subTest(identificador=identificador), self.assertRaises(ValidationError):
                self.lancar({self.inscricoes[0].pk: "presente", identificador: "ausente"})
        self.assertFalse(Frequencia.objects.exists())

    def test_origem_diferente_ou_participante_indisponivel_nao_recebe_frequencia(self):
        for origem, referencia in (("participantes", "demo-1"), ("placeholder", "inexistente")):
            inscricao = Inscricao.objects.create(atividade=self.atividade, origem_participante=origem,
                                                 participante_referencia=referencia, cadastrada_por=self.usuario)
            with self.subTest(origem=origem), self.assertRaises(ValidationError):
                self.lancar({inscricao.pk: "presente"})
        self.assertFalse(Frequencia.objects.exists())

    def test_reenvio_nao_sobrescreve_registro_e_reverte_lote_inteiro(self):
        frequencia = self.lancar()[0]
        snapshot = frequencia.registro_lancamento.dados.copy()
        with self.assertRaises(ValidationError):
            self.lancar({frequencia.inscricao_id: "ausente", self.inscricoes[1].pk: "presente"})
        frequencia.refresh_from_db()
        self.assertEqual(frequencia.situacao, "presente")
        self.assertEqual(frequencia.registro_lancamento.dados, snapshot)
        self.assertEqual(Frequencia.objects.count(), 1)

    def test_cancelada_e_vinculo_de_aula_incorreto_nao_aceitam_lancamento(self):
        with self.assertRaises(Aula.DoesNotExist):
            registrar_frequencias(usuario=self.usuario, atividade_id=self.outra.pk, aula_id=self.aula.pk,
                                  registros={self.inscricoes[0].pk: "presente"})
        Aula.objects.filter(pk=self.aula.pk).update(situacao="cancelada")
        with self.assertRaises(ValidationError):
            self.lancar()
        self.assertFalse(Frequencia.objects.exists())

    def test_falha_na_segunda_auditoria_desfaz_todo_lote(self):
        original = RegistroLancamentoFrequencia.objects.create
        chamadas = []

        def gravar(**kwargs):
            chamadas.append(1)
            if len(chamadas) == 2:
                raise RuntimeError("Falha de teste")
            return original(**kwargs)

        with patch("atividades.services.RegistroLancamentoFrequencia.objects.create", side_effect=gravar):
            with self.assertRaises(RuntimeError):
                self.lancar({self.inscricoes[0].pk: "presente", self.inscricoes[1].pk: "ausente"})
        self.assertFalse(Frequencia.objects.exists())
        self.assertFalse(RegistroLancamentoFrequencia.objects.exists())

    def test_anonimo_nao_persistido_sem_permissao_e_conta_desativada(self):
        sem_acesso = get_user_model().objects.create_user(username="sem_frequencia")
        for usuario in (None, AnonymousUser(), sem_acesso, get_user_model()(username="nao_salvo")):
            with self.subTest(usuario=usuario), self.assertRaises(PermissionDenied):
                registrar_frequencias(usuario=usuario, atividade_id=self.atividade.pk, aula_id=self.aula.pk,
                                      registros={self.inscricoes[0].pk: "presente"})
        self.assertTrue(self.usuario.has_perm("atividades.add_frequencia"))
        permissao = Permission.objects.get(content_type__app_label="atividades", codename="add_frequencia")
        self.usuario.user_permissions.remove(permissao)
        with self.assertRaises(PermissionDenied):
            self.lancar()
        self.usuario.user_permissions.add(permissao)
        get_user_model().objects.filter(pk=self.usuario.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.lancar()

    def test_banco_impede_duplicidade_e_situacao_invalida(self):
        self.lancar()
        for inscricao, situacao in ((self.inscricoes[0], "presente"), (self.inscricoes[1], "invalida")):
            with self.subTest(situacao=situacao), self.assertRaises(IntegrityError), transaction.atomic():
                Frequencia.objects.create(aula=self.aula, inscricao=inscricao, situacao=situacao)

    def test_modelo_valida_inscricao_de_atividade_diferente(self):
        with self.assertRaises(ValidationError):
            Frequencia(aula=self.aula, inscricao=self.inscricao_outra, situacao="presente").full_clean()

    def test_interface_lanca_apenas_selecionados_e_exibe_situacoes_sem_edicao(self):
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, 'type="radio"')
        self.assertFalse(Frequencia.objects.exists())
        resposta = self.client.post(self.post_url, {self.campo(): "presente", self.campo(1): "ausente_justificado"}, follow=True)
        self.assertContains(resposta, "Frequência registrada com sucesso")
        self.assertContains(resposta, "Ausente justificado")
        self.assertEqual(Frequencia.objects.count(), 2)
        self.assertNotContains(resposta, f'name="{self.campo()}"')
        self.assertContains(resposta, f'name="{self.campo(2)}"')

    def test_interface_vazio_status_invalido_e_id_forjado_nao_gravam(self):
        self.client.force_login(self.usuario)
        for dados in ({}, {self.campo(): "invalida"}, {self.campo(): "presente", "registro_999999": "ausente"}):
            with self.subTest(dados=dados):
                resposta = self.client.post(self.post_url, dados)
                self.assertEqual(resposta.status_code, 200)
                self.assertTrue(resposta.context["form"].errors)
        self.assertFalse(Frequencia.objects.exists())

    def test_interface_rejeita_multiplos_valores_para_mesma_inscricao(self):
        self.client.force_login(self.usuario)
        dados = QueryDict(mutable=True)
        dados.setlist(self.campo(), ["presente", "ausente"])
        resposta = self.client.post(self.post_url, dados.urlencode(), content_type="application/x-www-form-urlencoded")
        self.assertTrue(resposta.context["form"].errors)
        self.assertFalse(Frequencia.objects.exists())

    def test_interface_respeita_leitura_e_nao_expoe_situacao_sem_permissao(self):
        self.lancar()
        self.usuario.user_permissions.remove(Permission.objects.get(content_type__app_label="atividades", codename="add_frequencia"))
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Presente")
        self.assertNotContains(resposta, "Salvar frequência")
        self.assertEqual(self.client.post(self.post_url, {self.campo(1): "ausente"}).status_code, 403)
        self.usuario.user_permissions.remove(Permission.objects.get(content_type__app_label="atividades", codename="view_frequencia"))
        self.assertNotContains(self.client.get(self.url), "checked")

    def test_radios_presente_por_padrao_so_gravam_ao_salvar(self):
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url)
        dados = RadiosMarcados(resposta.content.decode()).dados
        self.assertEqual(dados, {self.campo(i): "presente" for i in range(3)})
        self.assertNotContains(resposta, "<select")
        self.assertFalse(Frequencia.objects.exists())
        dados[self.campo(1)] = "ausente"
        self.assertEqual(self.client.post(self.post_url, dados).status_code, 302)
        self.assertEqual(Frequencia.objects.filter(situacao="presente").count(), 2)
        self.assertEqual(Frequencia.objects.filter(situacao="ausente").count(), 1)

    def test_radios_preservam_escolhas_apos_erro_sem_repor_defaults_no_post(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(self.post_url, {self.campo(): "ausente", "registro_999999": "presente"})
        self.assertEqual(RadiosMarcados(resposta.content.decode()).dados, {self.campo(): "ausente"})
        self.assertTrue(resposta.context["form"].errors)
        self.assertFalse(Frequencia.objects.exists())

    def test_csrf_e_metodos_http(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.usuario)
        self.assertEqual(client.get(self.post_url).status_code, 405)
        self.assertEqual(client.post(self.post_url, {self.campo(): "presente"}).status_code, 403)
        client.get(self.url)
        token = client.cookies["csrftoken"].value
        self.assertEqual(client.post(self.post_url, {self.campo(): "presente", "csrfmiddlewaretoken": token}).status_code, 302)

    @override_settings(NCI_PARTICIPANTES_PROVIDER="atividades.test_inscricoes.ProvedorIndisponivel")
    def test_integracao_indisponivel_nao_grava(self):
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.post(self.post_url, {self.campo(): "presente"}).status_code, 503)
        self.assertFalse(Frequencia.objects.exists())
