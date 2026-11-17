"""RNF-SEG-11: exportação CSV dos participantes, autorizada e auditada. Dados fictícios (RN-SEG-02)."""

import csv
import io
import json
import tempfile
from datetime import date
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core.perfis import GRUPO_ADMINISTRADOR, GRUPO_EQUIPE
from participantes.exportacao import BOM, CABECALHO, _celula, exportar_participantes_csv
from participantes.models import Participante, RegistroExportacao
from participantes.services import cadastrar_participante, registrar_situacao_social

INDICADORES_FALSOS = {"mora_sozinho": False, "tem_apoio": False, "possui_deficiencia": False, "recebe_bpc": False,
                      "imigrante_refugiado": False}


def _dados(**extra):
    return {"nome_completo": "Ana Ficticia Exportacao", "data_nascimento": date(1948, 6, 1), "sexo": "F",
            "raca_cor": "parda", "identidade_genero": "mulher_cis", "telefone_celular": "61912345678",
            "telefone_residencial": "6131234567", "origem_encaminhamento": "cras", "endereco": "Rua Ficticia, 1",
            "ensino_medio_completo": True, "observacao_encaminhamento": "Encaminhada pelo CRAS ficticio",
            "data_entrada": date(2024, 2, 1), **extra}


def _membro(username, *grupos, **extra):
    usuario = get_user_model().objects.create_user(username=username, **extra)
    usuario.groups.add(*Group.objects.filter(name__in=grupos))
    return usuario


def _ler(texto):
    """(cabeçalho, linhas) de um CSV exportado, conferindo o BOM."""
    assert texto.startswith(BOM), "o CSV deve começar com o BOM do UTF-8"
    linhas = list(csv.reader(io.StringIO(texto[len(BOM):], newline=""), delimiter=";"))
    return linhas[0], linhas[1:]


def _exportar(usuario):
    destino = io.StringIO(newline="")
    quantidade = exportar_participantes_csv(usuario=usuario, destino=destino)
    return quantidade, destino.getvalue()


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = _membro("admin_ficticio", GRUPO_ADMINISTRADOR)
        cls.equipe = _membro("equipe_ficticia", GRUPO_EQUIPE)


class PermissaoTests(Base):
    def test_administrador_recebe_a_permissao_pelo_perfil_e_a_equipe_nao(self):
        self.assertTrue(Permission.objects.filter(content_type__app_label="participantes",
                                                  codename="exportar_participante",
                                                  name="Pode exportar participantes").exists())
        self.assertTrue(Group.objects.get(name=GRUPO_ADMINISTRADOR).permissions
                        .filter(codename="exportar_participante").exists())
        self.assertFalse(Group.objects.get(name=GRUPO_EQUIPE).permissions
                         .filter(codename="exportar_participante").exists())
        self.assertTrue(get_user_model().objects.get(pk=self.admin.pk).has_perm("participantes.exportar_participante"))
        self.assertFalse(get_user_model().objects.get(pk=self.equipe.pk)
                         .has_perm("participantes.exportar_participante"))

    def test_servico_recusa_sem_permissao_inativo_e_anonimo(self):
        from django.contrib.auth.models import AnonymousUser
        inativo = _membro("admin_inativo_ficticio", GRUPO_ADMINISTRADOR, is_active=False)
        for usuario in (self.equipe, inativo, AnonymousUser(), None):
            with self.subTest(usuario=usuario):
                with self.assertRaises(PermissionDenied):
                    _exportar(usuario)
        self.assertFalse(RegistroExportacao.objects.exists())


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class ViewTests(Base):
    url = reverse("participantes:exportar")

    def test_anonimo_vai_para_entrar(self):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(resposta["Location"].startswith("/entrar/"))

    def test_equipe_recebe_403_e_nada_e_auditado(self):
        self.client.force_login(self.equipe)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertFalse(RegistroExportacao.objects.exists())

    def test_inativo_nao_exporta(self):
        self.client.force_login(_membro("inativo_ficticio", GRUPO_ADMINISTRADOR, is_active=False))
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(resposta["Location"].startswith("/entrar/"))
        self.assertFalse(RegistroExportacao.objects.exists())

    def test_administrador_baixa_o_csv_sem_cache(self):
        cadastrar_participante(usuario=self.admin, **_dados())
        self.client.force_login(self.admin)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "text/csv; charset=utf-8")
        self.assertEqual(resposta["Content-Disposition"],
                         f'attachment; filename="participantes_{timezone.localdate():%Y-%m-%d}.csv"')
        self.assertEqual(resposta["Cache-Control"], "no-store")
        self.assertTrue(resposta.content.startswith(b"\xef\xbb\xbf"))
        cabecalho, linhas = _ler(resposta.content.decode("utf-8"))
        self.assertEqual(cabecalho, list(CABECALHO))
        self.assertEqual(len(linhas), 1)
        self.assertEqual(RegistroExportacao.objects.count(), 1)

    def test_post_nao_e_aceito(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_botao_so_aparece_com_a_permissao(self):
        lista = reverse("participantes:lista")
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(lista), f'href="{self.url}"')
        self.client.force_login(self.equipe)
        resposta = self.client.get(lista)
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, "Exportar CSV")
        self.assertNotContains(resposta, self.url)


class ConteudoTests(Base):
    def test_cabecalho_com_rotulos_em_portugues_e_separador_ponto_e_virgula(self):
        _, texto = _exportar(self.admin)
        primeira = texto[len(BOM):].split("\r\n")[0]
        self.assertEqual(primeira.split(";"), list(CABECALHO))
        self.assertEqual(list(CABECALHO), [
            "Código", "Nome completo", "Data de nascimento", "Sexo", "Raça/cor", "Identidade de gênero", "Endereço",
            "Telefone celular", "Telefone residencial", "Origem do encaminhamento",
            "Observação sobre o encaminhamento", "Ensino médio completo", "Status", "Data de entrada",
            "Mora sozinho", "Tem apoio familiar ou comunitário", "Possui deficiência", "Recebe BPC",
            "Imigrante ou refugiado", "Situação social vigente desde"])

    def test_linha_com_rotulos_datas_telefones_e_situacao_vigente(self):
        ana = cadastrar_participante(usuario=self.admin, **_dados())
        registrar_situacao_social(usuario=self.admin, participante_id=ana.pk, vigente_desde=date(2024, 3, 1),
                                  **{**INDICADORES_FALSOS, "mora_sozinho": True, "recebe_bpc": True})
        registrar_situacao_social(usuario=self.admin, participante_id=ana.pk, vigente_desde=date(2025, 6, 10),
                                  **{**INDICADORES_FALSOS, "tem_apoio": True, "recebe_bpc": True})
        quantidade, texto = _exportar(self.admin)
        self.assertEqual(quantidade, 1)
        _, linhas = _ler(texto)
        self.assertEqual(linhas, [[
            str(ana.pk), "Ana Ficticia Exportacao", "01/06/1948", "Feminino", "Parda", "Mulher cisgênero",
            "Rua Ficticia, 1", "(61) 91234-5678", "(61) 3123-4567", "CRAS", "Encaminhada pelo CRAS ficticio",
            "Sim", "Ativo", "01/02/2024", "Não", "Sim", "Não", "Sim", "Não", "10/06/2025"]])

    def test_sem_situacao_social_os_indicadores_ficam_vazios(self):
        cadastrar_participante(usuario=self.admin, **_dados(
            nome_completo="Benedito Ficticio Sem Situacao", sexo="M", identidade_genero="homem_cis",
            raca_cor="nao_informado", telefone_residencial="", ensino_medio_completo=False,
            origem_encaminhamento="rede", observacao_encaminhamento=""))
        _, linhas = _ler(_exportar(self.admin)[1])
        linha = dict(zip(CABECALHO, linhas[0], strict=True))
        self.assertEqual(linha["Sexo"], "Masculino")
        self.assertEqual(linha["Raça/cor"], "Não informado")
        self.assertEqual(linha["Identidade de gênero"], "Homem cisgênero")
        self.assertEqual(linha["Origem do encaminhamento"], "Outro serviço da rede")
        self.assertEqual(linha["Telefone residencial"], "")
        self.assertEqual(linha["Ensino médio completo"], "Não")
        for rotulo in CABECALHO[14:]:
            with self.subTest(coluna=rotulo):
                self.assertEqual(linha[rotulo], "")

    def test_texto_com_ponto_e_virgula_aspas_e_quebra_de_linha_fica_numa_celula(self):
        cadastrar_participante(usuario=self.admin, **_dados(
            endereco='Rua "Ficticia"; casa 2', observacao_encaminhamento="Linha um\nLinha dois; fim"))
        _, linhas = _ler(_exportar(self.admin)[1])
        linha = dict(zip(CABECALHO, linhas[0], strict=True))
        self.assertEqual(linha["Endereço"], 'Rua "Ficticia"; casa 2')
        self.assertEqual(linha["Observação sobre o encaminhamento"], "Linha um\nLinha dois; fim")

    def test_uma_linha_por_participante(self):
        for indice in range(3):
            cadastrar_participante(usuario=self.admin, **_dados(nome_completo=f"Pessoa Ficticia {indice}",
                                                                data_nascimento=date(1950, 1, indice + 1)))
        quantidade, texto = _exportar(self.admin)
        _, linhas = _ler(texto)
        self.assertEqual(quantidade, 3)
        self.assertEqual(sorted(int(linha[0]) for linha in linhas),
                         sorted(Participante.objects.values_list("pk", flat=True)))


class FormulaTests(Base):
    def test_celula_neutraliza_inicio_de_formula(self):
        for valor in ("=1+1", "+55", "-2", "@SOMA(A1)", "\tx", "\rx"):
            with self.subTest(valor=valor):
                self.assertEqual(_celula(valor), "'" + valor)
        for valor in ("Ana", "(61) 91234-5678", "a=b", 12, None):
            with self.subTest(valor=valor):
                self.assertEqual(_celula(valor), "" if valor is None else str(valor))

    def test_campos_do_cadastro_com_formula_saem_com_apostrofo(self):
        cadastrar_participante(usuario=self.admin, **_dados(
            nome_completo='=HIPERLINK("http://exemplo.invalid";"x")', endereco="+55 Rua Ficticia",
            observacao_encaminhamento="@SOMA(1;2)"))
        _, linhas = _ler(_exportar(self.admin)[1])
        linha = dict(zip(CABECALHO, linhas[0], strict=True))
        self.assertEqual(linha["Nome completo"], '\'=HIPERLINK("http://exemplo.invalid";"x")')
        self.assertEqual(linha["Endereço"], "'+55 Rua Ficticia")
        self.assertEqual(linha["Observação sobre o encaminhamento"], "'@SOMA(1;2)")


class ConsultasTests(Base):
    def _consultas(self):
        with CaptureQueriesContext(connection) as contexto:
            _exportar(self.admin)
        return len(contexto.captured_queries)

    def test_numero_de_consultas_nao_depende_da_quantidade(self):
        primeira = cadastrar_participante(usuario=self.admin, **_dados(nome_completo="Pessoa Ficticia 0"))
        registrar_situacao_social(usuario=self.admin, participante_id=primeira.pk, vigente_desde=date(2024, 3, 1),
                                  **INDICADORES_FALSOS)
        com_um = self._consultas()
        for indice in range(1, 6):
            pessoa = cadastrar_participante(usuario=self.admin, **_dados(nome_completo=f"Pessoa Ficticia {indice}",
                                                                         data_nascimento=date(1950, 2, indice)))
            registrar_situacao_social(usuario=self.admin, participante_id=pessoa.pk,
                                      vigente_desde=date(2024, 3, indice), **INDICADORES_FALSOS)
        with self.assertNumQueries(com_um):
            quantidade, _ = _exportar(self.admin)
        self.assertEqual(quantidade, 6)


class AuditoriaTests(Base):
    def test_evento_tem_quantidade_e_formato_sem_dados_pessoais(self):
        ana = cadastrar_participante(usuario=self.admin, **_dados())
        _exportar(self.admin)
        evento = RegistroExportacao.objects.get()
        self.assertEqual(evento.acao, "exportacao")
        self.assertEqual(evento.usuario_id, self.admin.pk)
        self.assertEqual(evento.alvo_id, self.admin.pk)
        self.assertEqual(evento.exportador, self.admin)
        self.assertIsNone(evento.anteriores)
        self.assertEqual(evento.novos, {"quantidade": 1, "formato": "csv"})
        conteudo = json.dumps([evento.novos, evento.anteriores], ensure_ascii=False)
        for dado in (ana.nome_completo, ana.endereco, ana.telefone_celular, "1948"):
            with self.subTest(dado=dado):
                self.assertNotIn(dado, conteudo)

    def test_cada_exportacao_gera_um_evento(self):
        _exportar(self.admin)
        _exportar(self.admin)
        self.assertEqual(list(RegistroExportacao.objects.filter(exportador=self.admin)
                              .values_list("novos", flat=True)),
                         [{"quantidade": 0, "formato": "csv"}] * 2)


class ComandoTests(Base):
    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp())
        self.addCleanup(self._limpar)
        self.saida = self.pasta / "participantes.csv"

    def _limpar(self):
        for arquivo in self.pasta.iterdir():
            arquivo.unlink()
        self.pasta.rmdir()

    def _rodar(self, *argumentos, usuario="admin_ficticio"):
        saida = io.StringIO()
        call_command("exportar_participantes", "--usuario", usuario, "--saida", str(self.saida), *argumentos,
                     stdout=saida)
        return saida.getvalue()

    def test_gera_o_arquivo_e_audita(self):
        cadastrar_participante(usuario=self.admin, **_dados())
        mensagem = self._rodar()
        self.assertIn("1 participante(s) exportado(s)", mensagem)
        self.assertIn("dados pessoais sensíveis", mensagem)
        bruto = self.saida.read_bytes()
        self.assertTrue(bruto.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"\r\n", bruto)
        self.assertNotIn(b"\r\r\n", bruto)
        cabecalho, linhas = _ler(bruto.decode("utf-8"))
        self.assertEqual(cabecalho, list(CABECALHO))
        self.assertEqual(linhas[0][1], "Ana Ficticia Exportacao")
        self.assertEqual(RegistroExportacao.objects.get().novos, {"quantidade": 1, "formato": "csv"})

    def test_recusa_sobrescrever_sem_a_opcao(self):
        self.saida.write_text("conteudo anterior", encoding="utf-8")
        with self.assertRaisesMessage(CommandError, "--sobrescrever"):
            self._rodar()
        self.assertEqual(self.saida.read_text(encoding="utf-8"), "conteudo anterior")
        self.assertFalse(RegistroExportacao.objects.exists())

    def test_sobrescreve_com_a_opcao(self):
        self.saida.write_text("conteudo anterior " * 100, encoding="utf-8")
        self._rodar("--sobrescrever")
        cabecalho, linhas = _ler(self.saida.read_bytes().decode("utf-8"))
        self.assertEqual(cabecalho, list(CABECALHO))
        self.assertEqual(linhas, [])
        self.assertEqual(RegistroExportacao.objects.count(), 1)

    def test_usuario_sem_permissao_ou_inexistente_nao_gera_arquivo(self):
        _membro("inativo_cmd_ficticio", GRUPO_ADMINISTRADOR, is_active=False)
        for usuario in ("equipe_ficticia", "inativo_cmd_ficticio", "nao_existe_ficticio"):
            with self.subTest(usuario=usuario):
                with self.assertRaises(CommandError):
                    self._rodar(usuario=usuario)
                self.assertFalse(self.saida.exists())
        self.assertFalse(RegistroExportacao.objects.exists())
