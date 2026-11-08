# FMR e relatórios — requisitos

> Fonte: `Requisitos_NCI_RF_RNF_RN_Revisado_v2.docx` (revisão aprovada até o momento). Este arquivo descreve **o que** o sistema deve fazer; não indica que algo já foi implementado.
> Convenção: **Confirmado** = definição aceita; **Pendente** = depende de validação. **MVP/Depois** = prioridade.

## RF — Requisitos funcionais

### RF-FMR-01 — Confirmado

Permitir selecionar o mês de referência para consultar o FMR de convivência.

- **Prioridade:** MVP
- **Fonte:** FMR; D09
- **Status da definição:** Confirmado

### RF-FMR-02 — Confirmado

Exibir em uma única área somente os indicadores do FMR de convivência que o MVP consegue calcular com os dados disponíveis, sem exigir cobertura integral do formulário.

- **Prioridade:** MVP
- **Fonte:** D09
- **Status da definição:** Confirmado

### RF-FMR-03 — Pendente (P06 para média)

Apresentar presenças por data, total mensal e média diária, distinguindo ocorrências de participantes únicos.

- **Prioridade:** MVP
- **Fonte:** FMR; D10; §6.4
- **Status da definição:** Pendente (P06 para média)

### RF-FMR-04 — Confirmado

Apresentar os participantes que permanecem no serviço no último dia do mês.

- **Prioridade:** MVP
- **Fonte:** FMR, §6.4
- **Status da definição:** Confirmado

### RF-FMR-05 — Pendente (P01 para aniversários)

Apresentar os totais por faixa etária e sexo de vindos do mês anterior, ingressantes, desligados e permanentes.

- **Prioridade:** MVP
- **Fonte:** FMR, §6.4
- **Status da definição:** Pendente (P01 para aniversários)

### RF-FMR-06 — Confirmado

Apresentar os desligamentos agrupados por motivo do FMR.

- **Prioridade:** MVP
- **Fonte:** FMR, §6.4
- **Status da definição:** Confirmado

### RF-FMR-07 — Confirmado

Apresentar ingressantes encaminhados por CRAS, CREAS e outros serviços da rede.

- **Prioridade:** MVP
- **Fonte:** FMR, §6.4
- **Status da definição:** Confirmado

### RF-FMR-08 — Confirmado

Apresentar os indicadores de sexo por raça/cor, identidade de gênero, imigrantes/refugiados e região de moradia.

- **Prioridade:** MVP
- **Fonte:** FMR, §6.4
- **Status da definição:** Confirmado

### RF-FMR-09 — Confirmado

Apresentar indicadores mensais de pessoas que moram sozinhas, têm apoio, possuem deficiência e recebem BPC.

- **Prioridade:** MVP
- **Fonte:** FMR, §6.4
- **Status da definição:** Confirmado

### RF-FMR-10 — Pendente (P04: mapeamento)

Apresentar, por categoria do FMR, a quantidade de aulas realizadas e a soma de participações.

- **Prioridade:** MVP
- **Fonte:** FMR; D10; §6.3
- **Status da definição:** Pendente (P04: mapeamento)

### RF-FMR-11 — Confirmado

Identificar, quando pertinente, os campos do FMR que não são contemplados pelo MVP ou não possuem dados ou regra de cálculo suficientes, sem inventar ou preencher automaticamente seus valores.

- **Prioridade:** MVP
- **Fonte:** §6.4; §6.4 nota final
- **Status da definição:** Confirmado

### RF-FMR-12 — Confirmado

Apresentar avisos quando os valores do FMR não respeitarem as regras de consistência conhecidas.

- **Prioridade:** MVP
- **Fonte:** FMR, §6.2; PROTO, §14
- **Status da definição:** Confirmado

### RF-FMR-13 — Confirmado

Disponibilizar dados organizados para transcrição manual ao portal da SMADS, sem depender de integração com o portal.

- **Prioridade:** MVP
- **Fonte:** D09
- **Status da definição:** Confirmado

### RF-FMR-14 — Pendente (detalhamento do cálculo)

Calcular a faixa de tempo de permanência de participantes desligados com base no período pertinente ao desligamento, sem somar períodos anteriores a uma reativação. A forma de determinar as faixas e a data inicial aplicável ainda depende de validação.

- **Prioridade:** MVP
- **Fonte:** FMR, §6.4; P03
- **Status da definição:** Pendente (detalhamento do cálculo)

### RF-FMR-15 — Pendente (P07)

Registrar os totais mensais não deriváveis do cadastro ou frequência, caso o NCI decida incluí-los no sistema.

- **Prioridade:** Depois
- **Fonte:** P07; §6.4
- **Status da definição:** Pendente (P07)

### RF-FMR-16 — Pendente (P09, P10)

Gerar exportação estruturada do FMR e a planilha trimestral para outros órgãos.

- **Prioridade:** Depois
- **Fonte:** §12; P09; P10
- **Status da definição:** Pendente (P09, P10)

### RF-FMR-17 — Pendente (P07)

Registrar eventos pontuais, vulnerabilidades, articulações em rede, encaminhamentos e temas para ampliar os relatórios.

- **Prioridade:** Depois
- **Fonte:** §12; P07
- **Status da definição:** Pendente (P07)

### RF-FMR-18 — Confirmado (fora do MVP)

Registrar atendimento domiciliar e indicadores do segundo bloco do FMR.

- **Prioridade:** Depois
- **Fonte:** D12; §12
- **Status da definição:** Confirmado (fora do MVP)

## RN — Regras de negócio

### RN-FMR-01 — Confirmado

Para cada faixa etária e sexo: permanecem = vieram do mês anterior + ingressaram − saíram.

- **Prioridade:** MVP
- **Fonte:** FMR, §6.2
- **Status da definição:** Confirmado

### RN-FMR-02 — Confirmado

A soma dos desligamentos por motivo deve ser igual ao total de desligamentos no mês.

- **Prioridade:** MVP
- **Fonte:** FMR, §6.2
- **Status da definição:** Confirmado

### RN-FMR-03 — Confirmado

A soma dos participantes classificados por região de moradia deve ser igual ao total dos que permanecem.

- **Prioridade:** MVP
- **Fonte:** FMR, §6.2
- **Status da definição:** Confirmado

### RN-FMR-04 — Confirmado

Os totais de sexo por raça/cor e de identidade de gênero devem corresponder ao total de participantes que permanecem.

- **Prioridade:** MVP
- **Fonte:** FMR, §6.2
- **Status da definição:** Confirmado

### RN-FMR-05 — Confirmado

A quantidade de participantes que moram sozinhos não pode superar o total de permanentes no mês.

- **Prioridade:** MVP
- **Fonte:** FMR, §6.2
- **Status da definição:** Confirmado

### RN-FMR-06 — Confirmado

A quantidade de participantes que moram sozinhos e têm apoio não pode superar a de participantes que moram sozinhos.

- **Prioridade:** MVP
- **Fonte:** FMR, §6.2
- **Status da definição:** Confirmado

### RN-FMR-07 — Pendente (conflito a validar)

O número de presenças computadas em um dia não pode superar o de permanentes no último dia do mês segundo a regra de validação apresentada no FMR; eventual conflito com contagem por ocorrências deve ser sinalizado para revisão.

- **Prioridade:** MVP
- **Fonte:** FMR, §6.2; D10
- **Status da definição:** Pendente (conflito a validar)

### RN-FMR-08 — Confirmado

As faixas etárias do FMR são 60–64, 65–69, 70–74 e 75 anos ou mais, com classificação por sexo M/F.

- **Prioridade:** MVP
- **Fonte:** FMR, §6.2
- **Status da definição:** Confirmado

### RN-FMR-09 — Confirmado

Por padrão, «pessoas por dia» deve contar ocorrências de presença por aula; a regra deve ser configurável para participantes distintos se houver orientação diferente.

- **Prioridade:** MVP
- **Fonte:** D10; §6.3
- **Status da definição:** Confirmado

### RN-FMR-10 — Confirmado

«Número de atividades» deve corresponder às aulas efetivamente realizadas no mês na respectiva categoria.

- **Prioridade:** MVP
- **Fonte:** D10; §6.3
- **Status da definição:** Confirmado

### RN-FMR-11 — Confirmado

«Número de participações» deve corresponder à soma dos registros de presença nas aulas da categoria.

- **Prioridade:** MVP
- **Fonte:** D10; §6.3
- **Status da definição:** Confirmado

### RN-FMR-12 — Confirmado

Os números de meses anteriores devem ser derivados do histórico com vigência temporal, sem reclassificação retroativa pela situação atual.

- **Prioridade:** MVP
- **Fonte:** FMR, §6.1
- **Status da definição:** Confirmado

### RN-FMR-13 — Confirmado

O MVP não precisa preencher o FMR inteiro; indicadores fora de seu escopo ou sem dados/regras validadas não devem receber valores estimados ou calculados por presunção.

- **Prioridade:** MVP
- **Fonte:** §6.4
- **Status da definição:** Confirmado

### RN-FMR-14 — Pendente (P06)

«Dias de funcionamento» e sua utilização na média diária dependem de definição do NCI.

- **Prioridade:** MVP
- **Fonte:** P06
- **Status da definição:** Pendente (P06)

### RN-FMR-15 — Pendente (intervalo de cálculo)

O tempo de permanência de quem saiu deve ser classificado nas faixas até 6 meses, 6 meses a 1 ano, 1 a 3 anos e mais de 3 anos, sem agregar tempo anterior à reativação. A definição operacional do intervalo a considerar permanece pendente.

- **Prioridade:** MVP
- **Fonte:** FMR, §6.4; P03
- **Status da definição:** Pendente (intervalo de cálculo)
