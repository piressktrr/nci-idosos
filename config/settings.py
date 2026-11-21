"""
Configurações do sistema NCI Idade Dourada (cadastro de participantes e atividades).

Valores sensíveis ou que mudam entre ambientes vêm do arquivo .env (modelo em
.env.example). Com DJANGO_DEBUG=True o comportamento é o de desenvolvimento; com
DJANGO_DEBUG=False valem as proteções de produção (HTTPS, cookies seguros, HSTS).

Referência: https://docs.djangoproject.com/en/6.1/ref/settings/
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from config.banco import banco_de_url, banco_local

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


def env_list(nome, padrao=''):
    """Lê uma variável de ambiente separada por vírgulas como lista, ignorando itens vazios."""
    return [item.strip() for item in os.getenv(nome, padrao).split(',') if item.strip()]


def env_bool(nome, padrao='False'):
    return os.getenv(nome, padrao).lower() == 'true'


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ['DJANGO_SECRET_KEY']

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env_bool('DJANGO_DEBUG')

ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')

# Origens com esquema, ex.: https://nci.exemplo.org.br. Necessário em produção atrás de HTTPS/proxy.
CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS')

# Render: o endereço público (ex.: nci-idosos.onrender.com) chega nesta variável, definida pelo próprio Render.
# Assim não é preciso repetir o domínio nas variáveis acima.
_HOST_RENDER = os.getenv('RENDER_EXTERNAL_HOSTNAME')
if _HOST_RENDER:
    ALLOWED_HOSTS.append(_HOST_RENDER)
    CSRF_TRUSTED_ORIGINS.append(f'https://{_HOST_RENDER}')

# E-mails que recebem os avisos de erro 500 quando DEBUG=False. Formato: ti@exemplo.org,outro@exemplo.org.
ADMINS = env_list('DJANGO_ADMINS')


# Application definition

INSTALLED_APPS = [
    'core.apps.CoreConfig',
    'atividades.apps.AtividadesConfig',
    'participantes.apps.ParticipantesConfig',
    'usuarios.apps.UsuariosConfig',
    'relatorios.apps.RelatoriosConfig',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

# Decisão atual: usar o usuário padrão do Django, sem modelo customizado.
AUTH_USER_MODEL = 'auth.User'
LOGIN_URL = 'entrar'
LOGIN_REDIRECT_URL = 'inicio'
LOGOUT_REDIRECT_URL = 'entrar'

# Sessão curta: computadores do NCI podem ser compartilhados (dados pessoais de idosos, LGPD).
SESSION_COOKIE_AGE = int(os.getenv('DJANGO_SESSION_COOKIE_AGE', str(8 * 60 * 60)))  # padrão: 8 horas
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# Cadastro real de participantes usado por inscrição e chamada de atividades.
NCI_PARTICIPANTES_PROVIDER = 'participantes.provedor.ProvedorParticipantes'
# RF-PAR-10: frequência do participante no detalhe, lida de atividades sem participantes importá-lo (vazio = sem cartão).
NCI_CONSULTA_FREQUENCIA_PARTICIPANTE = 'atividades.consultas_participante.frequencia_do_participante'
NCI_AJUSTE_AFASTAMENTO = 'atividades.ajustes_afastamento.atualizar_ausencias'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Serve os arquivos de static/ (CSS, JS, fontes) pelo próprio Django, comprimidos e com cache longo.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'relatorios.context_processors.acesso_fmr',
                'core.context_processors.perfil',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

# Hospedagem: DATABASE_URL (Render, Neon...). Local: POSTGRES_* do .env (docker-compose).
DATABASES = {
    'default': (
        banco_de_url(os.environ['DATABASE_URL'], conn_max_age=int(os.getenv('DJANGO_DB_CONN_MAX_AGE', '0')))
        if os.getenv('DATABASE_URL') else banco_local(os.environ)
    )
}


# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 10},
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = 'pt-br'

TIME_ZONE = 'America/Sao_Paulo'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
# Destino do collectstatic em produção (não versionado).
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Em produção, o collectstatic gera cópias comprimidas e com hash no nome (cache longo no navegador).
# Fica desligado por padrão porque exige rodar collectstatic antes (os testes e o runserver local não rodam).
if env_bool('DJANGO_STATIC_MANIFEST'):
    STORAGES = {
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
    }

# RNF-SEG-06: com DEBUG desligado (produção), tráfego só por HTTPS e cookies seguros.
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Comece baixo e suba aos poucos (ex.: 1 dia, 1 semana, 1 ano = 31536000) depois de confirmar
    # que o HTTPS funciona bem: o navegador passa a recusar HTTP pelo tempo definido.
    SECURE_HSTS_SECONDS = int(os.getenv('DJANGO_SECURE_HSTS_SECONDS', '3600'))
    # Decisão explícita: não incluir subdomínios nem pedir preload. O domínio final ainda não está
    # definido e esses dois são difíceis de desfazer (afetam outros serviços do domínio/lista dos navegadores).
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'

# Atrás de um proxy reverso que termina o HTTPS (nginx, Caddy...), defina
# DJANGO_SECURE_PROXY_SSL_HEADER=HTTP_X_FORWARDED_PROTO. Só use se o proxy sempre sobrescrever esse
# cabeçalho; sem proxy, deixe vazio.
if os.getenv('DJANGO_SECURE_PROXY_SSL_HEADER'):
    SECURE_PROXY_SSL_HEADER = (os.environ['DJANGO_SECURE_PROXY_SSL_HEADER'], 'https')


# Email
# https://docs.djangoproject.com/en/6.1/topics/email/#topic-email-configuration

# Em desenvolvimento o padrão é imprimir os e-mails no console; fora dele, SMTP com os dados do .env.
_email_backend_padrao = (
    'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend'
)
MAILERS = {
    'default': {
        'BACKEND': os.getenv('DJANGO_EMAIL_BACKEND', _email_backend_padrao),
    },
}
if MAILERS['default']['BACKEND'] == 'django.core.mail.backends.smtp.EmailBackend':
    MAILERS['default']['OPTIONS'] = {
        'host': os.getenv('DJANGO_EMAIL_HOST', 'localhost'),
        'port': int(os.getenv('DJANGO_EMAIL_PORT', '587')),
        'username': os.getenv('DJANGO_EMAIL_HOST_USER', ''),
        'password': os.getenv('DJANGO_EMAIL_HOST_PASSWORD', ''),
        'use_tls': env_bool('DJANGO_EMAIL_USE_TLS', 'True'),
        # Sem timeout, um SMTP pendurado prende o processo a cada pedido de "esqueci minha senha".
        'timeout': int(os.getenv('DJANGO_EMAIL_TIMEOUT', '10')),
    }
DEFAULT_FROM_EMAIL = os.getenv('DJANGO_DEFAULT_FROM_EMAIL', 'webmaster@localhost')
# RF-USR-05: o link de "esqueci minha senha" vale 2 horas (o padrão do Django é 3 dias).
PASSWORD_RESET_TIMEOUT = int(os.getenv('DJANGO_PASSWORD_RESET_TIMEOUT', str(2 * 60 * 60)))
SERVER_EMAIL = os.getenv('DJANGO_SERVER_EMAIL', DEFAULT_FROM_EMAIL)


# Logging
# https://docs.djangoproject.com/en/6.1/topics/logging/
# Mínimo: erros de requisição e de segurança (CSRF, host inválido etc.) vão para o console,
# onde o servidor de aplicação/serviço do sistema os coleta. Com DEBUG=False, erros também
# são enviados por e-mail aos ADMINS.

# RNF-SEG-05/LGPD: relatórios de erro (e-mail aos ADMINS) sem campos de formulário, cookies nem senhas.
DEFAULT_EXCEPTION_REPORTER_FILTER = 'core.relatorio_erros.FiltroRelatorioErros'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simples': {
            'format': '{asctime} {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simples',
        },
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler',
        },
    },
    'loggers': {
        'django.request': {
            'handlers': ['console', 'mail_admins'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console', 'mail_admins'],
            'level': 'WARNING',
            'propagate': False,
        },
        # Falhas de envio do "esqueci minha senha" (o Django as registra aqui e segue sem erro na tela).
        'django.contrib.auth': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}
