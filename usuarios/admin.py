"""Admin do Django para contas: sem exclusão, nem para superusuário.

Contas não são excluídas (o histórico das ações precisa ser preservado; a desativação é o RF-USR-04, pendente).
Contas com eventos de auditoria também são barradas pelo pre_delete do core (RegistroConta).
"""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin


class ContaAdmin(UserAdmin):
    def has_delete_permission(self, request, obj=None):
        return False


Usuario = get_user_model()
# Importar django.contrib.auth.admin (acima) já registra o UserAdmin padrão; aqui ele é substituído.
if admin.site.is_registered(Usuario):
    admin.site.unregister(Usuario)
admin.site.register(Usuario, ContaAdmin)
