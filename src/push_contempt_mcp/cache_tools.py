"""Invalidazione della cache OpenLiteSpeed per l'ambiente di sviluppo locale (ols-docker-env).

Due livelli di cache separati, entrambi devono essere invalidati:
1. Object cache (Redis, dietro il drop-in object-cache.php di LiteSpeed):
   cache dei dati letti da WordPress (post, meta...). Una scrittura diretta
   sul DB non passa da nessun hook che la invaliderebbe.
2. Page cache (LSCache, file su disco nel container): cache dell'HTML
   gia' renderizzato. Il purge "normale" (hook litespeed_purge_all, un
   semplice docker restart) non basta, serve cancellare la cache su disco
   E riavviare il container (vedi project_wp_cache_gotcha).

L'ORDINE CONTA: va svuotato prima Redis e poi la page cache, non il
contrario. Se si svuota prima la page cache, qualunque richiesta che la
ripopola nel frattempo (un crawler di pre-warm, una visita reale) legge
ancora dall'object cache vecchio e ci scrive dentro dati stale - esattamente
il bug osservato svuotando le due cache nell'ordine sbagliato.

Va chiamata da ogni tool che scrive qualcosa visibile sul frontend (prezzo,
descrizione, SEO) invece di restare una nota manuale da ricordarsi.

Specifico di questo ambiente dev (ols-docker-env): un'installazione sul
hosting di un cliente probabilmente non ha questi container né questa
cache - in quel caso purga_cache() fallisce in modo silenzioso (vedi sotto)
e andra' ripensata una procedura adatta a quell'hosting.
"""

import logging
import os
import subprocess

logger = logging.getLogger(__name__)

CONTAINER_LITESPEED = os.environ.get("LITESPEED_CONTAINER", "litespeed")
CONTAINER_REDIS = os.environ.get("REDIS_CONTAINER", "ols-docker-env-redis-1")
CACHEDATA_PATH = "/usr/local/lsws/cachedata"


def purga_cache() -> dict:
    """Svuota prima l'object cache (Redis), poi la page cache (LSCache su
    disco + restart del container) - l'ordine e' importante, vedi il
    docstring del modulo.

    Non lancia eccezioni: la scrittura nel DB/wp-admin che ha richiesto la
    purge e' comunque andata a buon fine anche se questa fallisce (container
    non trovato, docker non raggiungibile, ...) - un fallimento qui non deve
    far sembrare fallita l'operazione principale, risulta solo in
    `cache_purgata: false`.
    """
    try:
        subprocess.run(
            ["docker", "exec", CONTAINER_REDIS, "redis-cli", "FLUSHALL"],
            check=True,
            capture_output=True,
            timeout=30,
        )
        subprocess.run(
            ["docker", "exec", CONTAINER_LITESPEED, "sh", "-c", f"rm -rf {CACHEDATA_PATH}/*"],
            check=True,
            capture_output=True,
            timeout=30,
        )
        subprocess.run(
            ["docker", "restart", CONTAINER_LITESPEED],
            check=True,
            capture_output=True,
            timeout=60,
        )
        return {"cache_purgata": True}
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("Purge cache fallita: %s", e)
        return {"cache_purgata": False, "errore_cache": str(e)}
