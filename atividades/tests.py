from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from .models import Atividade, RegistroCadastroAtividade
from .services import cadastrar_atividade


class CadastroAtividadeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.autor = get_user_model().objects.create_user(username="equipe_ficticia")
        cls.autor.user_permissions.add(Permission.objects.get(
            content_type__app_label="atividades", codename="add_atividade"
        ))
        cls.dados = {"nome": "Dança sênior", "local": "Sala fictícia", "monitor": "Monitor fictício"}

    def cadastrar(self, **alteracoes):
        return cadastrar_atividade(usuario=self.autor, **(self.dados | alteracoes))

    def assert_sem_cadastros(self):
        self.assertFalse(Atividade.objects.exists())
        self.assertFalse(RegistroCadastroAtividade.objects.exists())

    def test_cadastro_persiste_dados_e_registra_autor_data_e_valores_originais(self):
        atividade = self.cadastrar(nome="  Dança sênior  ", local=" Sala fictícia ")
        atividade.refresh_from_db()
        self.assertEqual(str(atividade), self.dados["nome"])
        registro = atividade.registro_cadastro
        self.assertEqual(registro.usuario_id, self.autor.pk)
        self.assertIsNotNone(registro.registrado_em)
        self.assertEqual(registro.dados, self.dados)
        self.assertEqual(atividade.local, self.dados["local"])
        self.assertEqual(atividade.monitor, self.dados["monitor"])

    def test_anonimo_ou_usuario_nao_persistido_nao_cadastra(self):
        for usuario in (None, AnonymousUser(), get_user_model()(username="nao_salvo")):
            with self.subTest(usuario=usuario), self.assertRaises(PermissionDenied):
                cadastrar_atividade(usuario=usuario, **self.dados)
        self.assert_sem_cadastros()

    def test_usuario_sem_permissao_nao_cadastra(self):
        usuario = get_user_model().objects.create_user(username="sem_permissao")
        with self.assertRaises(PermissionDenied):
            cadastrar_atividade(usuario=usuario, **self.dados)
        self.assert_sem_cadastros()

    def test_usuario_desativado_no_banco_nao_cadastra_mesmo_com_permissao_em_cache(self):
        self.assertTrue(self.autor.has_perm("atividades.add_atividade"))
        get_user_model().objects.filter(pk=self.autor.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.cadastrar()
        self.assert_sem_cadastros()

    def test_permissao_revogada_nao_e_aceita_pelo_cache_do_usuario(self):
        self.assertTrue(self.autor.has_perm("atividades.add_atividade"))
        self.autor.user_permissions.clear()
        with self.assertRaises(PermissionDenied):
            self.cadastrar()
        self.assert_sem_cadastros()

    def test_campos_obrigatorios_rejeitam_vazio_espacos_e_valores_nao_textuais(self):
        for campo in self.dados:
            for valor in ("", " \t\n ", None, 123):
                with self.subTest(campo=campo, valor=valor), self.assertRaises(ValidationError) as erro:
                    self.cadastrar(**{campo: valor})
                self.assertIn(campo, erro.exception.message_dict)
        self.assert_sem_cadastros()

    def test_limite_de_tamanho_valida_antes_de_gravar(self):
        for campo in self.dados:
            with self.subTest(campo=campo), self.assertRaises(ValidationError):
                self.cadastrar(**{campo: "x" * 151})
        self.assert_sem_cadastros()
        atividade = self.cadastrar(**dict.fromkeys(self.dados, "x" * 150))
        self.assertEqual(len(Atividade.objects.get(pk=atividade.pk).nome), 150)

    def test_falha_na_auditoria_desfaz_o_cadastro(self):
        with patch("atividades.services.RegistroCadastroAtividade.objects.create", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.cadastrar()
        self.assert_sem_cadastros()


class InterfaceAtividadeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(
            username="equipe_interface_ficticia", password="SenhaApenasParaTestes-8173"
        )
        cls.usuario.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="atividades", codename__in=("view_atividade", "add_atividade")
        ))
        cls.dados = {"nome": "Atividade fictícia", "local": "Sala fictícia", "monitor": "Oficineiro fictício"}

    def setUp(self):
        self.url = reverse("atividades:lista")

    def test_anonimo_redirecionado_para_login_sem_expor_dados(self):
        for metodo in (self.client.get, self.client.post):
            resposta = metodo(self.url, self.dados)
            self.assertEqual(resposta.status_code, 302)
            self.assertIn(reverse("entrar"), resposta.url)
        self.assertFalse(Atividade.objects.exists())

    def test_usuario_sem_permissao_recebe_403(self):
        usuario = get_user_model().objects.create_user(username="sem_acesso_ficticio")
        self.client.force_login(usuario)
        self.assertContains(self.client.get(self.url), "Sem acesso", status_code=403)
        self.assertEqual(self.client.post(self.url, self.dados).status_code, 403)
        self.assertFalse(Atividade.objects.exists())

    def test_somente_leitura_nao_exibe_formulario_nem_permite_cadastro(self):
        self.usuario.user_permissions.remove(Permission.objects.get(
            content_type__app_label="atividades", codename="add_atividade"
        ))
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Nenhuma atividade cadastrada")
        self.assertNotContains(resposta, "Cadastrar atividade")
        self.assertEqual(self.client.post(self.url, self.dados).status_code, 403)
        self.assertFalse(Atividade.objects.exists())

    def test_login_cadastro_listagem_e_logout_com_backend_real(self):
        resposta = self.client.post(reverse("entrar"), {
            "username": self.usuario.username, "password": "SenhaApenasParaTestes-8173"
        })
        self.assertRedirects(resposta, self.url)
        self.assertContains(self.client.get(self.url), "Cadastrar atividade")
        resposta = self.client.post(self.url, self.dados, follow=True)
        self.assertContains(resposta, "Atividade cadastrada com sucesso")
        self.assertContains(resposta, self.dados["nome"])
        registro = RegistroCadastroAtividade.objects.get()
        self.assertEqual(registro.dados, self.dados)
        self.assertEqual(registro.usuario_id, self.usuario.pk)
        self.assertEqual(registro.atividade.nome, self.dados["nome"])
        # Atualizar a listagem após POST/redirect/GET não repete o cadastro.
        self.client.get(self.url)
        self.assertEqual(Atividade.objects.count(), 1)
        self.assertRedirects(self.client.post(reverse("sair")), reverse("entrar"))
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_formulario_invalido_preserva_valores_e_nao_grava(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(self.url, self.dados | {"nome": "   "})
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("nome", resposta.context["form"].errors)
        self.assertContains(resposta, self.dados["local"])
        self.assertFalse(Atividade.objects.exists())
        self.assertFalse(RegistroCadastroAtividade.objects.exists())

    def test_cadastro_exige_csrf_e_aceita_token_do_formulario(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.usuario)
        self.assertEqual(client.post(self.url, self.dados).status_code, 403)
        self.assertFalse(Atividade.objects.exists())
        client.get(self.url)
        token = client.cookies["csrftoken"].value
        self.assertEqual(client.post(self.url, self.dados | {"csrfmiddlewaretoken": token}).status_code, 302)
        self.assertEqual(RegistroCadastroAtividade.objects.count(), 1)

    def test_listagem_escapa_html_dos_dados_cadastrados(self):
        cadastrar_atividade(usuario=self.usuario, **(self.dados | {"nome": "<script>alert(1)</script>"}))
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "&lt;script&gt;")
        self.assertNotContains(resposta, "<script>alert(1)</script>")

    def test_raiz_leva_para_atividades(self):
        self.assertRedirects(self.client.get("/"), self.url, fetch_redirect_response=False)
