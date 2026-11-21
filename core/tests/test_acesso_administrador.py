"""Regressão do administrador criado pelas telas, sem permissões de demonstração."""

from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.sql import emit_post_migrate_signal
from django.test import TestCase, override_settings
from django.urls import reverse

from atividades.models import Aula, Frequencia
from atividades.services import cadastrar_atividade, inscrever_participante
from core.perfis import GRUPO_ADMINISTRADOR
from participantes.services import cadastrar_participante
from usuarios.services import cadastrar_colaborador


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False,
                   NCI_PARTICIPANTES_PROVIDER="participantes.provedor.ProvedorParticipantes")
class AcessoAdministradorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        autor = get_user_model().objects.create_superuser(username="configurador_ficticio", password=None)
        cls.admin = cadastrar_colaborador(
            usuario=autor, username="admin_site_ficticio", first_name="Operadora", last_name="Fictícia",
            email="operadora@example.org", perfil=GRUPO_ADMINISTRADOR, senha="ChamadaCompleta!2026",
        )
        cls.atividade = cadastrar_atividade(usuario=cls.admin, nome="Oficina fictícia", local="Sala", monitor="Equipe")
        pessoa = cadastrar_participante(
            usuario=cls.admin, data_entrada=date(2024, 1, 1), nome_completo="Ana Fictícia do Acesso",
            data_nascimento=date(1950, 1, 1), sexo="F", raca_cor="parda", identidade_genero="cisgenero",
            endereco="Rua Fictícia, 10", telefone_celular="11912345678", telefone_residencial="",
            ensino_medio_completo=True, origem_encaminhamento="cras", observacao_encaminhamento="",
        )
        cls.inscricao = inscrever_participante(
            usuario=cls.admin, atividade_id=cls.atividade.pk, participante_referencia=str(pessoa.pk),
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_criado_como_administrador_acessa_todas_as_telas_operacionais(self):
        self.assertFalse(self.admin.is_superuser)
        self.assertFalse(self.admin.is_staff)
        self.assertFalse(self.admin.user_permissions.exists())
        self.assertEqual(list(self.admin.groups.values_list("name", flat=True)), [GRUPO_ADMINISTRADOR])
        for rota in ("participantes:lista", "participantes:cadastrar", "atividades:lista",
                     "atividades:registro_diario", "atividades:frequencia_mensal",
                     "atividades:categorias_fmr", "usuarios:lista", "usuarios:cadastrar", "relatorios:fmr"):
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(reverse(rota)).status_code, 200)

    def test_admin_salva_chamada_real_e_consulta_o_total_mensal(self):
        dados = {"atividade": self.atividade.pk, "tipo": "regular", "data": "2024-02-29",
                 "inicio": "09:00", "fim": "10:00", f"registro_{self.inscricao.pk}": "presente"}
        resposta = self.client.post(reverse("atividades:registro_diario"), dados)
        aula = Aula.objects.get()
        self.assertRedirects(resposta, reverse("atividades:chamada", args=[self.atividade.pk, aula.pk]))
        self.assertEqual(Frequencia.objects.get().situacao, "presente")
        mensal = self.client.get(reverse("atividades:frequencia_mensal"), {"mes": "2024-02"})
        self.assertEqual(mensal.status_code, 200)
        self.assertEqual(mensal.context["totais"]["presentes"], 1)

    def test_migrate_repara_grupo_antigo_sem_trocar_flags_ou_permissoes_da_conta(self):
        grupo = Group.objects.get(name=GRUPO_ADMINISTRADOR)
        grupo.permissions.remove(*grupo.permissions.filter(content_type__app_label="atividades")
                                 .exclude(codename="view_atividade"))
        for rota in ("atividades:registro_diario", "atividades:frequencia_mensal"):
            self.assertEqual(self.client.get(reverse(rota)).status_code, 403)
        emit_post_migrate_signal(verbosity=0, interactive=False, db="default")
        for rota in ("atividades:registro_diario", "atividades:frequencia_mensal"):
            self.assertEqual(self.client.get(reverse(rota)).status_code, 200)
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_superuser)
        self.assertFalse(self.admin.is_staff)
        self.assertFalse(self.admin.user_permissions.exists())

    def test_remover_perfil_revoga_acesso_operacional(self):
        self.admin.groups.clear()
        for rota in ("atividades:registro_diario", "atividades:frequencia_mensal", "atividades:categorias_fmr"):
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(reverse(rota)).status_code, 403)

    def test_desativar_conta_revoga_acesso_operacional(self):
        get_user_model().objects.filter(pk=self.admin.pk).update(is_active=False)
        for rota in ("atividades:registro_diario", "atividades:frequencia_mensal", "atividades:categorias_fmr"):
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(reverse(rota)).status_code, 302)
