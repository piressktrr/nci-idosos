#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NCI Idade Dourada de Pinheiros - simulação em console (prova de conceito).

Objetivo: mostrar o "corpo" do sistema (cadastro, atividades, frequência e
indicadores do FMR) SEM interface web, SEM login e SEM Django.
Só usa a biblioteca padrão do Python (3.8+). Os dados ficam em nci_dados.json.

REGRAS DE NEGÓCIO IMPORTANTES (ver comentários marcados com [PENDENTE]):
- A frequência é digitada pela equipe do NCI a partir das listas de papel.
- Nada é apagado: idoso é desligado (com motivo) e pode ser reativado.
- Dados que mudam com o tempo (mora sozinho, BPC...) têm data de vigência.
- Faltam definições do NCI/SMADS: elas estão isoladas em constantes/funções
  para serem trocadas facilmente quando forem confirmadas.

Para testar rápido: opção 11 do menu carrega dados FICTÍCIOS de setembro/2026.
Use sempre dados fictícios em demonstrações e testes (LGPD).
"""
import calendar
import copy
import json
import os
import random
import sys
from datetime import date, datetime, timedelta

ARQUIVO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nci_dados.json")

# ----------------------------------------------------------------------------
# Listas fixas (vêm do formulário FMR) e configurações pendentes
# ----------------------------------------------------------------------------
SEXOS = ["F", "M"]
RACAS = ["Branca", "Preta", "Parda", "Amarela", "Indígena", "Não informada"]
GENEROS = ["Cisgênero", "Transgênero", "Agênero", "Não declarado"]
REGIOES = ["Subprefeitura do serviço", "Outra subprefeitura", "Outro município"]
MOTIVOS_SAIDA = ["Mudança de endereço", "Oferta do serviço em domicílio",
                 "Transferência para outro serviço", "Óbito", "Desistência",
                 "Excesso de faltas"]
# As 3 primeiras são as do FMR ("ingressaram encaminhados por"). As demais são nossas.
ORIGENS = ["CRAS", "CREAS", "Outros serviços da rede socioassistencial",
           "Demanda espontânea / outra", "Retorno (reativação)"]
ORIGENS_FMR = ORIGENS[:3]
CATEGORIAS_FMR = [
    "Ações em campanhas comunitárias", "Artesanato", "Atividades de arte e cultura",
    "Atividades de estimulação cognitiva", "Atividades de inclusão digital",
    "Atividades de linguagem", "Atividades esportivas", "Atividades externas",
    "Atividades que envolvam manipulação de alimentos", "Atividades recreativas",
    "Atividades sobre sustentabilidade ambiental", "Musicalidade",
]
JUSTIFICATIVAS_INICIAIS = ["Consulta médica", "Viagem", "Problemas familiares"]
FAIXAS = [("60 a 64", 60, 64), ("65 a 69", 65, 69), ("70 a 74", 70, 74), ("75 ou mais", 75, 200)]
FAIXA_FORA = "Menor de 60 (verificar cadastro)"
DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]

# Regra de "pessoas por dia" no FMR, conforme a prática atual do NCI: contar OCORRÊNCIAS
# (cada presença em cada aula). Para contar pessoas distintas por dia, troque por "distintas".
CONTAGEM_PESSOAS_POR_DIA = "ocorrencias"

# [A CONFIRMAR] Em qual faixa etária contar quem faz aniversário durante o mês e muda de faixa
# (ex.: 64 -> 65)? Hoje: idade no último dia do mês.
def data_referencia_idade(ini_mes, fim_mes):
    return fim_mes

# ----------------------------------------------------------------------------
# Datas e entrada de dados
# ----------------------------------------------------------------------------
def fmt(d):
    return d.strftime("%d/%m/%Y") if d else "-"

def D(s):
    """texto ISO -> date (ou None)"""
    return date.fromisoformat(s) if s else None

def iso(d):
    return d.isoformat() if d else None

def idade_em(nasc, ref):
    return ref.year - nasc.year - ((ref.month, ref.day) < (nasc.month, nasc.day))

def faixa_de(idade):
    for nome, lo, hi in FAIXAS:
        if lo <= idade <= hi:
            return nome
    return FAIXA_FORA

def pergunta(txt, obrigatorio=True, padrao=None):
    while True:
        sufixo = f" [{padrao}]" if padrao not in (None, "") else ""
        r = input(f"{txt}{sufixo}: ").strip()
        if not r and padrao is not None:
            return str(padrao)
        if r or not obrigatorio:
            return r
        print("  (campo obrigatório)")

def pergunta_data(txt, obrigatorio=True, padrao=None):
    while True:
        p = fmt(padrao) if padrao else None
        r = pergunta(f"{txt} (DD/MM/AAAA)", obrigatorio, p)
        if not r:
            return None
        try:
            return datetime.strptime(r, "%d/%m/%Y").date()
        except ValueError:
            print("  Data inválida. Exemplo: 25/09/2026")

def sim_nao(txt, padrao=None):
    dica = {True: "S/n", False: "s/N", None: "s/n"}[padrao]
    while True:
        r = input(f"{txt} ({dica}): ").strip().lower()
        if not r and padrao is not None:
            return padrao
        if r in ("s", "sim"):
            return True
        if r in ("n", "nao", "não"):
            return False
        print("  Responda s ou n.")

def escolher(txt, opcoes, permitir_vazio=False):
    print(txt)
    for n, o in enumerate(opcoes, 1):
        print(f"  {n}) {o}")
    while True:
        r = input("  Número: ").strip()
        if not r and permitir_vazio:
            return None
        if r.isdigit() and 1 <= int(r) <= len(opcoes):
            return opcoes[int(r) - 1]
        print("  Opção inválida.")

def pergunta_mes(txt, padrao):
    while True:
        r = pergunta(f"{txt} (MM/AAAA)", True, padrao)
        try:
            m, a = r.split("/")
            m, a = int(m), int(a)
            if 1 <= m <= 12:
                return a, m
        except ValueError:
            pass
        print("  Formato inválido. Exemplo: 09/2026")

def limites_mes(ano, mes):
    ini = date(ano, mes, 1)
    fim = date(ano, mes, calendar.monthrange(ano, mes)[1])
    return ini, fim, ini - timedelta(days=1)

def mes_anterior_padrao():
    h = date.today().replace(day=1) - timedelta(days=1)
    return f"{h.month:02d}/{h.year}"

# ----------------------------------------------------------------------------
# Banco de dados (JSON). Estrutura espelha o futuro modelo relacional.
# ----------------------------------------------------------------------------
def novo_banco():
    return {"prox_id": 1, "idosos": [], "atividades": [], "inscricoes": [],
            "ocorrencias": [], "justificativas": list(JUSTIFICATIVAS_INICIAIS), "log": []}

def carregar():
    if os.path.exists(ARQUIVO):
        with open(ARQUIVO, encoding="utf-8") as f:
            return json.load(f)
    return novo_banco()

def salvar(db):
    with open(ARQUIVO, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=1)

def novo_id(db):
    i = db["prox_id"]
    db["prox_id"] += 1
    return i

def registrar_log(db, acao, detalhe):
    # [PENDENTE] sem login ainda: na versão web, guardar também o usuário.
    db["log"].append({"quando": datetime.now().isoformat(timespec="seconds"),
                      "acao": acao, "detalhe": detalhe})

def tabela(cabecalho, linhas):
    linhas = [[str(c) for c in l] for l in linhas]
    larg = [max(len(str(h)), *(len(l[i]) for l in linhas)) if linhas else len(str(h))
            for i, h in enumerate(cabecalho)]
    fmt_l = "  " + " | ".join("{:<%d}" % w for w in larg)
    print(fmt_l.format(*cabecalho))
    print("  " + "-+-".join("-" * w for w in larg))
    for l in linhas:
        print(fmt_l.format(*l))

def titulo(t):
    print("\n" + "=" * 72 + f"\n{t}\n" + "=" * 72)

def subtitulo(t):
    print(f"\n--- {t} ---")

# ----------------------------------------------------------------------------
# Regras de domínio
# ----------------------------------------------------------------------------
def ativo_em(idoso, d):
    """Está no serviço na data d? data_saida é o 1º dia FORA do serviço."""
    for p in idoso["periodos"]:
        e, s = D(p["entrada"]), D(p["saida"])
        if e <= d and (s is None or s > d):
            return True
    return False

def situacao_em(idoso, d):
    """Situação vigente (mora sozinho, BPC...) na data d."""
    c = [s for s in idoso["situacoes"] if D(s["inicio"]) <= d]
    return max(c, key=lambda s: s["inicio"]) if c else None

def inscricao_ativa_em(insc, d):
    e, s = D(insc["entrada"]), D(insc["saida"])
    return e <= d and (s is None or s > d)

def inscritos_na_data(db, atividade_id, d):
    ids = {i["idoso_id"] for i in db["inscricoes"]
           if i["atividade_id"] == atividade_id and inscricao_ativa_em(i, d)}
    res = [x for x in db["idosos"] if x["id"] in ids and ativo_em(x, d)]
    return sorted(res, key=lambda x: x["nome"].casefold())

def achar_ocorrencia(db, atividade_id, d, hora):
    """Uma aula é identificada por atividade + data + horário de início."""
    for o in db["ocorrencias"]:
        if (o["atividade_id"] == atividade_id and o["data"] == iso(d)
                and (o.get("hora_inicio") or "") == (hora or "")):
            return o
    return None

def por_id(lista, i):
    return next((x for x in lista if x["id"] == i), None)

def escolher_idoso(db, so_ativos=None, texto="Buscar idoso pelo nome (parte do nome)"):
    hoje = date.today()
    while True:
        busca = pergunta(texto, obrigatorio=False)
        if not busca:
            return None
        achados = [i for i in db["idosos"] if busca.casefold() in i["nome"].casefold()]
        if so_ativos is True:
            achados = [i for i in achados if ativo_em(i, hoje)]
        if so_ativos is False:
            achados = [i for i in achados if not ativo_em(i, hoje)]
        if not achados:
            print("  Nenhum resultado.")
            continue
        achados.sort(key=lambda i: i["nome"].casefold())
        opcoes = [f"{i['nome']} (nasc. {fmt(D(i['data_nascimento']))}, id {i['id']})" for i in achados]
        esc = escolher("Selecione:", opcoes, permitir_vazio=True)
        if esc:
            return achados[opcoes.index(esc)]

def escolher_atividade(db, so_ativas=True):
    ats = [a for a in db["atividades"] if a["ativa"] or not so_ativas]
    if not ats:
        print("  Nenhuma atividade cadastrada.")
        return None
    ats.sort(key=lambda a: a["nome"].casefold())
    opcoes = [f"{a['nome']} ({a['categoria']})" for a in ats]
    esc = escolher("Atividade:", opcoes, permitir_vazio=True)
    return ats[opcoes.index(esc)] if esc else None

def escolher_justificativa(db):
    opcoes = db["justificativas"] + ["(adicionar novo motivo à lista)"]
    esc = escolher("Motivo da justificativa:", opcoes)
    if esc == opcoes[-1]:
        novo = pergunta("Novo motivo")
        if novo not in db["justificativas"]:
            db["justificativas"].append(novo)
        return novo
    return esc

# ----------------------------------------------------------------------------
# Idosos
# ----------------------------------------------------------------------------
def ler_situacao(padrao=None):
    padrao = padrao or {}
    s = {}
    s["mora_sozinho"] = sim_nao("Mora sozinho(a)?", padrao.get("mora_sozinho"))
    s["apoio"] = sim_nao("Conta com apoio da família/comunidade?", padrao.get("apoio")) if s["mora_sozinho"] else None
    s["deficiencia"] = sim_nao("Pessoa com deficiência?", padrao.get("deficiencia"))
    s["bpc"] = sim_nao("Recebe BPC?", padrao.get("bpc"))
    s["regiao"] = escolher("Região de moradia:", REGIOES)
    return s

def cadastrar_idoso(db):
    titulo("CADASTRAR IDOSO")
    nome = pergunta("Nome completo")
    nasc = pergunta_data("Data de nascimento")
    dup = [i for i in db["idosos"] if i["nome"].casefold() == nome.casefold()
           and i["data_nascimento"] == iso(nasc)]
    if dup:
        print("  ATENÇÃO: já existe cadastro com mesmo nome e nascimento.")
        print("  Se a pessoa está voltando, use 'Reativar idoso' em vez de cadastrar de novo.")
        if not sim_nao("Cadastrar mesmo assim?", False):
            return
    sexo = escolher("Sexo:", SEXOS)
    raca = escolher("Raça/cor (autodeclarada):", RACAS)
    genero = escolher("Identidade de gênero (autodeclarada):", GENEROS)
    imigrante = sim_nao("Imigrante/refugiado?", False)
    contato = pergunta("Contato principal (opcional)", obrigatorio=False)
    entrada = pergunta_data("Data de entrada no serviço", padrao=date.today())
    origem = escolher("Como chegou ao serviço (encaminhado por):", ORIGENS)
    print("Situação atual (fica registrada com data de vigência):")
    sit = ler_situacao()
    sit["inicio"] = iso(entrada)
    idoso = {"id": novo_id(db), "nome": nome, "data_nascimento": iso(nasc), "sexo": sexo,
             "raca_cor": raca, "identidade_genero": genero, "imigrante": imigrante,
             "contato": contato,
             "periodos": [{"entrada": iso(entrada), "origem": origem, "saida": None, "motivo_saida": None}],
             "situacoes": [sit]}
    db["idosos"].append(idoso)
    registrar_log(db, "idoso_cadastrado", f"id {idoso['id']} {nome}")
    salvar(db)
    print(f"  Cadastrado (id {idoso['id']}).")

def status_atual(idoso):
    return "Ativo" if ativo_em(idoso, date.today()) else "Desligado"

def listar_idosos(db):
    titulo("IDOSOS")
    busca = pergunta("Filtrar por nome (Enter = todos)", obrigatorio=False)
    lista = [i for i in db["idosos"] if busca.casefold() in i["nome"].casefold()]
    lista.sort(key=lambda i: i["nome"].casefold())
    hoje = date.today()
    tabela(["id", "nome", "idade", "sexo", "situação hoje"],
           [[i["id"], i["nome"], idade_em(D(i["data_nascimento"]), hoje), i["sexo"], status_atual(i)] for i in lista])
    print(f"  {len(lista)} registro(s).")
    if lista and sim_nao("Ver ficha completa de alguém?", False):
        i = escolher_idoso(db)
        if i:
            ficha_idoso(db, i)

def ficha_idoso(db, i):
    titulo(f"FICHA: {i['nome']}")
    hoje = date.today()
    print(f"  Nascimento: {fmt(D(i['data_nascimento']))} ({idade_em(D(i['data_nascimento']), hoje)} anos)  Sexo: {i['sexo']}")
    print(f"  Raça/cor: {i['raca_cor']}  Gênero: {i['identidade_genero']}  Imigrante/refugiado: {'sim' if i['imigrante'] else 'não'}")
    print(f"  Contato: {i['contato'] or '-'}  Situação hoje: {status_atual(i)}")
    subtitulo("Períodos no serviço")
    tabela(["entrada", "origem", "saída", "motivo"],
           [[fmt(D(p["entrada"])), p["origem"], fmt(D(p["saida"])), p["motivo_saida"] or "-"] for p in i["periodos"]])
    subtitulo("Histórico de situação")
    tabela(["vigente desde", "mora só", "apoio", "deficiência", "BPC", "região"],
           [[fmt(D(s["inicio"])), s["mora_sozinho"], s["apoio"], s["deficiencia"], s["bpc"], s["regiao"]]
            for s in sorted(i["situacoes"], key=lambda s: s["inicio"])])
    subtitulo("Inscrições")
    insc = [x for x in db["inscricoes"] if x["idoso_id"] == i["id"]]
    tabela(["atividade", "entrada", "saída"],
           [[por_id(db["atividades"], x["atividade_id"])["nome"], fmt(D(x["entrada"])), fmt(D(x["saida"]))] for x in insc])
    subtitulo("Frequência por atividade (todo o histórico)")
    cont = {}
    for o in db["ocorrencias"]:
        st = o["presencas"].get(str(i["id"]))
        if st:
            a = por_id(db["atividades"], o["atividade_id"])["nome"]
            cont.setdefault(a, {"P": 0, "A": 0, "J": 0})[st] += 1
    tabela(["atividade", "presenças", "faltas", "justificadas"],
           [[a, c["P"], c["A"], c["J"]] for a, c in sorted(cont.items())])

def editar_situacao(db):
    titulo("ATUALIZAR SITUAÇÃO (mora sozinho, BPC, deficiência, região)")
    i = escolher_idoso(db, so_ativos=True)
    if not i:
        return
    vig = pergunta_data("A partir de que data vale a nova situação", padrao=date.today())
    atual = situacao_em(i, vig) or {}
    print("Enter mantém o valor atual.")
    nova = ler_situacao(atual)
    nova["inicio"] = iso(vig)
    i["situacoes"] = [s for s in i["situacoes"] if s["inicio"] != nova["inicio"]]
    i["situacoes"].append(nova)  # o histórico anterior é preservado
    registrar_log(db, "situacao_atualizada", f"id {i['id']} a partir de {iso(vig)}")
    salvar(db)
    print("  Situação registrada (histórico anterior preservado).")

def desligar_idoso(db):
    titulo("DESLIGAR IDOSO (não apaga nada)")
    print("  Obs.: o sistema NÃO desliga ninguém automaticamente por faltas.")
    i = escolher_idoso(db, so_ativos=True)
    if not i:
        return
    saida = pergunta_data("Data de saída (1º dia fora do serviço)", padrao=date.today())
    motivo = escolher("Motivo (opções do FMR):", MOTIVOS_SAIDA)
    aberto = next(p for p in i["periodos"] if p["saida"] is None)
    if saida <= D(aberto["entrada"]):
        print("  A saída deve ser depois da entrada.")
        return
    aberto["saida"], aberto["motivo_saida"] = iso(saida), motivo
    for x in db["inscricoes"]:  # encerra inscrições abertas
        if x["idoso_id"] == i["id"] and x["saida"] is None:
            x["saida"] = iso(saida)
    registrar_log(db, "idoso_desligado", f"id {i['id']} {motivo} em {iso(saida)}")
    salvar(db)
    print("  Desligamento registrado. Inscrições abertas foram encerradas.")

def reativar_idoso(db):
    titulo("REATIVAR IDOSO")
    i = escolher_idoso(db, so_ativos=False)
    if not i:
        return
    entrada = pergunta_data("Data de retorno", padrao=date.today())
    ultimo = max(i["periodos"], key=lambda p: p["entrada"])
    if ultimo["saida"] and entrada < D(ultimo["saida"]):
        print("  A data de retorno deve ser posterior à última saída.")
        return
    i["periodos"].append({"entrada": iso(entrada), "origem": "Retorno (reativação)", "saida": None, "motivo_saida": None})
    if sim_nao("Atualizar a situação (mora sozinho, BPC...)?", True):
        sit = ler_situacao(situacao_em(i, entrada) or {})
        sit["inicio"] = iso(entrada)
        i["situacoes"].append(sit)
    registrar_log(db, "idoso_reativado", f"id {i['id']} em {iso(entrada)}")
    salvar(db)
    print("  Reativado. [PENDENTE] confirmar com o NCI se o retorno conta como 'entrou no mês' no FMR.")

# ----------------------------------------------------------------------------
# Atividades e inscrições
# ----------------------------------------------------------------------------
def cadastrar_atividade(db):
    titulo("CADASTRAR ATIVIDADE")
    nome = pergunta("Nome da atividade")
    local = pergunta("Local", obrigatorio=False)
    monitor = pergunta("Monitor/oficineiro", obrigatorio=False)
    categoria = escolher("Categoria do FMR:", CATEGORIAS_FMR)
    tipo = escolher("Tipo:", ["Aula regular", "Evento / ação pontual"])
    horarios = []
    while sim_nao("Adicionar dia/horário previsto?", len(horarios) == 0 and tipo == "Aula regular"):
        dia = escolher("Dia da semana:", DIAS)
        ini = pergunta("Hora de início (ex.: 09:00)")
        fim = pergunta("Hora de fim (ex.: 10:00)")
        horarios.append({"dia": DIAS.index(dia), "inicio": ini, "fim": fim})
    db["atividades"].append({"id": novo_id(db), "nome": nome, "local": local, "monitor": monitor,
                             "categoria": categoria, "tipo": tipo, "ativa": True, "horarios": horarios})
    registrar_log(db, "atividade_cadastrada", nome)
    salvar(db)
    print("  Atividade cadastrada.")

def listar_atividades(db):
    titulo("ATIVIDADES")
    linhas = []
    for a in sorted(db["atividades"], key=lambda a: a["nome"].casefold()):
        hor = ", ".join(f"{DIAS[h['dia']][:3]} {h['inicio']}-{h['fim']}" for h in a["horarios"]) or "-"
        n = sum(1 for x in db["inscricoes"] if x["atividade_id"] == a["id"] and inscricao_ativa_em(x, date.today()))
        linhas.append([a["id"], a["nome"], a["categoria"], a["local"] or "-", a["monitor"] or "-", hor, n])
    tabela(["id", "atividade", "categoria FMR", "local", "monitor", "horários", "inscritos hoje"], linhas)

def inscrever(db):
    titulo("INSCREVER IDOSO EM ATIVIDADE")
    i = escolher_idoso(db, so_ativos=True)
    if not i:
        return
    a = escolher_atividade(db)
    if not a:
        return
    ent = pergunta_data("Data de entrada na atividade", padrao=date.today())
    if any(x["idoso_id"] == i["id"] and x["atividade_id"] == a["id"] and inscricao_ativa_em(x, ent)
           for x in db["inscricoes"]):
        print("  Já está inscrito(a) nessa atividade.")
        return
    db["inscricoes"].append({"id": novo_id(db), "idoso_id": i["id"], "atividade_id": a["id"],
                             "entrada": iso(ent), "saida": None})
    registrar_log(db, "inscricao", f"idoso {i['id']} em {a['nome']}")
    salvar(db)
    print("  Inscrição registrada.")

def encerrar_inscricao(db):
    titulo("ENCERRAR INSCRIÇÃO")
    i = escolher_idoso(db)
    if not i:
        return
    abertas = [x for x in db["inscricoes"] if x["idoso_id"] == i["id"] and x["saida"] is None]
    if not abertas:
        print("  Sem inscrições abertas.")
        return
    nomes = [por_id(db["atividades"], x["atividade_id"])["nome"] for x in abertas]
    esc = escolher("Qual inscrição encerrar?", nomes)
    x = abertas[nomes.index(esc)]
    x["saida"] = iso(pergunta_data("Data de saída da atividade (1º dia fora)", padrao=date.today()))
    registrar_log(db, "inscricao_encerrada", f"idoso {i['id']} de {esc}")
    salvar(db)
    print("  Inscrição encerrada (o histórico de presenças é mantido).")

# ----------------------------------------------------------------------------
# Frequência
# ----------------------------------------------------------------------------
def resumo_presencas(oc):
    c = {"P": 0, "A": 0, "J": 0}
    for v in oc["presencas"].values():
        c[v] += 1
    return f"{c['P']}P/{c['A']}A/{c['J']}J" if oc["situacao"] == "realizada" else "cancelada"

def registrar_frequencia(db):
    titulo("REGISTRAR FREQUÊNCIA DA AULA (a partir da lista de papel)")
    a = escolher_atividade(db)
    if not a:
        return
    d = pergunta_data("Data da aula (qualquer data; pode ser fora da grade)", padrao=date.today())
    if d > date.today() and not sim_nao("  A data está no futuro. Registrar mesmo assim?", False):
        return
    grade_dia = [h for h in a["horarios"] if h["dia"] == d.weekday()]
    while True:
        hora = pergunta("Horário de início (HH:MM, opcional)", obrigatorio=False,
                        padrao=grade_dia[0]["inicio"] if grade_dia else None)
        try:
            if hora:
                datetime.strptime(hora, "%H:%M")
            break
        except ValueError:
            print("  Formato inválido. Exemplo: 09:00")
    antigo = achar_ocorrencia(db, a["id"], d, hora)
    if antigo:
        print(f"  Já existe registro desta aula ({resumo_presencas(antigo)}).")
        if not sim_nao("Corrigir o registro existente?", False):
            return
    extra, motivo_extra = False, None
    if a["horarios"] and not any(h["dia"] == d.weekday() and h["inicio"] == hora for h in a["horarios"]):
        grade = ", ".join(f"{DIAS[h['dia']][:3]} {h['inicio']}" for h in a["horarios"])
        print(f"  Esta aula está FORA DA GRADE de {a['nome']} ({grade}).")
        if not sim_nao("Registrar como aula extra/remarcada?", True):
            return
        extra = True
        motivo_extra = pergunta("Motivo (aula extra, reposição, horário alterado...)")
    nova = {"id": antigo["id"] if antigo else novo_id(db), "atividade_id": a["id"], "data": iso(d),
            "hora_inicio": hora, "extra": extra, "motivo_extra": motivo_extra,
            "situacao": "realizada", "motivo_cancelamento": None, "presencas": {}, "justificativas": {}}
    if not sim_nao("A aula aconteceu?", True):
        nova["situacao"] = "cancelada"
        nova["motivo_cancelamento"] = pergunta("Motivo (feriado, monitor ausente...)")
    else:
        inscritos = inscritos_na_data(db, a["id"], d)
        if not inscritos:
            print("  Não há inscritos ativos nessa data. Inscreva os idosos primeiro.")
            return
        print("\n  Inscritos nesta data:")
        for n, i in enumerate(inscritos, 1):
            print(f"   {n:>2}) {i['nome']}")
        print("  Todos começam como PRESENTES. Informe os AUSENTES conforme a lista assinada.")
        txt = pergunta("Números dos ausentes separados por vírgula (Enter = ninguém faltou)", obrigatorio=False)
        ausentes = set()
        for t in txt.replace(" ", "").split(","):
            if t.isdigit() and 1 <= int(t) <= len(inscritos):
                ausentes.add(int(t))
            elif t:
                print(f"  (ignorado: '{t}')")
        for n, i in enumerate(inscritos, 1):
            k = str(i["id"])
            if n not in ausentes:
                nova["presencas"][k] = "P"
                continue
            if sim_nao(f"  {i['nome']}: falta JUSTIFICADA?", False):
                nova["presencas"][k] = "J"
                nova["justificativas"][k] = {"motivo": escolher_justificativa(db),
                                             "obs": pergunta("  Observação (opcional)", obrigatorio=False)}
            else:
                nova["presencas"][k] = "A"
    if antigo:
        db["ocorrencias"].remove(antigo)
        registrar_log(db, "frequencia_corrigida",
                      f"{a['nome']} {iso(d)} {hora} antes: {json.dumps(antigo, ensure_ascii=False)}")
    else:
        registrar_log(db, "frequencia_registrada",
                      f"{a['nome']} {iso(d)} {hora} {resumo_presencas(nova)}" + (f" EXTRA: {motivo_extra}" if extra else ""))
    db["ocorrencias"].append(nova)
    salvar(db)
    print(f"  Salvo: {a['nome']} em {fmt(d)} {hora} -> {resumo_presencas(nova)}"
          + ("  [FORA DA GRADE]" if extra else ""))

def frequencia_mensal(db):
    titulo("FREQUÊNCIA MENSAL")
    modo = escolher("Visualização:", ["Por atividade (grade de dias)", "Geral (todas as atividades)"])
    ano, mes = pergunta_mes("Mês", mes_anterior_padrao())
    ini, fim, _ = limites_mes(ano, mes)
    no_mes = [o for o in db["ocorrencias"] if ini <= D(o["data"]) <= fim]
    if modo.startswith("Por"):
        a = escolher_atividade(db, so_ativas=False)
        if not a:
            return
        ocs = sorted([o for o in no_mes if o["atividade_id"] == a["id"] and o["situacao"] == "realizada"],
                     key=lambda o: o["data"])
        canc = [o for o in no_mes if o["atividade_id"] == a["id"] and o["situacao"] == "cancelada"]
        ids = set()
        for o in ocs:
            ids |= {int(k) for k in o["presencas"]}
        if not ocs:
            print("  Nenhuma aula realizada registrada nesse mês.")
            return
        linhas = []
        for i in sorted((x for x in db["idosos"] if x["id"] in ids), key=lambda x: x["nome"].casefold()):
            marc = [o["presencas"].get(str(i["id"]), ".") for o in ocs]
            linhas.append([i["nome"]] + marc + [marc.count("P"), marc.count("A"), marc.count("J")])
        print(f"  {a['nome']} - {mes:02d}/{ano}   (P=presente  A=falta  J=justificada  .=sem registro/não inscrito  *=fora da grade)")
        tabela(["nome"] + [D(o["data"]).strftime("%d") + ("*" if o.get("extra") else "") for o in ocs]
               + ["P", "A", "J"], linhas)
        print(f"  Aulas realizadas: {len(ocs)}   Aulas canceladas: {len(canc)}")
    else:
        resumo = {}
        for o in no_mes:
            if o["situacao"] != "realizada":
                continue
            for k, st in o["presencas"].items():
                r = resumo.setdefault(int(k), {"P": 0, "A": 0, "J": 0, "dias": set()})
                r[st] += 1
                if st == "P":
                    r["dias"].add(o["data"])
        linhas = []
        for i in sorted((x for x in db["idosos"] if x["id"] in resumo), key=lambda x: x["nome"].casefold()):
            r = resumo[i["id"]]
            linhas.append([i["nome"], r["P"], r["A"], r["J"], len(r["dias"])])
        print(f"  Geral - {mes:02d}/{ano}")
        tabela(["nome", "presenças", "faltas", "justificadas", "dias distintos presente"], linhas)

# ----------------------------------------------------------------------------
# FMR - serviço de convivência
# ----------------------------------------------------------------------------
def imprimir_faixa_sexo(rotulo, lista, ref):
    c = {}
    for i in lista:
        k = (faixa_de(idade_em(D(i["data_nascimento"]), ref)), i["sexo"])
        c[k] = c.get(k, 0) + 1
    linhas, tm, tf = [], 0, 0
    for f in [x[0] for x in FAIXAS] + [FAIXA_FORA]:
        m, fe = c.get((f, "M"), 0), c.get((f, "F"), 0)
        if f == FAIXA_FORA and m + fe == 0:
            continue
        linhas.append([f, m, fe, m + fe])
        tm += m
        tf += fe
    linhas.append(["TOTAL", tm, tf, tm + tf])
    print(f"  {rotulo}")
    tabela(["faixa etária", "Masculino", "Feminino", "Total"], linhas)

def contar(lista, campo):
    c = {}
    for i in lista:
        c[campo(i)] = c.get(campo(i), 0) + 1
    return c

def check(ok, msg):
    print(f"  [{'OK' if ok else 'DIVERGENTE'}] {msg}")

def relatorio_fmr(db):
    titulo("FMR NCI - SERVIÇO DE CONVIVÊNCIA (indicadores calculados)")
    ano, mes = pergunta_mes("Mês de referência", mes_anterior_padrao())
    ini, fim, ant = limites_mes(ano, mes)
    ref = data_referencia_idade(ini, fim)
    print(f"  Período: {fmt(ini)} a {fmt(fim)}. Idade calculada em {fmt(ref)}  [PENDENTE: data de referência]")

    idosos = db["idosos"]
    vieram = [i for i in idosos if ativo_em(i, ant)]
    permanecem = [i for i in idosos if ativo_em(i, fim)]
    entradas = [(i, p) for i in idosos for p in i["periodos"] if ini <= D(p["entrada"]) <= fim]
    saidas = [(i, p) for i in idosos for p in i["periodos"] if p["saida"] and ini <= D(p["saida"]) <= fim]

    # 1. Pessoas por dia
    subtitulo("1. Pessoas que frequentaram o serviço por dia")
    ocs = [o for o in db["ocorrencias"] if o["situacao"] == "realizada" and ini <= D(o["data"]) <= fim]
    por_dia = {}
    for o in ocs:
        pres = {int(k) for k, v in o["presencas"].items() if v == "P"}
        d = por_dia.setdefault(o["data"], {"distintas": set(), "presencas": 0})
        d["distintas"] |= pres
        d["presencas"] += len(pres)
    usa_oc = CONTAGEM_PESSOAS_POR_DIA == "ocorrencias"
    def v_fmr(v):
        return v["presencas"] if usa_oc else len(v["distintas"])
    def v_info(v):
        return len(v["distintas"]) if usa_oc else v["presencas"]
    rot_fmr = "presenças (ocorrências)" if usa_oc else "pessoas distintas"
    rot_info = "pessoas distintas" if usa_oc else "presenças (ocorrências)"
    if por_dia:
        tabela(["dia", f"{rot_fmr} = valor do FMR", f"{rot_info} (informativo)"],
               [[fmt(D(k)), v_fmr(v), v_info(v)] for k, v in sorted(por_dia.items())])
    soma_pres = sum(v["presencas"] for v in por_dia.values())
    soma_fmr = sum(v_fmr(v) for v in por_dia.values())
    dias_func = len(por_dia)
    unicos = {p for v in por_dia.values() for p in v["distintas"]}
    print(f"  Dias de funcionamento (com aula realizada): {dias_func}")
    print(f"  Total no mês: {soma_fmr}" + (f"   Média diária: {soma_fmr / dias_func:.1f}" if dias_func else ""))
    print(f"  Participantes únicos no mês (indivíduos diferentes): {len(unicos)}")
    print("  Regra adotada: contar ocorrências (prática atual do NCI). Se a SMADS exigir pessoas")
    print("  distintas por dia, troque CONTAGEM_PESSOAS_POR_DIA no início do arquivo.")
    if por_dia:
        check(max(v_fmr(v) for v in por_dia.values()) <= len(permanecem),
              "pessoas por dia <= pessoas que permanecem no mês (regra do FMR)")

    # 2. Pessoas atendidas
    subtitulo("2. Pessoas atendidas no mês")
    imprimir_faixa_sexo("Vieram do mês anterior", vieram, ref)
    imprimir_faixa_sexo("Entraram no mês", [i for i, _ in entradas], ref)
    imprimir_faixa_sexo("Saíram no mês", [i for i, _ in saidas], ref)
    imprimir_faixa_sexo("Permanecem no último dia", permanecem, ref)
    check(len(permanecem) == len(vieram) + len(entradas) - len(saidas),
          f"permanecem ({len(permanecem)}) = vieram ({len(vieram)}) + entraram ({len(entradas)}) - saíram ({len(saidas)})")

    # 3. Saídas
    subtitulo("3. Saídas: motivo e tempo de permanência")
    cm = contar(saidas, lambda x: x[1]["motivo_saida"])
    tabela(["motivo de saída", "quantidade"], [[m, cm.get(m, 0)] for m in MOTIVOS_SAIDA] + [["TOTAL", len(saidas)]])
    def faixa_tempo(p):
        dias = (D(p["saida"]) - D(p["entrada"])).days
        return ("Até 6 meses" if dias <= 182 else "Entre 6 meses e 1 ano" if dias <= 365
                else "Entre 1 ano e 3 anos" if dias <= 1095 else "Mais de 3 anos")
    ct = contar(saidas, lambda x: faixa_tempo(x[1]))
    tabela(["tempo de permanência (período que terminou)", "quantidade"],
           [[t, ct.get(t, 0)] for t in ["Até 6 meses", "Entre 6 meses e 1 ano", "Entre 1 ano e 3 anos", "Mais de 3 anos"]])
    check(sum(cm.values()) == len(saidas), "soma dos motivos = número de saídas")

    # 4. Ingressantes
    subtitulo("4. Ingressantes no mês, por origem")
    co = contar(entradas, lambda x: x[1]["origem"])
    tabela(["origem", "quantidade", "vai ao FMR?"],
           [[o, co.get(o, 0), "sim" if o in ORIGENS_FMR else "não (controle interno)"] for o in ORIGENS])

    # 5. Perfil de quem permanece
    subtitulo("5. Perfil de quem permanece (sexo x raça/cor, gênero, situação)")
    linhas = []
    for s, rot in (("F", "Feminino"), ("M", "Masculino")):
        linhas.append([rot] + [sum(1 for i in permanecem if i["sexo"] == s and i["raca_cor"] == r) for r in RACAS]
                      + [sum(1 for i in permanecem if i["sexo"] == s)])
    linhas.append(["Total"] + [sum(1 for i in permanecem if i["raca_cor"] == r) for r in RACAS] + [len(permanecem)])
    tabela(["sexo"] + RACAS + ["Total"], linhas)
    cg = contar(permanecem, lambda i: i["identidade_genero"])
    tabela(["identidade de gênero", "quantidade"], [[g, cg.get(g, 0)] for g in GENEROS] + [["Total", len(permanecem)]])
    sits = [(i, situacao_em(i, fim)) for i in permanecem]
    sem_sit = [i for i, s in sits if s is None]
    sozinhos = [s for _, s in sits if s and s["mora_sozinho"]]
    apoio = [s for s in sozinhos if s["apoio"]]
    deficiencia = [s for _, s in sits if s and s["deficiencia"]]
    bpc = [s for _, s in sits if s and s["bpc"]]
    imig = [i for i in permanecem if i["imigrante"]]
    cr = contar([s for _, s in sits if s], lambda s: s["regiao"])
    tabela(["indicador", "quantidade"], [
        ["Moram sozinhos", len(sozinhos)], ["  desses, com apoio família/comunidade", len(apoio)],
        ["Pessoas com deficiência", len(deficiencia)], ["Recebem BPC", len(bpc)],
        ["Imigrantes/refugiados", len(imig)]])
    tabela(["região de moradia", "quantidade"], [[r, cr.get(r, 0)] for r in REGIOES] + [["Total", sum(cr.values())]])
    if sem_sit:
        print(f"  ATENÇÃO: {len(sem_sit)} pessoa(s) sem situação cadastrada na data.")
    check(len(sozinhos) <= len(permanecem) and len(apoio) <= len(sozinhos), "apoio <= moram sozinhos <= permanecem")
    check(sum(cr.values()) == len(permanecem), "total por região = permanecem")
    check(sum(cg.values()) == len(permanecem), "total por gênero = permanecem")

    # 6. Atividades
    subtitulo("6. Atividades por categoria do FMR")
    linhas = []
    tot_a = tot_p = 0
    for cat in CATEGORIAS_FMR:
        oc_cat = [o for o in ocs if por_id(db["atividades"], o["atividade_id"])["categoria"] == cat]
        part = sum(1 for o in oc_cat for v in o["presencas"].values() if v == "P")
        linhas.append([cat, len(oc_cat), part])
        tot_a += len(oc_cat)
        tot_p += part
    linhas.append(["TOTAL", tot_a, tot_p])
    tabela(["categoria", "nº de atividades (aulas realizadas)", "nº de participações"], linhas)
    check(tot_p == soma_pres, "total de participações = total de presenças por dia (ocorrências)")

    # Extra: justificativas
    subtitulo("Extra (fora do FMR): faltas justificadas por motivo")
    cj = {}
    for o in ocs:
        for v in o["justificativas"].values():
            cj[v["motivo"]] = cj.get(v["motivo"], 0) + 1
    tabela(["motivo", "quantidade"], sorted([[m, n] for m, n in cj.items()], key=lambda x: -x[1]))

    subtitulo("NÃO CALCULÁVEIS COM CADASTRO + FREQUÊNCIA (precisam de registro/informação manual)")
    for t in ["Famílias de idosos atendidas e vulnerabilidades (isolamento, confinamento...)",
              "Ações coletivas com famílias (reuniões, passeios, oficinas, palestras, eventos)",
              "Ações de articulação em rede e encaminhamentos feitos pelo serviço",
              "Temas discutidos (nº de atividades e participações por tema)",
              "Atendimento domiciliar (fora do MVP, decisão da equipe)"]:
        print(f"  - {t}")

    if sim_nao("\nListar os NOMES de cada grupo (auditoria da contagem)?", False):
        for rot, lista in (("Vieram do mês anterior", vieram), ("Entraram no mês", [i for i, _ in entradas]),
                           ("Saíram no mês", [i for i, _ in saidas]), ("Permanecem", permanecem)):
            print(f"\n  {rot} ({len(lista)}):")
            for i in sorted(lista, key=lambda x: x["nome"].casefold()):
                idade = idade_em(D(i["data_nascimento"]), ref)
                print(f"    - {i['nome']} ({faixa_de(idade)}, {i['sexo']}, {i['raca_cor']})")

# ----------------------------------------------------------------------------
# Dados fictícios para demonstração
# ----------------------------------------------------------------------------
def carregar_demo(db):
    if db["idosos"] and not sim_nao("Já existem dados. Apagar TUDO e carregar a demonstração?", False):
        return
    db.clear()
    db.update(novo_banco())
    random.seed(42)
    hoje_ref = date(2026, 9, 30)
    reg = "Subprefeitura do serviço"
    # nome, nascimento, sexo, raça, gênero, imigrante, entrada, origem, sozinho, apoio, def, bpc, região, (saida, motivo)
    base = [
        ("Ana Lima (fictícia)", "1950-03-12", "F", "Branca", "Cisgênero", False, "2018-02-10", "CRAS", True, True, False, False, reg, None),
        ("Beatriz Souza (fictícia)", "1946-07-01", "F", "Parda", "Cisgênero", False, "2017-05-20", "Demanda espontânea / outra", True, False, False, True, reg, None),
        ("Carlos Pereira (fictício)", "1944-11-23", "M", "Preta", "Cisgênero", False, "2016-08-15", "CRAS", False, None, True, False, reg, None),
        ("Dora Nunes (fictícia)", "1958-01-30", "F", "Branca", "Cisgênero", False, "2026-09-08", "CRAS", True, True, False, False, reg, None),
        ("Eduardo Reis (fictício)", "1959-05-05", "M", "Parda", "Cisgênero", False, "2026-09-14", "Demanda espontânea / outra", False, None, False, False, "Outra subprefeitura", None),
        ("Fátima Oliveira (fictícia)", "1941-09-09", "F", "Branca", "Cisgênero", False, "2015-03-03", "CREAS", True, True, False, False, reg, ("2026-09-15", "Mudança de endereço")),
        ("Gilda Matos (fictícia)", "1953-12-02", "F", "Amarela", "Cisgênero", False, "2019-06-10", "Outros serviços da rede socioassistencial", False, None, False, False, reg, None),
        ("Hélio Costa (fictício)", "1949-04-18", "M", "Branca", "Cisgênero", False, "2020-02-02", "CRAS", True, False, False, False, reg, None),
        ("Irene Duarte (fictícia)", "1955-08-27", "F", "Parda", "Cisgênero", True, "2021-10-11", "Demanda espontânea / outra", True, True, False, False, "Outro município", None),
        ("Júlia Ramos (fictícia)", "1947-02-14", "F", "Branca", "Cisgênero", False, "2014-01-20", "CRAS", True, True, False, False, reg, None),
        ("Lauro Pinto (fictício)", "1962-10-10", "M", "Preta", "Cisgênero", False, "2022-03-07", "CRAS", False, None, False, False, reg, None),
        ("Marta Vidal (fictícia)", "1943-06-06", "F", "Branca", "Cisgênero", False, "2013-04-01", "CRAS", True, True, True, True, reg, None),
        ("Nair Campos (fictícia)", "1951-03-21", "F", "Indígena", "Cisgênero", False, "2018-09-09", "CREAS", False, None, False, False, reg, None),
        ("Olavo Teixeira (fictício)", "1945-12-12", "M", "Parda", "Cisgênero", False, "2012-05-05", "CRAS", True, False, False, False, reg, None),
    ]
    for (nome, nasc, sx, rc, gn, im, ent, org, soz, ap, de, bp, rg, sai) in base:
        p = [{"entrada": ent, "origem": org, "saida": sai[0] if sai else None, "motivo_saida": sai[1] if sai else None}]
        db["idosos"].append({"id": novo_id(db), "nome": nome, "data_nascimento": nasc, "sexo": sx, "raca_cor": rc,
                             "identidade_genero": gn, "imigrante": im, "contato": "", "periodos": p,
                             "situacoes": [{"inicio": ent, "mora_sozinho": soz, "apoio": ap, "deficiencia": de,
                                            "bpc": bp, "regiao": rg}]})
    # idosa que saiu em 2025 e voltou em 09/2026 (reativação)
    db["idosos"].append({"id": novo_id(db), "nome": "Paula Faria (fictícia)", "data_nascimento": "1952-05-17", "sexo": "F",
                         "raca_cor": "Branca", "identidade_genero": "Cisgênero", "imigrante": False, "contato": "",
                         "periodos": [{"entrada": "2016-02-01", "origem": "CRAS", "saida": "2025-04-30", "motivo_saida": "Desistência"},
                                      {"entrada": "2026-09-01", "origem": "Retorno (reativação)", "saida": None, "motivo_saida": None}],
                         "situacoes": [{"inicio": "2016-02-01", "mora_sozinho": True, "apoio": True, "deficiencia": False,
                                        "bpc": False, "regiao": reg}]})
    # idoso desligado em 2024 (não deve aparecer no FMR de 09/2026)
    db["idosos"].append({"id": novo_id(db), "nome": "Quirino Alves (fictício)", "data_nascimento": "1948-01-01", "sexo": "M",
                         "raca_cor": "Parda", "identidade_genero": "Cisgênero", "imigrante": False, "contato": "",
                         "periodos": [{"entrada": "2015-01-01", "origem": "CRAS", "saida": "2024-06-30", "motivo_saida": "Óbito"}],
                         "situacoes": [{"inicio": "2015-01-01", "mora_sozinho": False, "apoio": None, "deficiencia": False,
                                        "bpc": False, "regiao": reg}]})
    # atividades: nome, categoria, dias (weekday), horário, tipo
    ats = [("Pilates", "Atividades esportivas", [1, 4], "09:00", "10:00", "Aula regular"),
           ("Yoga Ayurveda", "Atividades esportivas", [0], "10:30", "11:30", "Aula regular"),
           ("Dança Sênior", "Atividades de arte e cultura", [0], "15:00", "16:00", "Aula regular"),
           ("Tricô", "Artesanato", [3], "14:00", "15:00", "Aula regular"),
           ("Clube de Leitura", "Atividades de estimulação cognitiva", [2], "14:00", "16:00", "Aula regular"),
           ("Passeio ao museu", "Atividades externas", [], "", "", "Evento / ação pontual")]
    for nome, cat, dias, hi, hf, tp in ats:
        db["atividades"].append({"id": novo_id(db), "nome": nome, "local": "AAESP", "monitor": "(fictício)",
                                 "categoria": cat, "tipo": tp, "ativa": True,
                                 "horarios": [{"dia": d, "inicio": hi, "fim": hf} for d in dias]})
    ativos = [i for i in db["idosos"] if i["nome"] not in ("Quirino Alves (fictício)",)]
    for a in db["atividades"]:
        for i in ativos:
            if random.random() < 0.55 or a["tipo"].startswith("Evento"):
                ent = max(D(i["periodos"][-1]["entrada"]), date(2025, 1, 1))
                sai = i["periodos"][-1]["saida"]
                db["inscricoes"].append({"id": novo_id(db), "idoso_id": i["id"], "atividade_id": a["id"],
                                         "entrada": iso(ent), "saida": sai})
    # chamadas de setembro/2026
    motivos = db["justificativas"]
    d = date(2026, 9, 1)
    while d <= hoje_ref:
        for a in db["atividades"]:
            grade = [h["dia"] for h in a["horarios"]]
            if a["tipo"].startswith("Evento"):
                aula = d == date(2026, 9, 26)
            elif a["nome"] == "Dança Sênior" and d == date(2026, 9, 17):
                aula = True  # quinta-feira, fora da grade (reposição)
            else:
                aula = d.weekday() in grade
            if not aula:
                continue
            hora = a["horarios"][0]["inicio"] if a["horarios"] else ""
            oc = {"id": novo_id(db), "atividade_id": a["id"], "data": iso(d), "hora_inicio": hora,
                  "extra": False, "motivo_extra": None, "situacao": "realizada",
                  "motivo_cancelamento": None, "presencas": {}, "justificativas": {}}
            if a["nome"] == "Dança Sênior" and d == date(2026, 9, 17):
                oc["hora_inicio"], oc["extra"], oc["motivo_extra"] = "10:00", True, "Reposição de aula"
            if d == date(2026, 9, 7):
                oc["situacao"], oc["motivo_cancelamento"] = "cancelada", "Feriado (Independência)"
            else:
                for i in inscritos_na_data(db, a["id"], d):
                    r = random.random()
                    if r < 0.78:
                        oc["presencas"][str(i["id"])] = "P"
                    elif r < 0.90:
                        oc["presencas"][str(i["id"])] = "J"
                        oc["justificativas"][str(i["id"])] = {"motivo": random.choice(motivos), "obs": ""}
                    else:
                        oc["presencas"][str(i["id"])] = "A"
            db["ocorrencias"].append(oc)
        d += timedelta(days=1)
    registrar_log(db, "demo_carregada", "dados fictícios de setembro/2026")
    salvar(db)
    print("  Demonstração carregada (dados FICTÍCIOS). Gere o FMR do mês 09/2026.")

# ----------------------------------------------------------------------------
# Menu
# ----------------------------------------------------------------------------
MENU = [
    ("Cadastrar idoso", cadastrar_idoso),
    ("Listar / buscar idosos (e ver ficha)", listar_idosos),
    ("Atualizar situação (mora sozinho, BPC, deficiência, região)", editar_situacao),
    ("Desligar idoso (com motivo do FMR)", desligar_idoso),
    ("Reativar idoso", reativar_idoso),
    ("Cadastrar atividade", cadastrar_atividade),
    ("Listar atividades", listar_atividades),
    ("Inscrever idoso em atividade", inscrever),
    ("Encerrar inscrição em atividade", encerrar_inscricao),
    ("Registrar frequência da aula (do papel para o sistema)", registrar_frequencia),
    ("Carregar dados FICTÍCIOS de demonstração", carregar_demo),
    ("Frequência mensal (por atividade ou geral)", frequencia_mensal),
    ("RELATÓRIO FMR (indicadores calculados)", relatorio_fmr),
]

def main():
    db = carregar()
    while True:
        titulo("NCI IDADE DOURADA DE PINHEIROS - protótipo em console")
        for n, (rot, _) in enumerate(MENU, 1):
            print(f"  {n:>2}) {rot}")
        print("   0) Sair")
        try:
            r = input("Opção: ").strip()
            if r == "0":
                break
            if r.isdigit() and 1 <= int(r) <= len(MENU):
                MENU[int(r) - 1][1](db)
            else:
                print("  Opção inválida.")
        except (EOFError, KeyboardInterrupt):
            print("\nEncerrando.")
            break

if __name__ == "__main__":
    main()
