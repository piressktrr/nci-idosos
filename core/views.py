from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def inicio(request):
    """Boas-vindas do protótipo: um cartão por módulo, só os que o usuário pode acessar."""
    return render(request, "nci/inicio.html")
