"""Acesso às telas de colaboradores (RN-USR-01); reaproveita o critério de `core.decorators`."""

from core.decorators import exige_administrador

administrador_required = exige_administrador("Somente administradores podem gerenciar contas de acesso.")
