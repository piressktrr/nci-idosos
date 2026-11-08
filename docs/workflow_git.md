# Workflow Git para dois desenvolvedores

## Branches

- `main`: versão estável; integrar somente código validado.
- `develop`: base de integração compartilhada, após configurar projeto e contratos essenciais.
- `feature/<area>-<ID>`: uma funcionalidade por branch curta, a partir da `develop` atualizada. Ex.: `feature/participantes-RF-PAR-02`.
- Branches maiores por área também são possíveis, mas criam PRs maiores e risco de divergência. **Preferir branches pequenas por requisito**, mesmo se cada pessoa assumir áreas diferentes.

## Passo a passo

1. Juntos: aprovar contratos em `docs/dependencias.md`, iniciar projeto Django, PostgreSQL por variáveis de ambiente, modelo de usuário e migrações fundacionais; integrar primeiro em `develop`.
2. Cada um: atualizar `develop` via `git fetch`/`git pull --ff-only`, criar branch própria para **um único** requisito.
3. Antes de editar: `git status`, conferir branch e arquivos do colega; trabalhar apenas no app responsável e no próprio arquivo de progresso, sempre que possível.
4. Implementar **um** requisito, adicionar testes; executar testes localmente. Commit pequeno, incluindo documentação de progresso correspondente.
5. Abrir pull request para `develop` com ID, escopo, evidências dos testes, alterações de migrations, dependências entre áreas e riscos.
6. O outro desenvolvedor revisa; CI executa testes. Resolver conflitos conscientemente, testar migrações e integrações; merge em `develop`.
7. Promover `develop` para `main` apenas com testes de integração e revisão de dependências concluídos.

## Convenções de commit

- `feat(participantes): implementa RF-PAR-02`
- `feat(atividades): implementa RF-ATV-05`
- `fix(fmr): corrige calculo RN-FMR-02`
- `test(usuarios): cobre permissao RF-USR-03`
- `docs(participantes): registra bloqueio P02`

## Política para alterações comuns

- `settings.py`, `urls.py`, `pyproject.toml/requirements`, `AUTH_USER_MODEL`, migrations e serviços compartilhados: negociar antes.
- Nunca editar migration de outra branch já aplicada; criar migration nova e conferir dependências após merge.
- Em caso de conflito, não executar `git checkout --theirs`, `reset --hard` ou rebases destrutivos sem revisar o impacto.
- Evitar mudanças de formatação/refatorações não relacionadas ao ID.
- Nunca commitar `.env`, segredos, banco local ou dados pessoais reais; usar `.env.example` sem credenciais.

## Exemplo de PR

```md
## Requisito
RF-PAR-02

## Mudanças
- Campos e validações necessárias ao requisito.

## Testes
- Comando: ...
- Resultado: ...

## Dependências
- Contratos usados: ...
- Requer merge de: ... (ou nenhuma)

## Banco
- Migrations novas: ... (ou nenhuma)

## Itens ainda pendentes
- ...
```

## Nota sobre automação

Se o repositório tiver GitHub Actions, manter execução de testes Django e validação de migrations no PR para `develop`. Sem workflow existente, criar CI em tarefa específica de infraestrutura, **não** como efeito colateral de um requisito aleatório. Não supor que workflow/CI existe sem verificar.
