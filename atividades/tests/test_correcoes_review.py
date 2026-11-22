"""Correções do code review em atividades (22/11/2026). Dados fictícios (RN-SEG-02).

- aula realizada duplicada (mesma atividade, data e início) e com data futura;
- chamada retroativa: quem não fazia parte da turma fica sem situação e sem frequência;
- justificativa escolhida pela equipe para afastado não é revertida no retorno;
- afastado sai da lista de espera, não entra nela e não é atendido (NCI 21/11);
- autorização pelo core, sem importar `usuarios`.
"""
import ast
from datetime import date, time, timedelta
from pathlib import Path

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from atividades.ajustes_afastamento import atualizar_ausencias
from atividades.chamada_unificada import salvar_chamada
from atividades.espera import adicionar_espera, primeiro_da_fila
from atividades.integracoes.participantes import obter_provedor
from atividades.integracoes.participantes_placeholder import ProvedorPlaceholder
from atividades.models import (
    MENSAGEM_AULA_DUPLICADA, Atividade, Aula, EsperaAtividade, Frequencia, Inscricao, RegistroEsperaAtividade,
)
from atividades.services import (
    cancelar_aula, inscrever_participante, registrar_aula, registrar_aula_cancelada, registrar_frequencias,
)
from atividades.situacao import alterar_situacao_atividade
from usuarios.tests.base import administrador, equipe

PLACEHOLDER = "atividades.integracoes.participantes_placeholder.ProvedorPlaceholder"
COM_SITUACOES = "atividades.tests.test_correcoes_review.ProvedorComSituacoes"

# referencia -> [(desde, tipo)], em ordem; o teste controla as situações por data.
MOVIMENTOS = {}


class ProvedorComSituacoes(ProvedorPlaceholder):
    """Placeholder com `situacoes_em` controlada pelo teste (o placeholder real não tem situações)."""

    def situacoes_em(self, data):
        estados = {}
        for referencia, movimentos in MOVIMENTOS.items():
            vigentes = [tipo for desde, tipo in movimentos if desde <= data]
            if vigentes:
                estados[referencia] = vigentes[-1]
        return estados


def usuario_atividades(username, *extras):
    usuario = get_user_model().objects.create_user(username=username, email=f"{username}@example.org")
    usuario.user_permissions.add(*Permission.objects.filter(content_type__app_label="atividades"))
    for app_label, codename in extras:
        usuario.user_permissions.add(Permission.objects.get(content_type__app_label=app_label, codename=codename))
    return get_user_model().objects.get(pk=usuario.pk)


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = usuario_atividades("revisao_ficticia", ("participantes", "change_participante"))
        cls.atividade = Atividade.objects.create(nome="Oficina fictícia", local="Sala", monitor="Fictício")

    def setUp(self):
        MOVIMENTOS.clear()
        self.addCleanup(MOVIMENTOS.clear)

    def inscrever(self, referencia, atividade=None):
        return Inscricao.objects.create(atividade=atividade or self.atividade, origem_participante="placeholder",
                                        participante_referencia=referencia, cadastrada_por=self.usuario)

    def aula(self, data=date(2024, 2, 15), inicio=time(9), **extra):
        return registrar_aula(usuario=self.usuario, atividade_id=self.atividade.pk, data=data, inicio=inicio,
                              fim=time(inicio.hour + 1), **extra)


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False, NCI_PARTICIPANTES_PROVIDER=PLACEHOLDER)
class AulaDuplicadaTests(Base):
    def test_realizada_repetida_e_recusada_canceladas_e_outro_inicio_nao(self):
        primeira = self.aula()
        with self.assertRaisesMessage(ValidationError, MENSAGEM_AULA_DUPLICADA):
            self.aula()
        self.aula(inicio=time(14))
        for _ in range(2):
            registrar_aula_cancelada(usuario=self.usuario, atividade_id=self.atividade.pk, data=date(2024, 2, 15),
                                     inicio=time(9), fim=time(10))
        self.assertEqual(Aula.objects.realizadas().count(), 2)
        # Cancelada a realizada, a ocorrência pode ser registrada de novo como realizada.
        cancelar_aula(usuario=self.usuario, atividade_id=self.atividade.pk, aula_id=primeira.pk)
        self.aula()
        self.assertEqual(Aula.objects.realizadas().count(), 2)

    def test_outra_atividade_no_mesmo_horario_e_permitida(self):
        outra = Atividade.objects.create(nome="Outra fictícia", local="Sala", monitor="Fictício")
        self.aula()
        registrar_aula(usuario=self.usuario, atividade_id=outra.pk, data=date(2024, 2, 15), inicio=time(9), fim=time(10))
        self.assertEqual(Aula.objects.count(), 2)

    def test_constraint_do_banco_barra_gravacao_fora_do_servico(self):
        Aula.objects.create(atividade=self.atividade, data=date(2024, 2, 15), inicio=time(9), fim=time(10))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Aula.objects.create(atividade=self.atividade, data=date(2024, 2, 15), inicio=time(9), fim=time(11))
        Aula.objects.create(atividade=self.atividade, data=date(2024, 2, 15), inicio=time(9), fim=time(10),
                            situacao="cancelada")

    def test_duplo_envio_da_nova_chamada_grava_uma_aula(self):
        inscricao = self.inscrever("demo-1")
        self.client.force_login(self.usuario)
        url = reverse("atividades:registro_diario")
        resposta = self.client.get(url, {"atividade": self.atividade.pk})
        self.assertContains(resposta, "data-salvar-chamada")
        dados = {"atividade": self.atividade.pk, "tipo": "regular", "data": "2024-02-15", "inicio": "09:00",
                 "fim": "10:00", f"registro_{inscricao.pk}": "presente"}
        self.assertEqual(self.client.post(url, dados).status_code, 302)
        resposta = self.client.post(url, dados)
        self.assertContains(resposta, "Já existe uma aula realizada desta atividade nesta data")
        self.assertEqual(Aula.objects.count(), 1)
        self.assertEqual(Frequencia.objects.count(), 1)


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False, NCI_PARTICIPANTES_PROVIDER=PLACEHOLDER)
class DataFuturaTests(Base):
    def test_realizada_futura_e_recusada_cancelada_futura_nao(self):
        amanha = timezone.localdate() + timedelta(days=1)
        with self.assertRaises(ValidationError) as erro:
            self.aula(data=amanha)
        self.assertIn("data", erro.exception.message_dict)
        self.assertFalse(Aula.objects.exists())
        registrar_aula_cancelada(usuario=self.usuario, atividade_id=self.atividade.pk, data=amanha,
                                 inicio=time(9), fim=time(10))
        self.aula(data=timezone.localdate())
        self.assertEqual(Aula.objects.count(), 2)

    def test_nova_chamada_com_data_futura_nao_grava(self):
        inscricao = self.inscrever("demo-1")
        self.client.force_login(self.usuario)
        amanha = timezone.localdate() + timedelta(days=1)
        resposta = self.client.post(reverse("atividades:registro_diario"), {
            "atividade": self.atividade.pk, "tipo": "regular", "data": amanha.isoformat(), "inicio": "09:00",
            "fim": "10:00", f"registro_{inscricao.pk}": "presente"})
        self.assertContains(resposta, "Aula realizada não pode ter data futura")
        self.assertFalse(Aula.objects.exists())


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False, NCI_PARTICIPANTES_PROVIDER=PLACEHOLDER)
class ChamadaRetroativaTests(Base):
    def setUp(self):
        super().setUp()
        self.antiga = self.inscrever("demo-1")
        # Inscrição de carga inicial: cadastrada hoje, mas a pessoa só entrou na turma depois da aula retroativa.
        self.nova = self.inscrever("demo-2")
        self.client.force_login(self.usuario)
        self.url = reverse("atividades:registro_diario")
        self.dados = {"atividade": self.atividade.pk, "tipo": "regular", "data": "2024-02-15", "inicio": "09:00",
                      "fim": "10:00", f"registro_{self.antiga.pk}": "presente", f"registro_{self.nova.pk}": ""}

    def test_tela_oferece_sem_situacao(self):
        resposta = self.client.get(self.url, {"atividade": self.atividade.pk})
        self.assertContains(resposta, "Sem situação")
        self.assertContains(resposta, f'name="registro_{self.nova.pk}" value=""')

    def test_quem_fica_sem_situacao_nao_recebe_frequencia(self):
        resposta = self.client.post(self.url, self.dados)
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(list(Frequencia.objects.values_list("inscricao_id", "situacao")),
                         [(self.antiga.pk, "presente")])

    def test_todos_sem_situacao_nao_grava_aula(self):
        resposta = self.client.post(self.url, self.dados | {f"registro_{self.antiga.pk}": ""})
        self.assertContains(resposta, "Selecione ao menos uma situação")
        self.assertFalse(Aula.objects.exists())

    def test_campo_ausente_do_post_ainda_indica_tela_desatualizada(self):
        dados = dict(self.dados)
        del dados[f"registro_{self.nova.pk}"]
        self.assertContains(self.client.post(self.url, dados), "Confira a situação de todos")
        self.assertFalse(Aula.objects.exists())

    def test_servico_aceita_subconjunto_mas_so_de_inscricoes_da_atividade(self):
        dados_aula = {"data": date(2024, 2, 15), "inicio": time(9), "fim": time(10), "tipo": "regular"}
        outra = Atividade.objects.create(nome="Outra fictícia", local="Sala", monitor="Fictício")
        alheia = self.inscrever("demo-3", atividade=outra)
        for registros in ({alheia.pk: "presente"}, {self.antiga.pk: "presente", alheia.pk: "ausente"}, {}):
            with self.subTest(registros=registros), self.assertRaises(ValidationError):
                salvar_chamada(usuario=self.usuario, atividade_id=self.atividade.pk, dados_aula=dados_aula,
                               registros=registros)
        self.assertFalse(Aula.objects.exists())
        salvar_chamada(usuario=self.usuario, atividade_id=self.atividade.pk, dados_aula=dados_aula,
                       registros={self.nova.pk: "ausente"})
        self.assertEqual(list(Frequencia.objects.values_list("inscricao_id", flat=True)), [self.nova.pk])

    def test_chamada_de_aula_existente_tambem_aceita_sem_situacao(self):
        aula = self.aula()
        resposta = self.client.post(reverse("atividades:lancar_frequencias", args=[self.atividade.pk, aula.pk]),
                                    {f"registro_{self.antiga.pk}": "", f"registro_{self.nova.pk}": "ausente"})
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(list(aula.frequencias.values_list("inscricao_id", flat=True)), [self.nova.pk])


@override_settings(DEBUG=True, NCI_PARTICIPANTES_PROVIDER=COM_SITUACOES)
class JustificativaDeAfastadoTests(Base):
    def setUp(self):
        super().setUp()
        self.manual = self.inscrever("demo-1")
        self.sem_detalhe = self.inscrever("demo-2")
        self.automatica = self.inscrever("demo-3")
        for referencia in ("demo-1", "demo-2", "demo-3"):
            MOVIMENTOS[referencia] = [(date(2024, 1, 1), "entrada"), (date(2024, 2, 1), "afastamento")]
        self.aula_fev = self.aula()

    def retornar(self, desde):
        for referencia in ("demo-1", "demo-2", "demo-3"):
            MOVIMENTOS[referencia].append((desde, "retorno"))
            atualizar_ausencias(usuario=self.usuario, origem="placeholder", referencia=referencia, desde=desde)

    def test_so_a_conversao_automatica_e_marcada_e_revertida_no_retorno(self):
        registrar_frequencias(usuario=self.usuario, atividade_id=self.atividade.pk, aula_id=self.aula_fev.pk,
            registros={self.manual.pk: "ausente_justificado", self.sem_detalhe.pk: "ausente_justificado",
                       self.automatica.pk: "ausente"},
            justificativas={self.manual.pk: {"observacao": "Atestado fictício"}})
        frequencias = {f.inscricao_id: f for f in Frequencia.objects.all()}
        self.assertEqual([(f.situacao, f.justificada_por_afastamento, f.motivo_descricao)
                          for f in (frequencias[self.manual.pk], frequencias[self.sem_detalhe.pk],
                                    frequencias[self.automatica.pk])],
                         [("ausente_justificado", False, ""), ("ausente_justificado", False, ""),
                          ("ausente_justificado", True, "Afastamento")])
        self.retornar(date(2024, 2, 10))
        situacoes = dict(Frequencia.objects.values_list("inscricao_id", "situacao"))
        self.assertEqual(situacoes, {self.manual.pk: "ausente_justificado",
                                     self.sem_detalhe.pk: "ausente_justificado", self.automatica.pk: "ausente"})
        self.assertEqual(Frequencia.objects.get(inscricao=self.manual).observacao, "Atestado fictício")

    def test_marca_antiga_com_observacao_nao_e_revertida(self):
        # Lançamentos anteriores à correção marcavam também a justificativa digitada pela equipe.
        legado = Frequencia.objects.create(aula=self.aula_fev, inscricao=self.manual, situacao="ausente_justificado",
            motivo_descricao="Afastamento", observacao="Digitada pela equipe", justificada_por_afastamento=True)
        self.retornar(date(2024, 2, 10))
        legado.refresh_from_db()
        self.assertEqual((legado.situacao, legado.observacao), ("ausente_justificado", "Digitada pela equipe"))


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False, NCI_PARTICIPANTES_PROVIDER=COM_SITUACOES)
class EsperaDeAfastadoTests(Base):
    def setUp(self):
        super().setUp()
        self.hoje = timezone.localdate()
        for referencia in ("demo-1", "demo-2", "demo-3"):
            MOVIMENTOS[referencia] = [(date(2024, 1, 1), "entrada")]

    def adicionar(self, referencia, atividade=None):
        return adicionar_espera(usuario=self.usuario, atividade_id=(atividade or self.atividade).pk,
                                participante_referencia=referencia)

    def afastar(self, referencia, avisar=True):
        MOVIMENTOS[referencia].append((self.hoje, "afastamento"))
        if avisar:
            atualizar_ausencias(usuario=self.usuario, origem="placeholder", referencia=referencia, desde=self.hoje)

    def test_afastado_nao_entra_na_espera(self):
        self.afastar("demo-1")
        with self.assertRaisesMessage(ValidationError, "Registre o retorno do participante afastado antes de adicionar à espera."):
            self.adicionar("demo-1")
        self.assertFalse(EsperaAtividade.objects.exists())

    def test_afastamento_retira_de_todas_as_esperas_com_auditoria(self):
        outra = Atividade.objects.create(nome="Outra fictícia", local="Sala", monitor="Fictício")
        esperas = [self.adicionar("demo-1"), self.adicionar("demo-1", atividade=outra)]
        vizinho = self.adicionar("demo-2")
        self.afastar("demo-1")
        for espera in esperas:
            espera.refresh_from_db()
            self.assertEqual(espera.situacao, "retirado")
            registro = RegistroEsperaAtividade.objects.filter(espera=espera).latest("pk")
            self.assertEqual((registro.anteriores, registro.novos),
                             ({"situacao": "aguardando"}, {"situacao": "retirado", "ajuste_automatico": "afastamento"}))
            self.assertEqual(registro.usuario_id, self.usuario.pk)
        vizinho.refresh_from_db()
        self.assertEqual(vizinho.situacao, "aguardando")

    def test_retorno_nao_mexe_na_espera(self):
        espera = self.adicionar("demo-1")
        MOVIMENTOS["demo-1"].append((self.hoje, "retorno"))
        atualizar_ausencias(usuario=self.usuario, origem="placeholder", referencia="demo-1", desde=self.hoje)
        espera.refresh_from_db()
        self.assertEqual(espera.situacao, "aguardando")

    def test_afastado_que_ficou_na_fila_nao_e_oferecido_nem_atendido(self):
        afastado = self.adicionar("demo-1")
        seguinte = self.adicionar("demo-2")
        self.afastar("demo-1", avisar=False)  # ex.: afastamento registrado com a integração desligada
        self.assertEqual(primeiro_da_fila(atividade=self.atividade, provedor=obter_provedor()), seguinte)
        with self.assertRaisesMessage(ValidationError, "Participante afastado não pode ser atendido"):
            inscrever_participante(usuario=self.usuario, atividade_id=self.atividade.pk, participante_referencia="demo-1",
                                   espera_id=afastado.pk, vaga_confirmada=True)
        with self.assertRaises(ValidationError):
            inscrever_participante(usuario=self.usuario, atividade_id=self.atividade.pk, participante_referencia="demo-3")
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("atividades:lista_espera", args=[self.atividade.pk]))
        self.assertContains(resposta, "Afastado: não pode ser atendido até o retorno")
        self.assertContains(resposta, reverse("atividades:atender_espera", args=[self.atividade.pk, seguinte.pk]))
        self.assertNotContains(resposta, reverse("atividades:atender_espera", args=[self.atividade.pk, afastado.pk]))
        inscrever_participante(usuario=self.usuario, atividade_id=self.atividade.pk, participante_referencia="demo-2",
                               espera_id=seguinte.pk, vaga_confirmada=True)
        seguinte.refresh_from_db()
        self.assertEqual(seguinte.situacao, "inscrito")


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False, NCI_PARTICIPANTES_PROVIDER=PLACEHOLDER)
class AutorizacaoPeloCoreTests(Base):
    def arquivos(self):
        raiz = Path(apps.get_app_config("atividades").path)
        return [caminho for caminho in raiz.rglob("*.py")
                if "tests" not in caminho.relative_to(raiz).parts and "__pycache__" not in caminho.parts]

    def test_atividades_nao_importa_usuarios_nem_copia_autorizar(self):
        violacoes = []
        for caminho in self.arquivos():
            texto = caminho.read_text(encoding="utf-8")
            for no in ast.walk(ast.parse(texto, filename=str(caminho))):
                modulos = []
                if isinstance(no, ast.Import):
                    modulos = [alias.name for alias in no.names]
                elif isinstance(no, ast.ImportFrom) and no.level == 0 and no.module:
                    modulos = [no.module]
                if any(modulo.split(".", 1)[0] == "usuarios" for modulo in modulos):
                    violacoes.append(f"{caminho}:{no.lineno}: import de {modulos}")
                if isinstance(no, ast.FunctionDef) and no.name in ("autorizar", "autorizar_administrador"):
                    violacoes.append(f"{caminho}:{no.lineno}: cópia local de {no.name}")
            if "is_active=True" in texto:
                violacoes.append(f"{caminho}: reconsulta o usuário por conta própria (use core.permissoes)")
        self.assertEqual(violacoes, [], "\n".join(violacoes))

    def test_mensagens_de_cada_ponto_mantidas(self):
        sem_permissao = get_user_model().objects.create_user(username="sem_permissao_ficticia")
        with self.assertRaisesMessage(PermissionDenied, "Você não tem permissão para registrar aulas."):
            registrar_aula(usuario=sem_permissao, atividade_id=self.atividade.pk, data=date(2024, 2, 15),
                           inicio=time(9), fim=time(10))
        with self.assertRaisesMessage(PermissionDenied, "Você não tem permissão para registrar inscrições."):
            inscrever_participante(usuario=sem_permissao, atividade_id=self.atividade.pk, participante_referencia="demo-1")
        inativo = usuario_atividades("inativo_ficticio")
        inativo.is_active = False
        inativo.save(update_fields=["is_active"])
        with self.assertRaises(PermissionDenied):
            registrar_aula(usuario=inativo, atividade_id=self.atividade.pk, data=date(2024, 2, 15),
                           inicio=time(9), fim=time(10))
        with self.assertRaisesMessage(PermissionDenied, "Somente administradores podem ativar ou desativar atividades."):
            alterar_situacao_atividade(usuario=equipe(), atividade_id=self.atividade.pk, ativa=False)
        alterar_situacao_atividade(usuario=administrador(), atividade_id=self.atividade.pk, ativa=False)
        self.atividade.refresh_from_db()
        self.assertFalse(self.atividade.ativa)

    def test_tela_de_situacao_so_para_administrador(self):
        url = reverse("atividades:situacao", args=[self.atividade.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(equipe())
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(administrador())
        resposta = self.client.get(url)
        self.assertContains(resposta, "Situação desejada")
        self.assertEqual(self.client.post(url, {"ativo": "0"}).status_code, 302)
        self.atividade.refresh_from_db()
        self.assertFalse(self.atividade.ativa)
