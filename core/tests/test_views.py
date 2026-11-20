"""Tela inicial, entrada e páginas de erro (core). Dados fictícios (RN-SEG-02)."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse


def _usuario(username, *codenames, app="participantes", **extra):
    usuario = get_user_model().objects.create_user(username=username, **extra)
    if codenames:
        usuario.user_permissions.add(*Permission.objects.filter(content_type__app_label=app, codename__in=codenames))
    return usuario


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class CoreTests(TestCase):
    """Início, entrada e páginas de erro (core)."""

    def test_inicio_exige_login(self):
        resposta = self.client.get(reverse("inicio"))
        self.assertRedirects(resposta, f"{reverse('entrar')}?next=/", fetch_redirect_response=False)

    def test_inicio_sem_permissoes_nao_mostra_modulos(self):
        self.client.force_login(_usuario("inicio_sem_perm_ficticio", first_name="Fulana"))
        resposta = self.client.get(reverse("inicio"))
        self.assertContains(resposta, "Olá, Fulana!")
        self.assertNotContains(resposta, reverse("participantes:lista"))
        self.assertNotContains(resposta, reverse("atividades:lista"))
        self.assertNotContains(resposta, "Gestão de Participantes")
        self.assertNotContains(resposta, "Gestão de Colaboradores")
        self.assertContains(resposta, "Formulário Mensal")

    def test_inicio_mostra_participantes_com_view(self):
        self.client.force_login(_usuario("inicio_par_ficticio", "view_participante"))
        resposta = self.client.get(reverse("inicio"))
        self.assertContains(resposta, f'<a class="nci-modulo" href="{reverse("participantes:lista")}">')
        self.assertNotContains(resposta, reverse("atividades:frequencia_mensal"))

    def test_inicio_mostra_atividades_com_view_atividade(self):
        self.client.force_login(_usuario("inicio_ativ_ficticio", "view_atividade", app="atividades"))
        resposta = self.client.get(reverse("inicio"))
        self.assertContains(resposta, f'<a class="nci-modulo" href="{reverse("atividades:frequencia_mensal")}">')
        self.assertContains(resposta, f'<a class="nci-modulo" href="{reverse("atividades:lista")}">')
        self.assertNotContains(resposta, reverse("participantes:lista"))

    def test_colaboradores_so_para_administrador(self):
        """RN-USR-01: o critério é core.perfis.e_administrador, não is_staff nem permissões avulsas de contas."""
        casos = {
            "staff_sem_perm": ({"is_staff": True}, False, False),
            "perm_sem_staff": ({}, True, False),
            "staff_com_perm": ({"is_staff": True}, True, False),
            "superusuario": ({"is_superuser": True}, False, True),
        }
        for nome, (extra, com_perm, aparece) in casos.items():
            with self.subTest(caso=nome):
                usuario = _usuario(f"colab_{nome}", **extra)
                if com_perm:
                    usuario.user_permissions.add(Permission.objects.get(content_type__app_label="auth",
                                                                        codename="view_user"))
                self.client.force_login(usuario)
                resposta = self.client.get(reverse("inicio"))
                self.assertNotContains(resposta, "/admin/auth/user/")
                if aparece:
                    self.assertContains(resposta, "Gestão de Colaboradores")
                    self.assertContains(resposta, reverse("usuarios:lista"))
                else:
                    self.assertNotContains(resposta, "Gestão de Colaboradores")
                    self.assertNotContains(resposta, reverse("usuarios:lista"))

    def test_logado_em_entrar_vai_para_inicio(self):
        self.client.force_login(_usuario("ja_logado_ficticio"))
        self.assertRedirects(self.client.get(reverse("entrar")), reverse("inicio"))

    def test_anonimo_ve_formulario_de_entrada(self):
        resposta = self.client.get(reverse("entrar"))
        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "nci/login.html")

    @override_settings(DEBUG=False)
    def test_404_usa_template_proprio(self):
        self.client.force_login(_usuario("visitante_404_ficticio"))
        resposta = self.client.get("/endereco-ficticio-inexistente/")
        self.assertEqual(resposta.status_code, 404)
        self.assertTemplateUsed(resposta, "404.html")
        self.assertContains(resposta, "Página não encontrada", status_code=404)

    @override_settings(DEBUG=False)
    def test_404_de_participante_inexistente_usa_template_proprio(self):
        self.client.force_login(_usuario("visitante_404b_ficticio", "view_participante"))
        resposta = self.client.get(reverse("participantes:detalhe", args=[999999]))
        self.assertEqual(resposta.status_code, 404)
        self.assertTemplateUsed(resposta, "404.html")

    def test_403_usa_template_proprio(self):
        self.client.force_login(_usuario("visitante_403_ficticio"))
        resposta = self.client.get(reverse("participantes:lista"))
        self.assertEqual(resposta.status_code, 403)
        self.assertTemplateUsed(resposta, "403.html")
