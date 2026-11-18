from datetime import date, time
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from core.models import EventoAuditoria
from participantes.models import Movimentacao, MotivoDesligamento
from participantes.tests.test_models import novo_participante
from participantes.movimentacoes import movimentar_participante, salvar_motivo
from participantes.consultas import permanentes_em
from relatorios.services import consultar_permanentes_fmr


class CicloParticipanteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_user(username="admin_ciclo_ficticio")
        cls.admin.groups.add(Group.objects.get(name="Administrador"))
        cls.equipe = get_user_model().objects.create_user(username="equipe_ciclo_ficticia")
        cls.equipe.groups.add(Group.objects.get(name="Equipe"))
        cls.pessoa = novo_participante()
        cls.pessoa.save()
        Movimentacao.objects.create(participante=cls.pessoa, usuario=cls.admin, tipo="entrada", data=date(2024, 1, 1))

    def motivo(self):
        return salvar_motivo(usuario=self.admin, descricao="Motivo fictício para teste")

    def mover(self, tipo, dia, **extra):
        return movimentar_participante(usuario=self.equipe, participante_id=self.pessoa.pk,
            tipo=tipo, data=date(2024, *dia), **extra)

    def refs(self, data):
        return {p.referencia for p in permanentes_em(usuario=self.equipe, data_referencia=data)}

    def test_catalogo_vazio_impede_desligamento_e_somente_admin_cadastra(self):
        MotivoDesligamento.objects.all().delete()
        self.assertFalse(MotivoDesligamento.objects.exists())
        with self.assertRaises(ValidationError):
            self.mover("desligamento", (2, 1))
        with self.assertRaises(PermissionDenied):
            salvar_motivo(usuario=self.equipe, descricao="Fictício")
        self.assertEqual(self.pessoa.movimentacoes.count(), 1)

    def test_desligamento_reativacao_preserva_identidade_e_historico_mensal(self):
        motivo = self.motivo()
        self.mover("desligamento", (2, 29), motivo_id=motivo.pk)
        self.assertIn(str(self.pessoa.pk), self.refs(date(2024, 2, 28)))
        self.assertNotIn(str(self.pessoa.pk), self.refs(date(2024, 2, 29)))
        self.mover("reativacao", (3, 10))
        self.assertIn(str(self.pessoa.pk), self.refs(date(2024, 3, 10)))
        self.assertNotIn(str(self.pessoa.pk), self.refs(date(2024, 3, 9)))
        self.assertEqual(self.pessoa.movimentacoes.filter(tipo="entrada").count(), 1)
        self.assertEqual(consultar_permanentes_fmr(usuario=self.equipe, ano=2024, mes=2)["total"], 0)
        self.assertEqual(consultar_permanentes_fmr(usuario=self.equipe, ano=2024, mes=3)["total"], 1)
        self.assertEqual(EventoAuditoria.objects.filter(tipo="RegistroParticipante").count(), 2)

    def test_afastado_permanece_no_servico_e_retorna_sem_nova_entrada(self):
        self.mover("afastamento", (2, 1))
        self.pessoa.refresh_from_db()
        self.assertEqual(self.pessoa.status, "afastado")
        self.assertIn(str(self.pessoa.pk), self.refs(date(2024, 2, 29)))
        self.mover("retorno", (3, 1))
        self.pessoa.refresh_from_db()
        self.assertEqual(self.pessoa.status, "ativo")
        self.assertEqual(self.pessoa.movimentacoes.filter(tipo="entrada").count(), 1)

    def test_motivo_editado_ou_inativo_nao_altera_snapshot_de_desligamento(self):
        motivo = self.motivo()
        movimento = self.mover("desligamento", (2, 1), motivo_id=motivo.pk)
        salvar_motivo(usuario=self.admin, motivo_id=motivo.pk, descricao="Descrição corrigida", ativo=False)
        movimento.refresh_from_db()
        self.assertEqual(movimento.motivo_descricao, "Motivo fictício para teste")
        self.mover("reativacao", (3, 1))
        with self.assertRaises(ValidationError):
            self.mover("desligamento", (3, 2), motivo_id=motivo.pk)

    def test_transicoes_datas_e_repeticoes_invalidas_nao_gravam(self):
        for tipo in ("retorno", "reativacao", "invalido"):
            with self.assertRaises(ValidationError):
                self.mover(tipo, (2, 1))
        with self.assertRaises(ValidationError):
            self.mover("afastamento", (1, 1), motivo_id=self.motivo().pk)
        self.mover("afastamento", (2, 1))
        with self.assertRaises(ValidationError):
            self.mover("afastamento", (2, 2))
        with self.assertRaises(ValidationError):
            self.mover("retorno", (1, 31))
        with self.assertRaises(ValidationError):
            movimentar_participante(usuario=self.equipe, participante_id=self.pessoa.pk, tipo="retorno", data=date(9999, 1, 1))
        self.assertEqual(self.pessoa.movimentacoes.count(), 2)

    def test_falha_de_auditoria_reverte_status_e_movimentacao(self):
        with patch("participantes.movimentacoes.registrar", side_effect=RuntimeError), self.assertRaises(RuntimeError):
            self.mover("afastamento", (2, 1))
        self.pessoa.refresh_from_db()
        self.assertEqual(self.pessoa.status, "ativo")
        self.assertEqual(self.pessoa.movimentacoes.count(), 1)

    def test_acervo_sem_entrada_ou_status_ambiguo_sinaliza_pendencia(self):
        self.pessoa.status = "inativo"
        self.pessoa.save(update_fields=["status"])
        self.assertIsNone(permanentes_em(usuario=self.equipe, data_referencia=date(2024, 2, 29)))
        self.pessoa.status = "ativo"
        self.pessoa.save(update_fields=["status"])
        self.pessoa.movimentacoes.all().delete()
        self.assertIsNone(consultar_permanentes_fmr(usuario=self.equipe, ano=2024, mes=2)["total"])

    def test_mes_antes_da_entrada_e_mes_vazio_retornam_zero_real(self):
        self.assertEqual(self.refs(date(2023, 12, 31)), set())
        self.assertEqual(consultar_permanentes_fmr(usuario=self.equipe, ano=2023, mes=12)["total"], 0)

    @override_settings(NCI_PARTICIPANTES_PROVIDER="participantes.provedor.ProvedorParticipantes")
    def test_afastamento_retroativo_justifica_ausencia_existente_e_retorno_restringe_periodo(self):
        from atividades.models import Atividade, Aula, Inscricao, Frequencia, RegistroCorrecaoFrequencia
        atividade = Atividade.objects.create(nome="Oficina fictícia", local="Sala", monitor="Teste")
        inscricao = Inscricao.objects.create(atividade=atividade, origem_participante="participantes",
            participante_referencia=str(self.pessoa.pk), cadastrada_por=self.equipe)
        aula = Aula.objects.create(atividade=atividade, data=date(2024, 2, 15), inicio=time(9), fim=time(10))
        frequencia = Frequencia.objects.create(aula=aula, inscricao=inscricao, situacao="ausente")
        self.mover("afastamento", (2, 1))
        frequencia.refresh_from_db()
        self.assertEqual(frequencia.situacao, "ausente_justificado")
        self.assertTrue(frequencia.justificada_por_afastamento)
        self.mover("retorno", (2, 10))
        frequencia.refresh_from_db()
        self.assertEqual(frequencia.situacao, "ausente")
        self.assertFalse(frequencia.justificada_por_afastamento)
        self.assertEqual(RegistroCorrecaoFrequencia.objects.filter(frequencia=frequencia).count(), 2)

    def test_interface_motivos_movimentacao_permissoes_e_sem_escrita_get(self):
        MotivoDesligamento.objects.all().delete()
        self.client.force_login(self.equipe)
        url = reverse("participantes:movimentar", args=[self.pessoa.pk])
        self.assertContains(self.client.get(url), "Não há motivos ativos cadastrados")
        self.assertEqual(self.pessoa.movimentacoes.count(), 1)
        self.assertEqual(self.client.get(reverse("participantes:motivos_desligamento")).status_code, 403)
        resposta = self.client.post(url, {"tipo": "afastamento", "data": "2024-02-01"})
        self.assertEqual(resposta.status_code, 302)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse("participantes:motivos_desligamento"),
            {"descricao": "Motivo fictício", "ativo": "on"}).status_code, 302)

    @override_settings(NCI_PARTICIPANTES_PROVIDER="participantes.provedor.ProvedorParticipantes")
    def test_ausencias_de_afastado_justificadas_presencas_permitidas_e_desligado_bloqueado(self):
        from atividades.models import Atividade, Aula, Inscricao
        from atividades.services import registrar_frequencias
        self.equipe.user_permissions.add(*Permission.objects.filter(content_type__app_label="atividades"))
        atividade = Atividade.objects.create(nome="Oficina fictícia", local="Sala", monitor="Teste")
        inscricao = Inscricao.objects.create(atividade=atividade, origem_participante="participantes",
            participante_referencia=str(self.pessoa.pk), cadastrada_por=self.equipe)
        def aula(dia):
            return Aula.objects.create(atividade=atividade, data=date(2024, 2, dia), inicio=time(9), fim=time(10))
        def lancar(dia, situacao):
            return registrar_frequencias(usuario=self.equipe, atividade_id=atividade.pk, aula_id=aula(dia).pk,
                registros={inscricao.pk: situacao})[0]
        self.mover("afastamento", (2, 2))
        self.assertEqual(lancar(1, "ausente").situacao, "ausente")
        falta = lancar(2, "ausente")
        self.assertEqual((falta.situacao, falta.motivo_descricao), ("ausente_justificado", "Afastamento"))
        self.assertEqual(lancar(3, "presente").situacao, "presente")
        self.mover("retorno", (2, 4))
        self.assertEqual(lancar(4, "ausente").situacao, "ausente")
        self.mover("desligamento", (2, 5), motivo_id=self.motivo().pk)
        with self.assertRaises(ValidationError):
            lancar(5, "presente")
