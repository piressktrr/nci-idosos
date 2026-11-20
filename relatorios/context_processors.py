from django.utils.functional import SimpleLazyObject

from .permissoes import pode_consultar_fmr


def acesso_fmr(request):
    return {"pode_consultar_fmr": SimpleLazyObject(lambda: pode_consultar_fmr(request.user))}
