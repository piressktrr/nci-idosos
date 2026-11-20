"""Auditoria comum (RNF-SEG-07): tabela única de eventos, sem FK para modelos de domínio.

Cada app declara seus tipos como proxies de `EventoAuditoria` com `alvo` (nome do objeto auditado, ex.
"atividade") e `modelo_alvo` (classe ou "app_label.Modelo"). A coluna `tipo` guarda o nome do proxy e
`alvo_id` a PK do objeto. O manager do proxy filtra pelo tipo e traduz `atividade=obj`/`atividade_id=`
para `alvo_id`; o proxy ganha a property `atividade` (objeto) e `atividade_id`.

Integridade sem FK: os modelos auditados herdam `ProtegidoPorAuditoria`, que recusa `delete()` de objeto
com eventos; um `pre_delete` (ligado em CoreConfig.ready) também bloqueia exclusões em massa e em cascata.
Exclusões por SQL direto ou `_base_manager` não são cobertas.
"""

from django.apps import apps
from django.conf import settings
from django.db import IntegrityError, models
from django.db.models.deletion import ProtectedError
from django.utils import timezone

# tipo (nome do proxy) -> classe proxy; preenchido na definição de cada proxy com `alvo`.
TIPOS_AUDITORIA = {}

# Lookups que, após o nome do alvo, se aplicam ao próprio alvo_id (o resto vira subconsulta no modelo alvo).
_LOOKUPS_ID = frozenset({"exact", "in", "isnull", "gt", "gte", "lt", "lte", "range"})
# Nomes antigos dos campos de dados (contrato legado dos serviços de atividades).
_ALIASES_DADOS = {"dados": "novos", "dados_novos": "novos", "dados_anteriores": "anteriores"}
# Tipos com no máximo um evento por objeto (índices únicos parciais).
TIPOS_UNICOS_POR_ALVO = {
    "RegistroCadastroAtividade": "core_evento_cadastro_unico",
    "RegistroRealizacaoAula": "core_evento_realizacao_unica",
    "RegistroCancelamentoAula": "core_evento_cancelamento_unico",
    "RegistroLancamentoFrequencia": "core_evento_lancamento_unico",
}


class AuditoriaImutavel(Exception):
    """Tentativa de alterar ou excluir evento de auditoria."""


def _pk(valor):
    return valor.pk if isinstance(valor, models.Model) else valor


def tipos_do_modelo(modelo):
    """Tipos de evento cujo alvo é `modelo` (classe concreta)."""
    concreto = modelo._meta.concrete_model
    return [tipo for tipo, proxy in TIPOS_AUDITORIA.items() if proxy.modelo_alvo_resolvido() is concreto]


def eventos_do_objeto(objeto):
    tipos = tipos_do_modelo(type(objeto))
    if not tipos or objeto.pk is None:
        return EventoAuditoria.objects.none()
    return EventoAuditoria.objects.filter(tipo__in=tipos, alvo_id=objeto.pk)


def _recusar_se_auditado(objeto):
    eventos = eventos_do_objeto(objeto)
    if eventos.exists():
        raise ProtectedError(
            f"Não é possível excluir {objeto._meta.verbose_name} com eventos de auditoria.", eventos[:10])


def bloquear_exclusao_auditada(sender, instance, **kwargs):
    """Receptor de pre_delete para exclusões que não passam por Model.delete (QuerySet.delete, cascata).

    Levanta dentro da transação do Collector; a transação externa, se houver, fica marcada para rollback.
    """
    if not instance.__dict__.pop("_auditoria_verificada", False):
        _recusar_se_auditado(instance)


class ProtegidoPorAuditoria:
    """Mixin para modelos auditados: substitui o PROTECT que a FK fazia no banco.

    A verificação ocorre antes da transação do Collector, então o erro não invalida a transação externa.
    """

    def delete(self, *args, **kwargs):
        _recusar_se_auditado(self)
        self._auditoria_verificada = True
        try:
            return super().delete(*args, **kwargs)
        finally:
            self.__dict__.pop("_auditoria_verificada", None)


class EventoAuditoriaQuerySet(models.QuerySet):
    def _alvo(self):
        return TIPOS_AUDITORIA.get(self.model.__name__) if self.model is not EventoAuditoria else None

    def _filter_or_exclude_inplace(self, negate, args, kwargs):
        proxy = self._alvo()
        if proxy is not None:
            kwargs = proxy.traduzir_filtros(kwargs)
        return super()._filter_or_exclude_inplace(negate, args, kwargs)

    def create(self, **kwargs):
        for antigo, novo in _ALIASES_DADOS.items():
            if antigo in kwargs:
                kwargs[novo] = kwargs.pop(antigo)
        if self.model is not EventoAuditoria:
            kwargs["tipo"] = self.model.__name__
        nomes_alvo = {proxy.alvo for proxy in TIPOS_AUDITORIA.values()}
        informados = [chave for chave in kwargs if chave.removesuffix("_id") in nomes_alvo]
        if informados:
            proxy = TIPOS_AUDITORIA.get(kwargs.get("tipo"))
            if len(informados) > 1 or proxy is None or informados[0].removesuffix("_id") != proxy.alvo:
                raise IntegrityError(f"Alvo {informados} incoerente com o tipo de evento {kwargs.get('tipo')!r}.")
            valor = kwargs.pop(informados[0])
            if isinstance(valor, models.Model) and not isinstance(valor, proxy.modelo_alvo_resolvido()):
                raise IntegrityError(f"{proxy.alvo!r} deve ser {proxy.modelo_alvo_resolvido().__name__}.")
            kwargs["alvo_id"] = _pk(valor)
        return super().create(**kwargs)

    create.alters_data = True

    def update(self, **kwargs):
        raise AuditoriaImutavel("Eventos de auditoria não podem ser alterados.")

    update.alters_data = True

    def delete(self):
        raise AuditoriaImutavel("Eventos de auditoria não podem ser excluídos.")

    delete.alters_data = True


class GerenciadorEvento(models.Manager.from_queryset(EventoAuditoriaQuerySet)):
    """Nos proxies, restringe ao próprio tipo (coluna `tipo`)."""

    def get_queryset(self):
        consulta = super().get_queryset()
        if self.model is not EventoAuditoria:
            consulta = consulta.filter(tipo=self.model.__name__)
        return consulta


class EventoAuditoria(models.Model):
    """Evento imutável: quem fez, quando, antes/depois. Não usar como cadastro editável."""

    tipo = models.CharField(max_length=50)
    alvo_id = models.PositiveBigIntegerField()
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="eventos_auditoria")
    registrado_em = models.DateTimeField(default=timezone.now, editable=False)
    anteriores = models.JSONField(null=True)
    novos = models.JSONField()
    acao = models.CharField(max_length=40, blank=True, default="")
    # PK do registro na tabela de origem antes da unificação (0013 de atividades); nulo nos eventos novos.
    origem_id = models.PositiveBigIntegerField(null=True, editable=False)

    objects = GerenciadorEvento()

    # Nos proxies: nome do alvo (ex. "atividade") e modelo (classe ou "app_label.Modelo").
    alvo = None
    modelo_alvo = None

    class Meta:
        default_permissions = ()
        ordering = ["registrado_em", "pk"]
        verbose_name = "evento de auditoria"
        verbose_name_plural = "eventos de auditoria"
        indexes = [
            models.Index(fields=["tipo", "alvo_id", "registrado_em"], name="core_evento_alvo_idx"),
            models.Index(fields=["tipo", "registrado_em"], name="core_evento_tipo_data_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["alvo_id"], condition=models.Q(tipo=tipo), name=nome)
            for tipo, nome in TIPOS_UNICOS_POR_ALVO.items()
        ]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        alvo = cls.__dict__.get("alvo")
        if not alvo:
            return
        TIPOS_AUDITORIA[cls.__name__] = cls

        def obter(self):
            cache = self.__dict__.setdefault("_alvo_cache", {})
            if cache.get("pk") != self.alvo_id:
                modelo = type(self).modelo_alvo_resolvido()
                cache.update(pk=self.alvo_id, objeto=modelo._base_manager.get(pk=self.alvo_id))
            return cache["objeto"]

        def definir(self, objeto):
            self.alvo_id = objeto.pk
            self.__dict__["_alvo_cache"] = {"pk": objeto.pk, "objeto": objeto}

        setattr(cls, alvo, property(obter, definir))
        setattr(cls, alvo + "_id", property(lambda self: self.alvo_id))

    @classmethod
    def modelo_alvo_resolvido(cls):
        modelo = cls.modelo_alvo
        return apps.get_model(modelo) if isinstance(modelo, str) else modelo

    @classmethod
    def traduzir_filtros(cls, kwargs):
        """`atividade=obj`, `atividade_id__in=[...]`, `atividade__nome=` -> lookups sobre alvo_id."""
        traduzidos = {}
        for chave, valor in kwargs.items():
            base, _, resto = chave.partition("__")
            if base not in (cls.alvo, cls.alvo + "_id"):
                traduzidos[chave] = valor
            elif not resto or resto in _LOOKUPS_ID:
                if resto in ("in", "range"):
                    valor = [_pk(item) for item in valor] if not isinstance(valor, models.QuerySet) else valor
                traduzidos["alvo_id" + ("__" + resto if resto else "")] = _pk(valor)
            else:
                consulta = cls.modelo_alvo_resolvido()._base_manager.filter(**{resto: valor}).values("pk")
                traduzidos["alvo_id__in"] = consulta
        return traduzidos

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AuditoriaImutavel("Eventos de auditoria não podem ser alterados.")
        if type(self) is not EventoAuditoria:
            self.tipo = type(self).__name__
        if self.tipo not in TIPOS_AUDITORIA:
            raise IntegrityError(f"Tipo de evento de auditoria desconhecido: {self.tipo!r}.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditoriaImutavel("Eventos de auditoria não podem ser excluídos.")

    @property
    def objeto_alvo(self):
        proxy = TIPOS_AUDITORIA.get(self.tipo)
        return proxy.modelo_alvo_resolvido()._base_manager.filter(pk=self.alvo_id).first() if proxy else None

    # Nomes legados usados pelos serviços e testes de atividades.
    dados = property(lambda self: self.novos)
    dados_novos = property(lambda self: self.novos)
    dados_anteriores = property(lambda self: self.anteriores)

    def __str__(self):
        return f"{self.tipo} #{self.alvo_id} em {self.registrado_em:%d/%m/%Y %H:%M}"
