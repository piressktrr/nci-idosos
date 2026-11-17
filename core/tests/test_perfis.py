"""RF-USR-02 / RN-USR-02 / RNF-SEG-04: grupos Equipe e Administrador (core.perfis). Dados fictícios (RN-SEG-02)."""

from datetime import date
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.management.sql import emit_post_migrate_signal
from django.test import TestCase, override_settings
from django.urls import reverse

from core.perfis import (
    GRUPO_ADMINISTRADOR,
    GRUPO_EQUIPE,
    PERMISSOES_ADMINISTRADOR,
    PERMISSOES_EQUIPE,
    e_administrador,
    garantir_perfis,
)
from core.permissoes import autorizar
from participantes.models import Participante
from participantes.services import cadastrar_participante, corrigir_participante

DADOS = {
    "nome_completo": "Joana Fictícia dos Perfis",
    "data_nascimento": date(1951, 5, 20),
    "sexo": "F",
    "raca_cor": "parda",
    "identidade_genero": "mulher_cis",
    "telefone_celular": "61912345678",
    "telefone_residencial": "",
    "origem_encaminhamento": "cras",
    "endereco": "Rua Fictícia, 200",
    "ensino_medio_completo": True,
    "observacao_encaminhamento": "",
}
ENTRADA = date(2024, 2, 1)


def nomes(grupo):
    return set(grupo.permissions.values_list("content_type__app_label", "codename")
               .order_by().distinct())


def como_texto(pares):
    return {f"{app}.{codename}" for app, codename in pares}


def todas_do_app(app_label):
    return set(Permission.objects.filter(content_type__app_label=app_label)
               .values_list("content_type__app_label", "codename"))


def permissao(nome):
    app_label, codename = nome.split(".")
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def membro(username, *grupos, **extra):
    usuario = get_user_model().objects.create_user(username=username, **extra)
    usuario.groups.add(*Group.objects.filter(name__in=grupos))
    return get_user_model().objects.get(pk=usuario.pk)


class GruposAposMigrateTests(TestCase):
    def test_grupos_existem_com_as_permissoes_minimas(self):
        equipe = Group.objects.get(name=GRUPO_EQUIPE)
        administrador = Group.objects.get(name=GRUPO_ADMINISTRADOR)
        self.assertEqual(como_texto(nomes(equipe)), set(PERMISSOES_EQUIPE))
        esperadas_admin = como_texto(todas_do_app("participantes")) | set(PERMISSOES_ADMINISTRADOR)
        self.assertEqual(como_texto(nomes(administrador)), esperadas_admin)

    def test_equipe_tem_exatamente_ver_cadastrar_corrigir_participante(self):
        self.assertEqual(set(PERMISSOES_EQUIPE), {"participantes.view_participante",
                                                  "participantes.add_participante",
                                                  "participantes.change_participante"})

    def test_administrador_tem_todas_de_participantes_e_contas_sem_excluir(self):
        administrador = Group.objects.get(name=GRUPO_ADMINISTRADOR)
        pares = nomes(administrador)
        self.assertTrue(todas_do_app("participantes"))
        self.assertLessEqual(todas_do_app("participantes"), pares)
        auth = {codename for app, codename in pares if app == "auth"}
        self.assertEqual(auth, {"view_user", "add_user", "change_user", "view_group", "add_group", "change_group"})
        self.assertFalse({"delete_user", "delete_group"} & auth)
        self.assertFalse(any(app == "auth" and codename.endswith("_permission") for app, codename in pares))

    def test_nenhum_grupo_tem_permissao_de_atividades(self):
        for nome in (GRUPO_EQUIPE, GRUPO_ADMINISTRADOR):
            with self.subTest(grupo=nome):
                grupo = Group.objects.get(name=nome)
                self.assertFalse(grupo.permissions.filter(content_type__app_label="atividades").exists())

    def test_post_migrate_recria_grupos_apagados(self):
        Group.objects.filter(name__in=(GRUPO_EQUIPE, GRUPO_ADMINISTRADOR)).delete()
        emit_post_migrate_signal(verbosity=0, interactive=False, db="default")
        self.assertEqual(como_texto(nomes(Group.objects.get(name=GRUPO_EQUIPE))), set(PERMISSOES_EQUIPE))
        self.assertTrue(Group.objects.filter(name=GRUPO_ADMINISTRADOR).exists())


class IdempotenciaTests(TestCase):
    def test_rodar_duas_vezes_nao_duplica_nem_acrescenta(self):
        garantir_perfis()
        antes = {nome: nomes(Group.objects.get(name=nome)) for nome in (GRUPO_EQUIPE, GRUPO_ADMINISTRADOR)}
        resultado = garantir_perfis()
        self.assertEqual(resultado, {GRUPO_EQUIPE: (False, 0), GRUPO_ADMINISTRADOR: (False, 0)})
        for nome, permissoes in antes.items():
            with self.subTest(grupo=nome):
                self.assertEqual(Group.objects.filter(name=nome).count(), 1)
                self.assertEqual(nomes(Group.objects.get(name=nome)), permissoes)
                grupo = Group.objects.get(name=nome)
                self.assertEqual(grupo.permissions.count(), len(permissoes))

    def test_nao_remove_permissoes_extras_adicionadas_manualmente(self):
        equipe = Group.objects.get(name=GRUPO_EQUIPE)
        administrador = Group.objects.get(name=GRUPO_ADMINISTRADOR)
        extra_equipe = permissao("participantes.view_situacaosocial")
        extra_admin = permissao("auth.view_permission")
        equipe.permissions.add(extra_equipe)
        administrador.permissions.add(extra_admin)
        garantir_perfis()
        garantir_perfis()
        self.assertTrue(equipe.permissions.filter(pk=extra_equipe.pk).exists())
        self.assertTrue(administrador.permissions.filter(pk=extra_admin.pk).exists())
        self.assertEqual(como_texto(nomes(equipe)), set(PERMISSOES_EQUIPE) | {"participantes.view_situacaosocial"})

    def test_repoe_permissao_minima_removida(self):
        equipe = Group.objects.get(name=GRUPO_EQUIPE)
        equipe.permissions.remove(permissao("participantes.add_participante"))
        self.assertEqual(garantir_perfis()[GRUPO_EQUIPE], (False, 1))
        self.assertEqual(como_texto(nomes(equipe)), set(PERMISSOES_EQUIPE))

    def test_cria_grupo_que_faltar(self):
        Group.objects.filter(name=GRUPO_ADMINISTRADOR).delete()
        criado, acrescentadas = garantir_perfis()[GRUPO_ADMINISTRADOR]
        self.assertTrue(criado)
        self.assertEqual(acrescentadas, len(todas_do_app("participantes")) + len(PERMISSOES_ADMINISTRADOR))

    def test_comando_garantir_perfis(self):
        Group.objects.filter(name=GRUPO_EQUIPE).delete()
        saida = StringIO()
        call_command("garantir_perfis", stdout=saida)
        call_command("garantir_perfis", stdout=saida)
        texto = saida.getvalue()
        self.assertIn("Grupo Equipe: criado; 3 permissão(ões) acrescentada(s).", texto)
        self.assertIn("Grupo Equipe: já existia; 0 permissão(ões) acrescentada(s).", texto)
        self.assertIn("Perfis de acesso garantidos.", texto)
        self.assertEqual(Group.objects.filter(name=GRUPO_EQUIPE).count(), 1)
        self.assertEqual(como_texto(nomes(Group.objects.get(name=GRUPO_EQUIPE))), set(PERMISSOES_EQUIPE))


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class EquipeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.equipe = membro("equipe_perfil_ficticia", GRUPO_EQUIPE)

    def test_cadastra_e_corrige_participante_pelos_servicos(self):
        participante = cadastrar_participante(usuario=self.equipe, data_entrada=ENTRADA, **DADOS)
        corrigir_participante(usuario=self.equipe, participante_id=participante.pk, data_entrada=ENTRADA,
                              **(DADOS | {"endereco": "Rua Fictícia, 300"}))
        participante.refresh_from_db()
        self.assertEqual(participante.endereco, "Rua Fictícia, 300")

    def test_acessa_telas_de_participantes(self):
        self.client.force_login(self.equipe)
        self.assertEqual(self.client.get(reverse("participantes:lista")).status_code, 200)
        self.assertEqual(self.client.get(reverse("participantes:cadastrar")).status_code, 200)

    def test_nao_administra_contas(self):
        for nome in PERMISSOES_ADMINISTRADOR:
            with self.subTest(permissao=nome), self.assertRaises(PermissionDenied):
                autorizar(self.equipe, nome)
        self.assertFalse(e_administrador(self.equipe))

    def test_nao_abre_contas_no_admin_nem_com_is_staff(self):
        url = reverse("admin:auth_user_changelist")
        self.client.force_login(self.equipe)
        self.assertRedirects(self.client.get(url), f"{reverse('admin:login')}?next={url}",
                             fetch_redirect_response=False)
        get_user_model().objects.filter(pk=self.equipe.pk).update(is_staff=True)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:auth_group_changelist")).status_code, 403)

    def test_inicio_nao_mostra_gestao_de_colaboradores(self):
        self.client.force_login(self.equipe)
        resposta = self.client.get(reverse("inicio"))
        self.assertContains(resposta, "Gestão de Participantes")
        self.assertNotContains(resposta, "Gestão de Colaboradores")


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class AdministradorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.administrador = membro("admin_perfil_ficticio", GRUPO_ADMINISTRADOR)

    def test_membro_do_grupo_e_administrador(self):
        self.assertTrue(e_administrador(self.administrador))
        self.assertEqual(autorizar(self.administrador, *PERMISSOES_ADMINISTRADOR).pk, self.administrador.pk)

    def test_superusuario_e_administrador_sem_grupo(self):
        superusuario = get_user_model().objects.create_superuser(username="super_perfil_ficticio", password=None)
        self.assertTrue(e_administrador(superusuario))

    def test_inativo_nao_e_administrador(self):
        inativo = membro("admin_inativo_ficticio", GRUPO_ADMINISTRADOR, is_active=False)
        super_inativo = get_user_model().objects.create_superuser(username="super_inativo_ficticio", password=None,
                                                                  is_active=False)
        for usuario in (inativo, super_inativo):
            with self.subTest(usuario=usuario.username):
                self.assertFalse(e_administrador(usuario))

    def test_desativado_depois_do_login_nao_e_administrador(self):
        usuario = get_user_model().objects.get(pk=self.administrador.pk)
        get_user_model().objects.filter(pk=usuario.pk).update(is_active=False)
        self.assertTrue(usuario.is_active)  # objeto em memória desatualizado
        self.assertFalse(e_administrador(usuario))

    def test_sem_grupo_equipe_anonimo_e_nao_salvo_nao_sao_administradores(self):
        comum = membro("comum_perfil_ficticio")
        equipe = membro("equipe_admin_ficticia", GRUPO_EQUIPE)
        nao_salvo = get_user_model()(username="nao_salvo_perfil_ficticio", is_superuser=True)
        for usuario in (None, AnonymousUser(), comum, equipe, nao_salvo):
            with self.subTest(usuario=usuario):
                self.assertFalse(e_administrador(usuario))

    def test_removido_do_grupo_deixa_de_ser_administrador(self):
        self.administrador.groups.clear()
        self.assertFalse(e_administrador(self.administrador))

    def test_administrador_com_is_staff_abre_contas_no_admin(self):
        get_user_model().objects.filter(pk=self.administrador.pk).update(is_staff=True)
        self.client.force_login(self.administrador)
        self.assertEqual(self.client.get(reverse("admin:auth_user_changelist")).status_code, 200)

    def test_administrador_ve_gestao_de_colaboradores_sem_is_staff(self):
        """RF-USR-03: o menu e o cartão apontam para as telas próprias, não para o admin do Django."""
        self.client.force_login(self.administrador)
        resposta = self.client.get(reverse("inicio"))
        self.assertContains(resposta, "Gestão de Colaboradores")
        self.assertContains(resposta, reverse("usuarios:lista"))
        self.assertNotContains(resposta, reverse("admin:auth_user_changelist"))
        self.assertEqual(self.client.get(reverse("usuarios:lista")).status_code, 200)

    def test_administrador_cadastra_participante(self):
        participante = cadastrar_participante(usuario=self.administrador, data_entrada=ENTRADA, **DADOS)
        self.assertTrue(Participante.objects.filter(pk=participante.pk).exists())
