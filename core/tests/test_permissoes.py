"""RNF-SEG-04 / RF-USR-04: core.permissoes.autorizar. Dados fictícios (RN-SEG-02)."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from core.permissoes import autorizar

PERMISSAO = "participantes.add_participante"
OUTRA = "participantes.change_participante"


def permissao(nome):
    app_label, codename = nome.split(".")
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


class AutorizarTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Usuario = get_user_model()
        cls.sem_permissao = Usuario.objects.create_user(username="sem_permissao_ficticio")
        cls.com_permissao = Usuario.objects.create_user(username="com_permissao_ficticio")
        cls.com_permissao.user_permissions.add(permissao(PERMISSAO))
        cls.superusuario = Usuario.objects.create_superuser(username="super_ficticio", password=None)

    def recarregar(self, usuario):
        return get_user_model().objects.get(pk=usuario.pk)

    def test_sem_permissao_levanta_permission_denied_com_a_mensagem(self):
        with self.assertRaisesMessage(PermissionDenied, "Mensagem fictícia de recusa."):
            autorizar(self.recarregar(self.sem_permissao), PERMISSAO, mensagem="Mensagem fictícia de recusa.")

    def test_mensagem_padrao(self):
        with self.assertRaisesMessage(PermissionDenied, "Você não tem permissão para esta ação."):
            autorizar(self.recarregar(self.sem_permissao), PERMISSAO)

    def test_anonimo_ou_ausente_e_recusado(self):
        for usuario in (None, AnonymousUser()):
            with self.subTest(usuario=usuario), self.assertRaisesMessage(PermissionDenied, "É necessário entrar"):
                autorizar(usuario, PERMISSAO)

    def test_usuario_nao_salvo_e_recusado(self):
        with self.assertRaises(PermissionDenied):
            autorizar(get_user_model()(username="nao_salvo_ficticio", is_superuser=True), PERMISSAO)

    def test_com_permissao_retorna_usuario_reconsultado(self):
        usuario = self.recarregar(self.com_permissao)
        autor = autorizar(usuario, PERMISSAO)
        self.assertEqual(autor.pk, usuario.pk)
        self.assertIsNot(autor, usuario)

    def test_permissao_via_grupo(self):
        grupo = Group.objects.create(name="Grupo fictício")
        grupo.permissions.add(permissao(OUTRA))
        usuario = get_user_model().objects.create_user(username="membro_ficticio")
        usuario.groups.add(grupo)
        self.assertEqual(autorizar(self.recarregar(usuario), OUTRA).pk, usuario.pk)

    def test_inativo_negado_mesmo_com_permissao_reconsulta_no_banco(self):
        usuario = self.recarregar(self.com_permissao)
        self.assertTrue(usuario.has_perm(PERMISSAO))  # popula o cache de permissões do objeto em memória
        get_user_model().objects.filter(pk=usuario.pk).update(is_active=False)
        self.assertTrue(usuario.is_active)  # objeto em memória desatualizado
        with self.assertRaisesMessage(PermissionDenied, "Recusado."):
            autorizar(usuario, PERMISSAO, mensagem="Recusado.")

    def test_permissao_removida_depois_do_cache_e_negada(self):
        usuario = self.recarregar(self.com_permissao)
        self.assertTrue(usuario.has_perm(PERMISSAO))
        usuario.user_permissions.remove(permissao(PERMISSAO))
        self.assertTrue(usuario.has_perm(PERMISSAO))  # cache antigo
        with self.assertRaises(PermissionDenied):
            autorizar(usuario, PERMISSAO)

    def test_superusuario_passa_sem_permissoes_explicitas(self):
        autor = autorizar(self.recarregar(self.superusuario), PERMISSAO, OUTRA, "atividades.add_atividade")
        self.assertEqual(autor.pk, self.superusuario.pk)

    def test_superusuario_inativo_e_negado(self):
        usuario = self.recarregar(self.superusuario)
        get_user_model().objects.filter(pk=usuario.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            autorizar(usuario, PERMISSAO)

    def test_varias_permissoes_exigem_todas(self):
        usuario = self.recarregar(self.com_permissao)
        with self.assertRaisesMessage(PermissionDenied, "Faltou uma."):
            autorizar(usuario, PERMISSAO, OUTRA, mensagem="Faltou uma.")
        usuario.user_permissions.add(permissao(OUTRA))
        self.assertEqual(autorizar(self.recarregar(usuario), PERMISSAO, OUTRA).pk, usuario.pk)

    def test_permissao_inexistente_e_negada(self):
        with self.assertRaises(PermissionDenied):
            autorizar(self.recarregar(self.com_permissao), "participantes.permissao_inexistente_ficticia")
