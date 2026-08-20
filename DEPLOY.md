# Prospect BarberHub — Guia de Deploy em Produção

Stack de produção: **Ubuntu 22.04 LTS · Python 3.12 · Gunicorn · Nginx · SQLite (ou PostgreSQL)**

---

## Índice

1. [Pré-requisitos](#1-pré-requisitos)
2. [Preparar o servidor](#2-preparar-o-servidor)
3. [Instalar o projeto](#3-instalar-o-projeto)
4. [Configurar variáveis de ambiente](#4-configurar-variáveis-de-ambiente)
5. [Inicializar o banco de dados](#5-inicializar-o-banco-de-dados)
6. [Configurar o Gunicorn (systemd)](#6-configurar-o-gunicorn-systemd)
7. [Configurar o Nginx](#7-configurar-o-nginx)
8. [SSL com Let's Encrypt](#8-ssl-com-lets-encrypt)
9. [Job diário de downgrade por inadimplência (cron)](#9-job-diário-de-downgrade-por-inadimplência-cron)
10. [Atualizar a aplicação (deploy)](#10-atualizar-a-aplicação-deploy)
11. [Logs e monitoramento](#11-logs-e-monitoramento)
12. [Migração para PostgreSQL](#12-migração-para-postgresql)
13. [Estrutura de arquivos no servidor](#13-estrutura-de-arquivos-no-servidor)

---

## 1. Pré-requisitos

- VPS Ubuntu 22.04 LTS (1 GB RAM mínimo)
- Domínio apontando para o IP do servidor (para SSL)
- Acesso SSH como root ou usuário com sudo
- Repositório Git com o código da aplicação

---

## 2. Preparar o servidor

```bash
# Atualizar pacotes
sudo apt update && sudo apt upgrade -y

# Instalar dependências de sistema
sudo apt install -y python3.12 python3.12-venv python3-pip \
                    nginx git curl ufw

# Firewall: permitir SSH, HTTP e HTTPS
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable

# Criar usuário dedicado para a aplicação (sem shell de login)
sudo useradd --system --no-create-home --shell /usr/sbin/nologin barberhub

# Criar diretório da aplicação com as permissões corretas
sudo mkdir -p /var/www/barberhub
sudo chown barberhub:www-data /var/www/barberhub
sudo chmod 750 /var/www/barberhub
```

---

## 3. Instalar o projeto

```bash
# Clonar o repositório como usuário barberhub
sudo -u barberhub git clone https://github.com/SEU_USUARIO/barber_prospect.git \
     /var/www/barberhub

cd /var/www/barberhub

# Criar o ambiente virtual
sudo -u barberhub python3.12 -m venv venv

# Instalar dependências (incluindo Gunicorn)
sudo -u barberhub venv/bin/pip install --upgrade pip
sudo -u barberhub venv/bin/pip install -r requirements.txt

# Criar diretório de logs
sudo mkdir -p /var/www/barberhub/logs
sudo chown barberhub:www-data /var/www/barberhub/logs

# Garantir permissão de escrita nos uploads
sudo chown -R barberhub:www-data /var/www/barberhub/app/static/uploads
sudo chmod -R 775 /var/www/barberhub/app/static/uploads
```

---

## 4. Configurar variáveis de ambiente

```bash
# Copiar o template e editar
sudo -u barberhub cp /var/www/barberhub/.env.example /var/www/barberhub/.env
sudo nano /var/www/barberhub/.env
```

Preencha obrigatoriamente:

```dotenv
FLASK_CONFIG=production

# Gere com: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=cole_aqui_a_chave_gerada

# Caminho absoluto para o SQLite no servidor
DATABASE_URL=sqlite:////var/www/barberhub/database.db
```

Restrinja o acesso ao arquivo:

```bash
sudo chmod 640 /var/www/barberhub/.env
sudo chown barberhub:barberhub /var/www/barberhub/.env
```

---

## 5. Inicializar o banco de dados

```bash
cd /var/www/barberhub

# Aplica todas as migrações Alembic (cria o schema do zero em um banco novo,
# ou traz um banco existente até a revisão mais recente — idempotente)
sudo -u barberhub FLASK_CONFIG=production venv/bin/flask --app wsgi db upgrade
```

> Não há mais comando de seed automático (era da era pré-multi-tenant). O
> primeiro acesso é pela tela de cadastro de empresa (`/auth/signup` ou
> equivalente) — crie o usuário dono real ali, não há admin/senha padrão
> pra trocar.

---

## 6. Configurar o Gunicorn (systemd)

```bash
# Copiar o arquivo de serviço
sudo cp /var/www/barberhub/deploy/barberhub.service \
        /etc/systemd/system/barberhub.service

# Recarregar o systemd, ativar e iniciar o serviço
sudo systemctl daemon-reload
sudo systemctl enable barberhub
sudo systemctl start barberhub

# Verificar status
sudo systemctl status barberhub
```

O Gunicorn escuta na porta definida em `bind` no `gunicorn.conf.py` (padrão `127.0.0.1:8020` — em servidor compartilhado com outros apps, confira com `sudo ss -tln` se a porta escolhida está livre antes de subir o serviço). Nunca exponha essa porta diretamente — o Nginx faz o proxy.

**Comandos úteis:**

| Ação | Comando |
|------|---------|
| Iniciar | `sudo systemctl start barberhub` |
| Parar | `sudo systemctl stop barberhub` |
| Reiniciar (aplica código/`.env` novos) | `sudo systemctl restart barberhub` |
| Ver logs em tempo real | `sudo journalctl -u barberhub -f` |

> **`reload` não serve pra atualizar código nem `.env` neste projeto.**
> Com `preload_app=True` (`gunicorn.conf.py`), o app é importado uma vez
> no processo master e os workers nascem a partir dessa cópia em memória
> — um `reload` (SIGHUP) só recicla os workers usando essa mesma cópia
> antiga, nunca reimporta o código do disco. `EnvironmentFile=` do
> systemd também só é lido quando o processo nasce, não num reload.
> **Sempre use `restart`** pra qualquer mudança de código ou variável de
> ambiente — confirmado na prática em 2026-08-20 (um `reload` depois de
> um `git pull` manteve a rota antiga no ar, gerando 404 na rota nova).

---

## 7. Configurar o Nginx

```bash
# Copiar a configuração (edite o domínio antes!)
sudo cp /var/www/barberhub/deploy/nginx.conf \
        /etc/nginx/sites-available/barberhub

# Editar e substituir "seudominio.com.br" pelo domínio real
sudo nano /etc/nginx/sites-available/barberhub

# Ativar o site
sudo ln -s /etc/nginx/sites-available/barberhub \
           /etc/nginx/sites-enabled/barberhub

# Remover o site default (opcional, se for o único site)
sudo rm -f /etc/nginx/sites-enabled/default

# Testar e recarregar
sudo nginx -t
sudo systemctl reload nginx
```

> Neste momento a aplicação já estará acessível em `http://seudominio.com.br` via HTTP. O bloco SSL só funciona após instalar o certificado (passo 8).

---

## 8. SSL com Let's Encrypt

```bash
# Instalar o Certbot
sudo apt install -y certbot python3-certbot-nginx

# Obter e instalar o certificado (substitua pelo domínio real)
sudo certbot --nginx -d seudominio.com.br -d www.seudominio.com.br

# O Certbot atualiza automaticamente a configuração do Nginx.
# Verifique a renovação automática:
sudo systemctl status certbot.timer
```

O certificado é renovado automaticamente antes de expirar (90 dias).

---

## 9. Job diário de downgrade por inadimplência (cron)

Empresa com assinatura inadimplente há >= 8 dias é rebaixada pro plano
Free automaticamente (ver `app/billing/service.py:downgrade_inadimplentes()`).
Esse job **não** roda dentro do processo do Gunicorn — sob
`preload_app=True` com múltiplos workers (padrão deste projeto, ver
`gunicorn.conf.py`), uma thread de scheduler iniciada no processo master
não sobrevive ao `fork()` de forma confiável nos workers filhos
(confirmado como cenário real, não hipotético, no deploy de 2026-08-20).
Por isso o job é um endpoint HTTP interno chamado por `cron` do próprio
SO, fora do processo da aplicação inteiramente — funciona igual não
importa a topologia (1 worker, N workers, Passenger no Hostinger).

```bash
# Gere um token e salve em INTERNAL_JOB_TOKEN no .env (ver passo 4)
python3 -c "import secrets; print(secrets.token_hex(32))"
sudo nano /var/www/barberhub/.env   # adicione a linha INTERNAL_JOB_TOKEN=...

# IMPORTANTE: reload (SIGHUP) NÃO recarrega variáveis de ambiente novas --
# o systemd só lê EnvironmentFile= quando o processo é (re)iniciado do
# zero, não num reload graceful. Precisa ser restart:
sudo systemctl restart barberhub

# Registre o cron (roda todo dia às 3h da manhã)
sudo -u barberhub crontab -e
```

Adicione a linha (substitua `SEU_TOKEN_AQUI` pelo mesmo valor de
`INTERNAL_JOB_TOKEN` no `.env`):

```cron
0 3 * * * curl -sS -X POST -H "X-Internal-Token: SEU_TOKEN_AQUI" https://seudominio.com.br/internal/downgrade-inadimplentes >> /var/www/barberhub/logs/downgrade-cron.log 2>&1
```

Teste manualmente antes de confiar no agendamento:

```bash
curl -sS -X POST -H "X-Internal-Token: SEU_TOKEN_AQUI" https://seudominio.com.br/internal/downgrade-inadimplentes
# Resposta esperada: {"rebaixadas": 0}  (ou > 0 se havia empresa pra rebaixar)
```

---

## 10. Atualizar a aplicação (deploy)

Para atualizar o código após um `git push`:

```bash
# Opção 1: script automatizado
sudo -u barberhub bash /var/www/barberhub/deploy/deploy.sh

# Opção 2: passo a passo manual
cd /var/www/barberhub
sudo -u barberhub git pull --ff-only
sudo -u barberhub venv/bin/pip install -r requirements.txt -q
sudo systemctl restart barberhub
```

`restart`, não `reload` — com `preload_app=True` (padrão deste projeto),
`reload` (SIGHUP) recicla os workers usando a cópia do código já
carregada em memória no processo master, sem reimportar nada do disco.
Só `restart` reinicia o master e força a reimportação. Custa um breve
downtime (segundos) em vez de zero-downtime, mas é o único jeito
confiável de garantir que o código novo está de fato no ar — confirmado
na prática em 2026-08-20 (ver seção 6).

---

## 11. Logs e monitoramento

| Log | Localização |
|-----|-------------|
| App (Flask) | `/var/www/barberhub/logs/barberhub.log` |
| Gunicorn requests | `/var/www/barberhub/logs/gunicorn-access.log` |
| Gunicorn erros | `/var/www/barberhub/logs/gunicorn-error.log` |
| Nginx access | `/var/log/nginx/barberhub-access.log` |
| Nginx erros | `/var/log/nginx/barberhub-error.log` |
| systemd (Gunicorn) | `journalctl -u barberhub` |

```bash
# Acompanhar erros da aplicação em tempo real
tail -f /var/www/barberhub/logs/barberhub.log

# Ver últimas 50 linhas do log do Gunicorn
tail -50 /var/www/barberhub/logs/gunicorn-error.log

# Verificar memória e CPU dos workers
ps aux | grep gunicorn
```

---

## 12. Migração para PostgreSQL

Quando precisar escalar para PostgreSQL:

```bash
# 1. Instalar PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# 2. Criar banco e usuário
sudo -u postgres psql -c "CREATE USER barberhub WITH PASSWORD 'senha_forte';"
sudo -u postgres psql -c "CREATE DATABASE barberhub OWNER barberhub;"

# 3. Instalar driver Python
sudo -u barberhub venv/bin/pip install psycopg2-binary

# 4. Atualizar requirements.txt (descomentar a linha psycopg2-binary)

# 5. Atualizar .env
# DATABASE_URL=postgresql://barberhub:senha_forte@localhost:5432/barberhub

# 6. Recriar tabelas no PostgreSQL
sudo -u barberhub FLASK_CONFIG=production venv/bin/flask --app wsgi db upgrade

# 7. (Opcional) Migrar dados do SQLite
#    Use a ferramenta pgloader ou exporte/importe manualmente
sudo apt install -y pgloader
pgloader sqlite:///var/www/barberhub/database.db \
         postgresql://barberhub:senha@localhost/barberhub

# 8. Reiniciar a aplicação
sudo systemctl restart barberhub
```

> O código da aplicação não precisa de nenhuma alteração — apenas o `DATABASE_URL` muda.

---

## 13. Estrutura de arquivos no servidor

```
/var/www/barberhub/
├── app/
│   ├── models/
│   ├── static/
│   │   ├── css/
│   │   ├── js/
│   │   └── uploads/          ← arquivos enviados pelos usuários
│   └── templates/
├── deploy/
│   ├── barberhub.service     ← copiado para /etc/systemd/system/
│   ├── nginx.conf            ← copiado para /etc/nginx/sites-available/
│   └── deploy.sh             ← script de atualização
├── logs/
│   ├── barberhub.log         ← erros da aplicação Flask
│   ├── gunicorn-access.log
│   └── gunicorn-error.log
├── venv/                     ← ambiente virtual Python
├── .env                      ← variáveis secretas (não versionado)
├── gunicorn.conf.py          ← configuração do servidor WSGI
├── requirements.txt
└── wsgi.py                   ← entry point de produção
```

---

## Checklist de go-live

- [ ] `SECRET_KEY` gerada e salva no `.env`
- [ ] Cadastro da primeira empresa/dono feito pela tela de signup (sem seed/senha padrão)
- [ ] SSL instalado e redirecionamento HTTP → HTTPS ativo
- [ ] `sudo systemctl status barberhub` → `active (running)`
- [ ] `sudo nginx -t` → `syntax is ok`
- [ ] Acesso ao sistema pelo domínio funcionando
- [ ] Upload de foto de barbeiro testado
- [ ] Geração de relatório Excel testada
- [ ] Log de erros limpo: `tail -20 logs/barberhub.log`
- [ ] `INTERNAL_JOB_TOKEN` gerado, salvo no `.env` e no crontab (passo 9) — teste manual do `curl` retornou `{"rebaixadas": ...}`
