import multiprocessing

# ── Binding ───────────────────────────────────────────────────────────────────
# Servidor compartilhado com outros apps -- 8000/8001/8010/8080 já estavam
# ocupados por outros serviços quando isso foi checado (2026-08-20).
bind = "127.0.0.1:8020"

# ── Workers ───────────────────────────────────────────────────────────────────
# Fórmula recomendada pelo Gunicorn: (2 × CPUs) + 1
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
threads = 1
timeout = 30
keepalive = 5

# Reinicia workers após N requisições para evitar memory leaks
max_requests = 1000
max_requests_jitter = 100

# Carrega o app antes de forkar (economiza memória via copy-on-write)
preload_app = True

# ── Logs ──────────────────────────────────────────────────────────────────────
accesslog = "/var/www/barberhub/logs/gunicorn-access.log"
errorlog  = "/var/www/barberhub/logs/gunicorn-error.log"
loglevel  = "warning"
capture_output = True
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" %(D)sµs'

# ── Processo ──────────────────────────────────────────────────────────────────
proc_name = "barberhub"
pidfile   = "/var/www/barberhub/barberhub.pid"
