"""RF-FMR-11: identifica limitações da consulta, sem calcular ou substituir valores."""


def identificar_campos_indisponiveis(dados):
    campos = []

    def adicionar(campo, pendencia):
        campos.append({"campo": campo, "situacao": "Aguardando dados ou definição",
                       "motivo": pendencia["aviso"], "explicacao": pendencia["explicacao"]})

    def acesso(campo, aviso):
        campos.append({"campo": campo, "situacao": "Indisponível nesta consulta",
                       "motivo": aviso, "explicacao": aviso})

    for chave, rotulo in (
        ("permanentes", "Participantes que permanecem no serviço"),
        ("movimentacao_etaria", "Movimentação por faixa etária e sexo"),
        ("desligamentos_motivo", "Desligamentos por motivo"),
        ("tempo_permanencia", "Tempo de permanência dos desligados"),
        ("ingressantes_encaminhamento", "Ingressantes por encaminhamento"),
        ("situacao_social", "Situação social dos participantes"),
        ("categorias_atividades", "Atividades e participações por categoria"),
    ):
        bloco = dados.get(chave, {})
        if bloco.get("aviso"):
            acesso(rotulo, bloco["aviso"])
            continue
        pendencias = list(bloco.get("pendencias", []))
        if bloco.get("pendencia"):
            pendencias.append(bloco["pendencia"])
        for pendencia in pendencias:
            adicionar(rotulo, pendencia)

    perfil = dados.get("perfil_demografico", {})
    if perfil.get("aviso"):
        acesso("Perfil demográfico dos participantes", perfil["aviso"])
    else:
        for bloco in perfil.get("blocos_pendentes", []):
            adicionar(bloco["titulo"], bloco)
        if perfil.get("pendencia_imigrantes"):
            adicionar("Imigrantes/refugiados", perfil["pendencia_imigrantes"])
    if dados.get("aviso"):
        acesso("Aulas, participações e presenças", dados["aviso"])
    presencas = dados.get("presencas")
    if presencas is not None and presencas.get("media_diaria") is None:
        campos.append({"campo": "Média diária", "situacao": "Sem base para cálculo",
                       "motivo": "Não houve dias com atendimento registrado neste mês.",
                       "explicacao": "Sem dias com atendimento, o divisor é zero. A média fica sem cálculo; "
                           "os totais mensais e as quantidades diárias continuam disponíveis."})

    for campo, motivo in (
        ("Totais mensais não derivados do cadastro ou frequência",
         "Registro manual desses totais previsto para etapa posterior, sujeito à definição do NCI."),
        ("Eventos pontuais, vulnerabilidades, articulações em rede, encaminhamentos e temas",
         "Registro complementar para ampliação dos relatórios previsto para etapa posterior ao MVP."),
        ("Atendimento domiciliar e indicadores do segundo bloco do FMR",
         "Este bloco está fora do MVP de convivência."),
    ):
        campos.append({"campo": campo, "situacao": "Fora do MVP", "motivo": motivo,
                       "explicacao": motivo + " Nenhum valor é estimado ou preenchido automaticamente."})
    return campos
