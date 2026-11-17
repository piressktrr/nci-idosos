"""Auditoria das contas de acesso (RNF-SEG-07), na tabela única core.EventoAuditoria.

As contas são o `auth.User` padrão do Django; este app não tem tabela própria. O alvo se chama "conta" porque
`usuario` já é o autor do evento em `EventoAuditoria`.

Com este proxy, o `pre_delete` do core (CoreConfig.ready) passa a barrar a exclusão de contas com eventos.
"""

from core.models import EventoAuditoria


class RegistroConta(EventoAuditoria):
    """Cadastro, correção e redefinição de senha de uma conta. Nunca guarda senha nem hash."""

    alvo, modelo_alvo = "conta", "auth.User"

    class Meta:
        proxy = True
        default_permissions = ()
