"""RNF-SEG-07: auditoria comum (core.EventoAuditoria) imutável e protegendo os objetos auditados.

Dados fictícios (RN-SEG-02).
"""

from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from atividades.models import Atividade, RegistroCadastroAtividade
from core.models import TIPOS_AUDITORIA, AuditoriaImutavel, EventoAuditoria, eventos_do_objeto, tipos_do_modelo
from participantes.models import Participante, RegistroParticipante


def criar_participante(nome="Pessoa Fictícia Auditoria"):
    return Participante.objects.create(
        nome_completo=nome, data_nascimento=date(1950, 3, 15), sexo="F", raca_cor="parda",
        identidade_genero="mulher_cis", endereco="Rua Fictícia, 100", ensino_medio_completo=True,
        telefone_celular="61912345678", origem_encaminhamento="cras",
    )


class EventoImutavelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="auditor_ficticio")
        cls.participante = criar_participante()
        cls.evento = RegistroParticipante.objects.create(participante=cls.participante, usuario=cls.usuario,
                                                         acao="cadastro", novos={"nome_completo": "Fictícia"})

    def test_save_de_evento_existente_e_recusado(self):
        evento = EventoAuditoria.objects.get(pk=self.evento.pk)
        evento.novos = {"nome_completo": "Alterado"}
        with self.assertRaises(AuditoriaImutavel):
            evento.save()
        self.assertEqual(EventoAuditoria.objects.get(pk=self.evento.pk).novos, {"nome_completo": "Fictícia"})

    def test_save_de_evento_existente_pelo_proxy_e_recusado(self):
        evento = RegistroParticipante.objects.get(pk=self.evento.pk)
        evento.acao = "correcao"
        with self.assertRaises(AuditoriaImutavel):
            evento.save(update_fields=["acao"])

    def test_delete_de_instancia_e_recusado(self):
        with self.assertRaises(AuditoriaImutavel):
            EventoAuditoria.objects.get(pk=self.evento.pk).delete()
        with self.assertRaises(AuditoriaImutavel):
            self.evento.delete()
        self.assertTrue(EventoAuditoria.objects.filter(pk=self.evento.pk).exists())

    def test_queryset_update_e_recusado(self):
        with self.assertRaises(AuditoriaImutavel):
            EventoAuditoria.objects.filter(pk=self.evento.pk).update(acao="adulterado")
        with self.assertRaises(AuditoriaImutavel):
            RegistroParticipante.objects.all().update(novos={})
        self.assertEqual(EventoAuditoria.objects.get(pk=self.evento.pk).acao, "cadastro")

    def test_queryset_delete_e_recusado(self):
        with self.assertRaises(AuditoriaImutavel):
            EventoAuditoria.objects.filter(pk=self.evento.pk).delete()
        with self.assertRaises(AuditoriaImutavel):
            RegistroParticipante.objects.all().delete()
        self.assertTrue(EventoAuditoria.objects.filter(pk=self.evento.pk).exists())

    def test_tipo_nao_registrado_e_recusado(self):
        self.assertNotIn("TipoInexistenteFicticio", TIPOS_AUDITORIA)
        with self.assertRaises(IntegrityError):
            EventoAuditoria.objects.create(tipo="TipoInexistenteFicticio", alvo_id=1, usuario=self.usuario, novos={})
        with self.assertRaises(IntegrityError):
            EventoAuditoria(tipo="", alvo_id=1, usuario=self.usuario, novos={}).save()
        self.assertFalse(EventoAuditoria.objects.filter(tipo="TipoInexistenteFicticio").exists())

    def test_tipo_registrado_pela_base_e_aceito(self):
        evento = EventoAuditoria.objects.create(tipo="RegistroParticipante", alvo_id=self.participante.pk,
                                                usuario=self.usuario, novos={"x": 1})
        self.assertIn(evento.pk, RegistroParticipante.objects.values_list("pk", flat=True))

    def test_proxy_grava_o_proprio_nome_como_tipo(self):
        evento = RegistroParticipante(tipo="RegistroCadastroAtividade", alvo_id=self.participante.pk,
                                      usuario=self.usuario, novos={})
        evento.save()
        self.assertEqual(EventoAuditoria.objects.get(pk=evento.pk).tipo, "RegistroParticipante")


class ProxyEAlvoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="auditor_proxy_ficticio")
        cls.participante = criar_participante()
        cls.atividade = Atividade.objects.create(nome="Oficina fictícia", local="Sala 1", monitor="Monitor fictício")
        cls.evento_participante = RegistroParticipante.objects.create(
            participante=cls.participante, usuario=cls.usuario, acao="cadastro", novos={})
        # Mesmo alvo_id numérico em outro tipo: o proxy não pode misturá-los.
        cls.evento_atividade = RegistroCadastroAtividade.objects.create(
            alvo_id=cls.participante.pk, usuario=cls.usuario, novos={})

    def test_proxy_filtra_somente_o_proprio_tipo(self):
        self.assertEqual(list(RegistroParticipante.objects.values_list("pk", flat=True)),
                         [self.evento_participante.pk])
        self.assertEqual(list(RegistroCadastroAtividade.objects.values_list("pk", flat=True)),
                         [self.evento_atividade.pk])
        self.assertEqual(RegistroParticipante.objects.filter(alvo_id=self.participante.pk).count(), 1)
        self.assertEqual(EventoAuditoria.objects.filter(alvo_id=self.participante.pk).count(), 2)

    def test_proxy_traduz_filtro_pelo_alvo(self):
        self.assertEqual(RegistroParticipante.objects.get(participante=self.participante).pk,
                         self.evento_participante.pk)
        self.assertEqual(RegistroParticipante.objects.get(participante_id=self.participante.pk).pk,
                         self.evento_participante.pk)
        self.assertEqual(RegistroParticipante.objects.filter(participante__in=[self.participante]).count(), 1)
        self.assertEqual(RegistroParticipante.objects.filter(
            participante__nome_completo=self.participante.nome_completo).count(), 1)

    def test_alvo_id_coerente_com_o_objeto(self):
        evento = RegistroParticipante.objects.get(pk=self.evento_participante.pk)
        self.assertEqual(evento.alvo_id, self.participante.pk)
        self.assertEqual(evento.participante_id, self.participante.pk)
        self.assertEqual(evento.participante, self.participante)
        self.assertEqual(evento.objeto_alvo, self.participante)
        evento_base = EventoAuditoria.objects.get(pk=self.evento_participante.pk)
        self.assertEqual(evento_base.objeto_alvo, self.participante)

    def test_alvo_de_outro_tipo_e_recusado(self):
        with self.assertRaises(IntegrityError):
            RegistroParticipante.objects.create(atividade=self.atividade, usuario=self.usuario, novos={})
        with self.assertRaises(IntegrityError):
            RegistroParticipante.objects.create(participante=self.atividade, usuario=self.usuario, novos={})
        with self.assertRaises(IntegrityError):
            RegistroParticipante.objects.create(participante=self.participante, atividade=self.atividade,
                                                usuario=self.usuario, novos={})
        self.assertEqual(RegistroParticipante.objects.count(), 1)

    def test_tipos_do_modelo_e_eventos_do_objeto(self):
        self.assertEqual(tipos_do_modelo(Participante), ["RegistroParticipante"])
        self.assertEqual(list(eventos_do_objeto(self.participante)), [EventoAuditoria.objects.get(
            pk=self.evento_participante.pk)])

    def test_ordem_por_registrado_em(self):
        participante = criar_participante("Outra Pessoa Fictícia")
        base = timezone.make_aware(datetime(2024, 5, 10, 12, 0))
        tarde = RegistroParticipante.objects.create(participante=participante, usuario=self.usuario,
                                                    registrado_em=base + timedelta(hours=2), novos={"ordem": 3})
        cedo = RegistroParticipante.objects.create(participante=participante, usuario=self.usuario,
                                                   registrado_em=base, novos={"ordem": 1})
        meio = RegistroParticipante.objects.create(participante=participante, usuario=self.usuario,
                                                   registrado_em=base + timedelta(hours=1), novos={"ordem": 2})
        self.assertEqual(list(RegistroParticipante.objects.filter(participante=participante)),
                         [cedo, meio, tarde])
        self.assertEqual([evento.novos["ordem"] for evento in eventos_do_objeto(participante)], [1, 2, 3])


class ProtecaoDeExclusaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="auditor_protecao_ficticio")

    def test_usuario_com_eventos_nao_pode_ser_excluido(self):
        autor = get_user_model().objects.create_user(username="autor_eventos_ficticio")
        RegistroParticipante.objects.create(participante=criar_participante(), usuario=autor, novos={})
        with self.assertRaises(ProtectedError):
            autor.delete()
        with transaction.atomic(), self.assertRaises(ProtectedError):
            get_user_model().objects.filter(pk=autor.pk).delete()
        self.assertTrue(get_user_model().objects.filter(pk=autor.pk).exists())

    def test_usuario_sem_eventos_pode_ser_excluido(self):
        autor = get_user_model().objects.create_user(username="autor_sem_eventos_ficticio")
        autor.delete()
        self.assertFalse(get_user_model().objects.filter(username="autor_sem_eventos_ficticio").exists())

    def test_objeto_auditado_nao_pode_ser_excluido_pela_instancia(self):
        participante = criar_participante()
        RegistroParticipante.objects.create(participante=participante, usuario=self.usuario, novos={})
        with self.assertRaises(ProtectedError):
            participante.delete()
        # A verificação ocorre antes da transação do Collector: a transação do teste segue utilizável.
        self.assertTrue(Participante.objects.filter(pk=participante.pk).exists())

    def test_objeto_auditado_nao_pode_ser_excluido_pelo_queryset(self):
        participante = criar_participante()
        RegistroParticipante.objects.create(participante=participante, usuario=self.usuario, novos={})
        with transaction.atomic(), self.assertRaises(ProtectedError):
            Participante.objects.filter(pk=participante.pk).delete()
        self.assertTrue(Participante.objects.filter(pk=participante.pk).exists())

    def test_outro_modelo_auditado_tambem_protegido(self):
        atividade = Atividade.objects.create(nome="Oficina protegida", local="Sala 2", monitor="Monitor fictício")
        RegistroCadastroAtividade.objects.create(atividade=atividade, usuario=self.usuario, novos={})
        with self.assertRaises(ProtectedError):
            atividade.delete()
        with transaction.atomic(), self.assertRaises(ProtectedError):
            Atividade.objects.filter(pk=atividade.pk).delete()
        self.assertTrue(Atividade.objects.filter(pk=atividade.pk).exists())

    def test_evento_de_outro_tipo_com_mesmo_alvo_id_nao_protege(self):
        participante = criar_participante()
        RegistroCadastroAtividade.objects.create(alvo_id=participante.pk, usuario=self.usuario, novos={})
        participante.delete()
        self.assertFalse(Participante.objects.filter(pk=participante.pk).exists())

    def test_objeto_sem_eventos_pode_ser_excluido_pela_instancia(self):
        participante = criar_participante()
        participante.delete()
        self.assertFalse(Participante.objects.filter(pk=participante.pk).exists())

    def test_objeto_sem_eventos_pode_ser_excluido_pelo_queryset(self):
        participantes = [criar_participante("Fictícia Um"), criar_participante("Fictícia Dois")]
        Participante.objects.filter(pk__in=[p.pk for p in participantes]).delete()
        self.assertFalse(Participante.objects.filter(pk__in=[p.pk for p in participantes]).exists())

    def test_queryset_misto_e_bloqueado_por_inteiro(self):
        livre = criar_participante("Fictícia Livre")
        auditado = criar_participante("Fictícia Auditada")
        RegistroParticipante.objects.create(participante=auditado, usuario=self.usuario, novos={})
        with transaction.atomic(), self.assertRaises(ProtectedError):
            Participante.objects.filter(pk__in=[livre.pk, auditado.pk]).delete()
        self.assertEqual(Participante.objects.filter(pk__in=[livre.pk, auditado.pk]).count(), 2)
