"""Contas e grupos fora do admin do Django (RNF-SEG-07, RF-USR-03).

Contas só são criadas e alteradas pelas telas próprias (`/colaboradores/`), cujos serviços gravam cada mudança
junto com o seu evento `usuarios.RegistroConta`. Pelo admin do Django as alterações ficariam só no LogEntry,
fora da auditoria comum; por isso `auth.User` e `auth.Group` são retirados dele. Exclusão de contas continua
barrada pelo pre_delete do core para contas com eventos de auditoria.
"""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

# Importar django.contrib.auth.admin registra User e Group; aqui os dois são retirados do site.
import django.contrib.auth.admin  # noqa: F401  (garante o registro antes de retirar, qualquer que seja a ordem)

for modelo in (get_user_model(), Group):
    if admin.site.is_registered(modelo):
        admin.site.unregister(modelo)
