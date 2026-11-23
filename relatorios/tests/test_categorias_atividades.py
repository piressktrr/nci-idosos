"""RF-FMR-10: aulas realizadas e participações por categoria do FMR (P04). Dados fictícios (RN-SEG-02)."""
from datetime import date, time

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from atividades.models import Atividade, Aula, CategoriaFMR, ClassificacaoAtividade, Frequencia, Inscricao
from relatorios.services import consultar_categorias_atividades_fmr, consultar_indicadores_fmr


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False,
                   NCI_PARTICIPANTES_PROVIDER="participantes.provedor.ProvedorParticipantes")
class CategoriasAtividadesFMRTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="categorias_fmr_ficticio")
        cls.grupo = Group.objects.get(name="Equipe")
        cls.usuario.groups.add(cls.grupo)
        cls.permissoes = Permission.objects.filter(content_type__app_label="atividades",
                                                   codename__in=("view_atividade", "view_aula", "view_frequencia"))
        cls.usuario.user_permissions.add(*cls.permissoes)
        cls.url = reverse("relatorios:fmr")
        cls.danca = CategoriaFMR.objects.create(nome="Categoria fictícia Dança")
        cls.esporte = CategoriaFMR.objects.create(nome="Categoria fictícia Esporte")
        cls.vazia = CategoriaFMR.objects.create(nome="Categoria fictícia Vazia")
        CategoriaFMR.objects.create(nome="Categoria fictícia Inativa", ativa=False)
        cls.oficina = Atividade.objects.create(nome="Oficina fictícia A", monitor="Equipe", local="Sala")
        cls.outra = Atividade.objects.create(nome="Oficina fictícia B", monitor="Equipe", local="Sala")
        ClassificacaoAtividade.objects.create(atividade=cls.oficina, categoria=cls.danca,
                                              categoria_nome=cls.danca.nome, inicio=date(2024, 1, 1))
        ClassificacaoAtividade.objects.create(atividade=cls.outra, categoria=cls.esporte,
                                              categoria_nome=cls.esporte.nome, inicio=date(2024, 1, 1))
        cls.inscricoes = {atividade.pk: [Inscricao.objects.create(
            atividade=atividade, origem_participante="participantes", participante_referencia=f"ref-{atividade.pk}-{n}",
            cadastrada_por=cls.usuario) for n in range(3)] for atividade in (cls.oficina, cls.outra)}

    def setUp(self):
        self.client.force_login(self.usuario)

    def aula(self, atividade, dia, hora=9, presentes=0, ausentes=0, situacao="realizada"):
        # Uma aula por (atividade, data, início): compatível com a restrição de aula realizada única.
        aula = Aula.objects.create(atividade=atividade, data=dia, inicio=time(hora), fim=time(hora + 1),
                                   situacao=situacao)
        inscricoes = self.inscricoes[atividade.pk]
        for indice in range(presentes + ausentes):
            Frequencia.objects.create(aula=aula, inscricao=inscricoes[indice],
                                      situacao="presente" if indice < presentes else "ausente")
        return aula

    def consultar(self, **extras):
        return consultar_categorias_atividades_fmr(**({"usuario": self.usuario, "ano": 2024, "mes": 2} | extras))

    def por_categoria(self, dados):
        """Só as categorias fictícias do teste; as do catálogo semeado pela migration ficam com zero real."""
        linhas = {linha["categoria"]: (linha["aulas"], linha["participacoes"]) for linha in dados["linhas"]}
        outras = {nome: valor for nome, valor in linhas.items() if not nome.startswith("Categoria fictícia")}
        if dados["total_aulas"] is not None:
            self.assertTrue(all(valor == (0, 0) for valor in outras.values()), outras)
        return {nome: valor for nome, valor in linhas.items() if nome.startswith("Categoria fictícia")}

    def test_aulas_e_presencas_por_categoria_com_zero_real_e_sem_canceladas(self):
        self.aula(self.oficina, date(2024, 2, 1), presentes=2, ausentes=1)
        self.aula(self.oficina, date(2024, 2, 1), hora=14, presentes=1)
        self.aula(self.oficina, date(2024, 2, 2), situacao="cancelada")
        self.aula(self.outra, date(2024, 2, 29), presentes=3)
        self.aula(self.outra, date(2024, 3, 1), presentes=3)  # Outro mês.
        dados = self.consultar()
        self.assertEqual(self.por_categoria(dados), {
            "Categoria fictícia Dança": (2, 3), "Categoria fictícia Esporte": (1, 3),
            "Categoria fictícia Vazia": (0, 0)})
        self.assertEqual((dados["total_aulas"], dados["total_participacoes"]), (3, 6))
        self.assertEqual(dados["pendencias"], [])

    def test_categoria_vigente_na_data_de_cada_aula(self):
        ClassificacaoAtividade.objects.create(atividade=self.oficina, categoria=self.esporte,
                                              categoria_nome=self.esporte.nome, inicio=date(2024, 2, 15))
        self.aula(self.oficina, date(2024, 2, 14), presentes=1)
        self.aula(self.oficina, date(2024, 2, 15), presentes=2)
        self.assertEqual(self.por_categoria(self.consultar()), {
            "Categoria fictícia Dança": (1, 1), "Categoria fictícia Esporte": (1, 2),
            "Categoria fictícia Vazia": (0, 0)})

    def test_atividade_sem_categoria_vira_pendencia_e_nao_zero(self):
        sem_categoria = Atividade.objects.create(nome="Oficina fictícia sem categoria", monitor="Equipe", local="Sala")
        self.inscricoes[sem_categoria.pk] = [Inscricao.objects.create(
            atividade=sem_categoria, origem_participante="participantes", participante_referencia="ref-sem",
            cadastrada_por=self.usuario)]
        self.aula(self.oficina, date(2024, 2, 1), presentes=1)
        self.aula(sem_categoria, date(2024, 2, 1), presentes=1)
        dados = self.consultar()
        self.assertEqual(dados["sem_categoria"], {"aulas": 1, "participacoes": 1})
        self.assertTrue(all(linha["aulas"] is None and linha["participacoes"] is None for linha in dados["linhas"]))
        self.assertIsNone(dados["total_aulas"])
        self.assertEqual([p["codigo"] for p in dados["pendencias"]], ["CATEGORIA"])
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Aulas sem categoria vigente: 1")
        self.assertContains(resposta, 'aria-describedby="categorias-pendencia-CATEGORIA"')

    def test_tela_detalhada_e_transcricao_mostram_a_tabela(self):
        self.aula(self.oficina, date(2024, 2, 1), presentes=2)
        for parametros in ({"mes": "2024-02"}, {"mes": "2024-02", "modo": "transcricao"}):
            with self.subTest(parametros=parametros):
                resposta = self.client.get(self.url, parametros)
                self.assertContains(resposta, 'id="tabela-categorias-atividades"')
                self.assertContains(resposta, "<tr><th scope=\"row\">Categoria fictícia Dança</th><td>1</td><td>2</td></tr>",
                                    html=True)
                self.assertNotContains(resposta, "Categoria fictícia Inativa")

    def test_soma_por_categoria_confere_com_indicadores_e_nao_fica_pendente_na_cobertura(self):
        self.aula(self.oficina, date(2024, 2, 1), presentes=2)
        self.aula(self.outra, date(2024, 2, 2), presentes=1)
        with CaptureQueriesContext(connection) as consultas:
            dados = consultar_indicadores_fmr(usuario=self.usuario, ano=2024, mes=2)
        self.assertTrue(all(q["sql"].upper().startswith("SELECT") for q in consultas))
        indicadores = {i["codigo"]: i["valor"] for i in dados["indicadores"]}
        categorias = dados["categorias_atividades"]
        self.assertEqual((categorias["total_aulas"], categorias["total_participacoes"]),
                         (indicadores["aulas_realizadas"], indicadores["participacoes"]))
        self.assertNotIn("Atividades e participações por categoria",
                         [campo["campo"] for campo in dados["campos_indisponiveis"]])
        self.assertEqual([a for a in dados["avisos_consistencia"] if a["secao"] == "categorias-atividades"], [])

    def test_origem_de_demonstracao_nao_conta_como_participacao(self):
        demo = Inscricao.objects.create(atividade=self.oficina, origem_participante="placeholder",
                                        participante_referencia="ref-demo", cadastrada_por=self.usuario)
        aula = self.aula(self.oficina, date(2024, 2, 1), presentes=1)
        Frequencia.objects.create(aula=aula, inscricao=demo, situacao="presente")
        self.assertEqual(self.por_categoria(self.consultar())["Categoria fictícia Dança"], (1, 1))

    def test_sem_permissao_de_frequencia_mostra_aviso_sem_numeros(self):
        self.usuario.user_permissions.remove(*self.permissoes)
        dados = self.consultar()
        self.assertTrue(dados["aviso"])
        self.assertEqual(dados["linhas"], [])
        self.assertNotIn("categorias_atividades", consultar_indicadores_fmr(usuario=self.usuario, ano=2024, mes=2))
