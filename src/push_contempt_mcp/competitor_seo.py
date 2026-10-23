"""Analisi SEO "a campione" del sito di un altro negozio, per prendere spunto da
come e' fatto: struttura dei titoli, parole usate, modo di descrivere i
prodotti, intenzione, dati strutturati.

Gira sulla macchina dell'utente, non sul sito WordPress (l'hosting spesso
blocca le richieste in uscita, vedi Altervista), e senza AI: scarica poche
pagine, ne estrae i campi SEO e il testo con codice normale e restituisce un
report compatto. Chi lo chiama (l'assistente AI) legge solo il riassunto, quindi
il costo in token non dipende da quante pagine vengono scaricate ma da quanto
testo di esempio si chiede (`caratteri_per_pagina`).

Scelte di progetto:
- Campione fisso e piccolo (home, sitemap, qualche categoria, una decina di
  prodotti); i limiti sono parametri, con un tetto massimo.
- Rispetta robots.txt (compreso Crawl-delay), si presenta con uno User-Agent
  riconoscibile, fa una pausa fra una richiesta e l'altra e non esce dal
  dominio indicato.
- Il testo conta: oltre ai campi SEO il report ha vocabolario (parole e coppie
  di parole ricorrenti), segnali di stile e intenzione e un breve estratto
  della descrizione di ogni pagina, perche' l'assistente giudichi tono e modo
  di descrivere i prodotti (vedi competitor_text.py). Le formule che si
  ripetono su meta' delle pagine (template del sito) sono separate dai
  contenuti. Gli estratti servono ad analizzare, non a riusare: i testi nostri
  vanno scritti con parole proprie.
- Rifiuta indirizzi di reti private (localhost, 192.168.x.x, ...) per non
  usare lo strumento contro risorse interne; per provarlo su un sito locale
  impostare SEO_ANALISI_CONSENTI_RETE_PRIVATA=1.
"""

import html
import ipaddress
import json
import os
import re
import socket
import subprocess
import time
from collections import Counter
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests

from push_contempt_mcp import competitor_text, seo_scorecard, text_similarity

USER_AGENT_TOKEN = "push_contempt_mcp-seo"
USER_AGENT = f"{USER_AGENT_TOKEN}/0.1 (+https://github.com/ness1-contempt/push_contempt_mcp)"

PAUSA_SECONDI = 1.0
PAUSA_MASSIMA_SECONDI = 10.0
TIMEOUT_SECONDI = 10
MAX_BYTE = 1_500_000
# Le sitemap sono molto piu' grandi delle pagine (il protocollo ammette 50 MB per file):
# con il tetto delle pagine se ne leggerebbe solo l'inizio, e il campione sarebbe
# sbilanciato verso i primi gruppi dell'elenco.
MAX_BYTE_SITEMAP = 50_000_000
MAX_REDIRECT = 3
MAX_SITEMAP_FIGLIE = 2
RETRY_AFTER_MASSIMO_SECONDI = 120

MAX_CATEGORIE_DEFAULT = 3
MAX_PRODOTTI_DEFAULT = 10
TETTO_CATEGORIE = 10
TETTO_PRODOTTI = 30
CARATTERI_DEFAULT = 600
TETTO_CARATTERI = 2000

_SEPARATORI_TITOLO = (" | ", " - ", " – ", " — ", " • ", " · ")
_FRAGMENT_CATEGORIA = (
    "/product-category/",
    "/categoria-prodotto/",
    "/categoria/",
    "/category/",
    "/l/",  # pagine di elenco (es. /it-it/l/smartphone/...)
)
_FRAGMENT_COLLEZIONE = ("/collections/", "/collection/")
_FRAGMENT_PRODOTTO = ("/product/", "/products/", "/prodotto/", "/prodotti/", "/p/")


class ErroreAnalisi(Exception):
    """Errore atteso (rete, robots.txt, URL non valido): finisce nel report."""


class SitoBloccato(ErroreAnalisi):
    """La home risponde 403/429: il sito non accetta questo tipo di richieste. Chi
    chiama puo' ritentare con un altro metodo (browser)."""

    def __init__(self, messaggio: str, retry_after: float | None = None):
        super().__init__(messaggio)
        self.retry_after = retry_after


class _Risposta:
    def __init__(self, status: int, url: str, testo: str, retry_after: float | None = None):
        self.status = status
        self.url = url
        self.testo = testo
        self.retry_after = retry_after  # secondi, dall'intestazione Retry-After


# --- rete -------------------------------------------------------------------


def _host_base(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.")


def _normalizza_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise ErroreAnalisi("URL vuoto")
    if "://" not in url:
        url = f"https://{url}"
    parti = urlsplit(url)
    if parti.scheme not in ("http", "https") or not parti.hostname:
        raise ErroreAnalisi(f"URL non valido: {url} (servono http:// o https://)")
    return url if parti.path else urlunsplit(parti._replace(path="/"))


def _risolvi(host: str) -> list[str]:
    try:
        return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})
    except socket.gaierror as errore:
        raise ErroreAnalisi(f"Dominio non raggiungibile: {host} ({errore})") from errore


def _controlla_destinazione(url: str) -> None:
    if os.environ.get("SEO_ANALISI_CONSENTI_RETE_PRIVATA") == "1":
        return
    host = urlsplit(url).hostname or ""
    for indirizzo in _risolvi(host):
        if not ipaddress.ip_address(indirizzo.split("%")[0]).is_global:
            raise ErroreAnalisi(
                f"{host} punta a una rete privata o locale ({indirizzo}): "
                "per sicurezza l'analisi e' solo per siti pubblici."
            )


def _limite_byte(url: str) -> int:
    """Tetto alla dimensione della risposta: piu' alto per sitemap e robots.txt."""
    percorso = urlsplit(url).path.lower()
    return MAX_BYTE_SITEMAP if "sitemap" in percorso or percorso.endswith(".xml") else MAX_BYTE


def _decodifica(dati: bytes, codifica: str | None) -> str:
    try:
        return dati.decode(codifica or "utf-8", errors="replace")
    except LookupError:
        return dati.decode("utf-8", errors="replace")


_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5"


def _richiesta_requests(url: str) -> tuple[int, dict[str, str], bytes, str | None]:
    """Una GET senza seguire i redirect: (status, intestazioni in minuscolo,
    corpo fino a MAX_BYTE, codifica dichiarata)."""
    try:
        risposta = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": _ACCEPT},
            timeout=TIMEOUT_SECONDI,
            allow_redirects=False,
            stream=True,
        )
    except requests.RequestException as errore:
        raise ErroreAnalisi(f"{url}: {errore.__class__.__name__}") from errore
    try:
        limite = _limite_byte(url)
        pezzi: list[bytes] = []
        letti = 0
        for blocco in risposta.iter_content(262144):
            pezzi.append(blocco)
            letti += len(blocco)
            if letti > limite:
                break
        intestazioni = {k.lower(): v for k, v in risposta.headers.items()}
        return risposta.status_code, intestazioni, b"".join(pezzi)[:limite], risposta.encoding
    finally:
        risposta.close()


def _separa_risposta_curl(grezzo: bytes) -> tuple[int, dict[str, str], bytes, str | None]:
    """Interpreta l'output di `curl -i`: riga di stato, intestazioni, corpo."""
    testa, _, corpo = grezzo.partition(b"\r\n\r\n")
    while testa.startswith(b"HTTP/") and b" 100 " in testa.split(b"\r\n", 1)[0]:
        testa, _, corpo = corpo.partition(b"\r\n\r\n")  # risposta provvisoria
    righe = testa.decode("latin-1").split("\r\n")
    stato = re.match(r"HTTP/\S+\s+(\d{3})", righe[0])
    if not stato:
        raise ErroreAnalisi("Risposta di curl non riconosciuta")
    intestazioni = {}
    for riga in righe[1:]:
        nome, due_punti, valore = riga.partition(":")
        if due_punti:
            intestazioni[nome.strip().lower()] = valore.strip()
    codifica = re.search(r"charset=([\w-]+)", intestazioni.get("content-type", ""), re.I)
    return (
        int(stato.group(1)),
        intestazioni,
        corpo,
        codifica.group(1) if codifica else None,
    )


def _richiesta_curl(url: str) -> tuple[int, dict[str, str], bytes, str | None]:
    """Come _richiesta_requests, ma con il programma `curl` (stesso User-Agent
    dichiarato). Nessuna shell: gli argomenti sono una lista."""
    comando = [
        "curl",
        "-sS",
        "-i",
        "--proto",
        "=http,https",
        "--max-time",
        str(TIMEOUT_SECONDI),
        "-A",
        USER_AGENT,
        "-H",
        f"Accept: {_ACCEPT}",
        url,
    ]
    try:
        with subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as processo:
            grezzo = processo.stdout.read(_limite_byte(url) + 65536)
            processo.kill()  # se il corpo e' piu' grande del tetto, non serve il resto
            processo.wait()
            errore = processo.stderr.read().decode("utf-8", errors="replace").strip()
            if not grezzo:
                raise ErroreAnalisi(f"{url}: curl senza risposta ({errore or 'nessun errore'})")
    except FileNotFoundError as eccezione:
        raise ErroreAnalisi("curl non e' installato su questa macchina") from eccezione
    return _separa_risposta_curl(grezzo)


def _scarica(url: str, host_base: str, richiesta) -> _Risposta:
    """GET con redirect gestiti a mano (restando sullo stesso dominio),
    controllo della destinazione e tetto alla dimensione, con il trasporto
    `richiesta` (requests o curl). Nessuna pausa e nessun controllo di
    robots.txt: ci pensa _Scaricatore."""
    for _ in range(MAX_REDIRECT + 1):
        _controlla_destinazione(url)
        status, intestazioni, dati, codifica = richiesta(url)
        destinazione = intestazioni.get("location")
        if status in (301, 302, 303, 307, 308) and destinazione:
            url = urljoin(url, destinazione)
            if _host_base(url) != host_base:
                raise ErroreAnalisi(f"Redirect verso un altro dominio: {url}")
            continue
        tipo = intestazioni.get("content-type", "").lower()
        if status == 200 and not any(t in tipo for t in ("text/", "xml", "json")):
            raise ErroreAnalisi(f"{url}: contenuto non testuale ({tipo or 'sconosciuto'})")
        attesa = intestazioni.get("retry-after", "").strip()
        return _Risposta(
            status, url, _decodifica(dati, codifica), float(attesa) if attesa.isdigit() else None
        )
    raise ErroreAnalisi(f"Troppi redirect: {url}")


def _scarica_grezzo(url: str, host_base: str) -> _Risposta:
    return _scarica(url, host_base, _richiesta_requests)


def _scarica_grezzo_curl(url: str, host_base: str) -> _Risposta:
    return _scarica(url, host_base, _richiesta_curl)


def _avvia_playwright(visibile: bool = False):
    """Avvia un Chromium (senza finestra, oppure con la finestra visibile se `visibile`),
    con il suo User-Agent di serie, che non scarica immagini, video e font (pesano sul sito
    e non servono all'analisi). Restituisce (funzione che chiude tutto, pagina)."""
    from playwright.sync_api import sync_playwright

    avvio = sync_playwright().start()
    browser = avvio.chromium.launch(headless=not visibile)
    pagina = browser.new_page()
    pagina.route(
        "**/*",
        lambda route: (
            route.abort()
            if route.request.resource_type in ("image", "media", "font")
            else route.continue_()
        ),
    )

    def chiudi():
        browser.close()
        avvio.stop()

    return chiudi, pagina


class _Browser:
    """Trasporto con un browser vero: carica la pagina (JavaScript compreso) e ne
    restituisce l'HTML gia' costruito. Si avvia alla prima richiesta."""

    def __init__(self, visibile: bool = False):
        self.visibile = visibile
        self._chiudi = None
        self._pagina = None

    def scarica(self, url: str, host_base: str) -> _Risposta:
        _controlla_destinazione(url)
        if self._pagina is None:
            try:
                self._chiudi, self._pagina = (
                    _avvia_playwright(visibile=True) if self.visibile else _avvia_playwright()
                )
            except Exception as errore:  # noqa: BLE001 - Playwright non installato o senza Chromium
                raise ErroreAnalisi(
                    f"Browser non disponibile: {errore.__class__.__name__}"
                ) from errore
        try:
            risposta = self._pagina.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                self._pagina.wait_for_load_state("load", timeout=10000)
            except Exception:  # noqa: BLE001 - se non arriva a "load" si usa quello che c'e'
                pass
            self._pagina.wait_for_timeout(500)  # un attimo per il JavaScript della pagina
            if risposta is None:
                raise ErroreAnalisi(f"{url}: nessuna risposta")
            if _host_base(self._pagina.url) != host_base:
                raise ErroreAnalisi(f"Redirect verso un altro dominio: {self._pagina.url}")
            tipo = risposta.headers.get("content-type", "").lower()
            testo = self._pagina.content() if "html" in tipo else risposta.text()
            attesa = (risposta.headers.get("retry-after") or "").strip()
            return _Risposta(
                risposta.status,
                self._pagina.url,
                testo[: _limite_byte(url)],
                float(attesa) if attesa.isdigit() else None,
            )
        except ErroreAnalisi:
            raise
        except Exception as errore:  # noqa: BLE001 - timeout, rete, pagina chiusa
            raise ErroreAnalisi(f"{url}: {errore.__class__.__name__}") from errore

    def chiudi(self):
        if self._chiudi:
            self._chiudi()
        self._chiudi = self._pagina = None


class _Scaricatore:
    """Aggiunge a _scarica_grezzo il rispetto di robots.txt e la pausa."""

    def __init__(
        self,
        url_iniziale: str,
        usa_curl: bool = False,
        browser: "_Browser | None" = None,
        ritenta_dopo_429: bool = True,
    ):
        self.usa_curl = usa_curl
        self.browser = browser
        self.ritenta_dopo_429 = ritenta_dopo_429
        parti = urlsplit(url_iniziale)
        self.origine = f"{parti.scheme}://{parti.netloc}"
        self.host = _host_base(url_iniziale)
        self.sitemap_dichiarate: list[str] = []
        self._robots = RobotFileParser()
        self._pausa = PAUSA_SECONDI
        self._ultima = 0.0

    def _scarica(self, url: str) -> _Risposta:
        # Le funzioni di trasporto si cercano al momento della chiamata (i test le sostituiscono).
        if self.browser:
            return self.browser.scarica(url, self.host)
        scarica = _scarica_grezzo_curl if self.usa_curl else _scarica_grezzo
        return scarica(url, self.host)

    def carica_robots(self) -> None:
        risposta = self._scarica(f"{self.origine}/robots.txt")
        if risposta.status >= 500:
            raise ErroreAnalisi(
                f"robots.txt non leggibile (HTTP {risposta.status}): "
                "per prudenza non analizzo il sito."
            )
        # 4xx: nessun robots.txt, quindi nessuna restrizione.
        self._robots.parse(risposta.testo.splitlines() if risposta.status == 200 else [])
        self.sitemap_dichiarate = self._robots.site_maps() or []
        ritardo = self._robots.crawl_delay(USER_AGENT_TOKEN)
        if ritardo:
            self._pausa = max(self._pausa, min(float(ritardo), PAUSA_MASSIMA_SECONDI))

    def get(self, url: str) -> _Risposta:
        if not self._robots.can_fetch(USER_AGENT_TOKEN, url):
            raise ErroreAnalisi(f"{url}: vietato da robots.txt")
        attesa = self._pausa - (time.monotonic() - self._ultima)
        if attesa > 0:
            time.sleep(attesa)
        try:
            risposta = self._scarica(url)
            # Se il sito chiede di rallentare si aspetta quanto indicato e si
            # ritenta una volta sola; se insiste, non si prosegue (vedi _analizza).
            if (
                self.ritenta_dopo_429
                and risposta.status in (429, 503)
                and risposta.retry_after is not None
                and risposta.retry_after <= RETRY_AFTER_MASSIMO_SECONDI
            ):
                time.sleep(risposta.retry_after)
                risposta = self._scarica(url)
            return risposta
        finally:
            self._ultima = time.monotonic()


# --- estrazione dei campi SEO da una pagina ---------------------------------


class _Estrattore(HTMLParser):
    _IGNORATI = frozenset(
        {"script", "style", "noscript", "template", "nav", "footer", "header", "aside"}
    )
    # Tag che chiudono un "blocco" di testo (un paragrafo, una voce di elenco, ...):
    # il testo dei tag in linea (strong, a, span) resta nello stesso blocco.
    _BLOCCHI = frozenset(
        "p div li ul ol tr td th table br section article main h1 h2 h3 h4 h5 h6 dt dd dl "
        "blockquote button figcaption form option select optgroup label legend summary "
        "caption fieldset".split()
    )
    _MAX_BLOCCHI = 800
    _MAX_CARATTERI_BLOCCO = 1500

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.titolo = ""
        self.meta: dict[str, str] = {}
        self.canonical = ""
        self.lingua = ""
        self.h1: list[str] = []
        self.h2: list[str] = []
        self.n_h3 = 0
        self.json_ld: list[str] = []
        self.link: list[str] = []
        self.immagini = 0
        self.immagini_senza_alt = 0
        self.parole = 0
        self.paragrafi = 0
        self.voci_elenco = 0
        self.tabelle = 0
        self.video = 0
        self.blocchi: list[str] = []
        self.blocchi_dopo_h1: list[str] = []
        self._in_titolo = False
        self._titolo_aperto: str | None = None
        self._buffer_titolo: list[str] = []
        self._buffer_titolo_h: list[str] = []
        self._json_ld_aperto = False
        self._buffer_json: list[str] = []
        self._buffer_blocco: list[str] = []
        self._profondita_ignorata = 0
        self._in_head = False
        self._h1_visto = False

    def _chiudi_blocco(self):
        testo = " ".join("".join(self._buffer_blocco).split())
        self._buffer_blocco = []
        if not testo or len(self.blocchi) >= self._MAX_BLOCCHI:
            return
        testo = testo[: self._MAX_CARATTERI_BLOCCO]
        self.blocchi.append(testo)
        if self._h1_visto:
            self.blocchi_dopo_h1.append(testo)

    def _nel_contenuto(self) -> bool:
        return not self._in_head and not self._profondita_ignorata

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag in self._BLOCCHI or tag in self._IGNORATI:
            self._chiudi_blocco()
        if self._nel_contenuto():
            if tag == "p":
                self.paragrafi += 1
            elif tag == "li":
                self.voci_elenco += 1
            elif tag in ("table", "dl"):
                self.tabelle += 1
            elif tag == "video" or (
                tag == "iframe" and re.search(r"youtube|vimeo", a.get("src", ""), re.I)
            ):
                self.video += 1
        if tag == "html":
            self.lingua = a.get("lang", "")
        elif tag == "title":
            self._in_titolo = True
        elif tag == "meta":
            chiave = (a.get("name") or a.get("property") or "").lower()
            if chiave and chiave not in self.meta:
                self.meta[chiave] = a.get("content", "").strip()
        elif tag == "link" and a.get("rel", "").lower() == "canonical":
            self.canonical = a.get("href", "").strip()
        elif tag == "a" and a.get("href"):
            self.link.append(a["href"].strip())
        elif tag == "img":
            self.immagini += 1
            if not a.get("alt", "").strip():
                self.immagini_senza_alt += 1
        elif tag in ("h1", "h2"):
            self._titolo_aperto = tag
            self._buffer_titolo_h = []
        elif tag == "h3":
            if self._nel_contenuto():  # gli H3 di menu e footer non fanno parte della gerarchia
                self.n_h3 += 1
        elif tag == "head":
            self._in_head = True
        if tag == "script" and "ld+json" in a.get("type", "").lower():
            self._json_ld_aperto = True
            self._buffer_json = []
        if tag in self._IGNORATI:
            self._profondita_ignorata += 1

    def handle_endtag(self, tag):
        if tag in self._BLOCCHI or tag in self._IGNORATI:
            self._chiudi_blocco()
        if tag == "title":
            self._in_titolo = False
            if not self.titolo:
                self.titolo = " ".join("".join(self._buffer_titolo).split())
        elif tag in ("h1", "h2") and self._titolo_aperto == tag:
            testo = " ".join("".join(self._buffer_titolo_h).split())
            if testo:
                (self.h1 if tag == "h1" else self.h2).append(testo)
            self._titolo_aperto = None
            if tag == "h1":
                self._h1_visto = True
        elif tag == "head":
            self._in_head = False
        elif tag == "script" and self._json_ld_aperto:
            self._json_ld_aperto = False
            self.json_ld.append("".join(self._buffer_json))
        if tag in self._IGNORATI:
            self._profondita_ignorata = max(0, self._profondita_ignorata - 1)

    def handle_data(self, dati):
        if self._in_titolo:
            self._buffer_titolo.append(dati)
        if self._json_ld_aperto:
            self._buffer_json.append(dati)
        if self._titolo_aperto:
            self._buffer_titolo_h.append(dati)
        if self._nel_contenuto():
            self.parole += len(dati.split())
            self._buffer_blocco.append(dati)

    def close(self):
        super().close()
        self._chiudi_blocco()


def _tipi_schema(blocchi_json: list[str]) -> list[str]:
    tipi: set[str] = set()

    def visita(nodo):
        if isinstance(nodo, list):
            for elemento in nodo:
                visita(elemento)
        elif isinstance(nodo, dict):
            valore = nodo.get("@type")
            if isinstance(valore, str):
                tipi.add(valore)
            elif isinstance(valore, list):
                tipi.update(v for v in valore if isinstance(v, str))
            for figlio in nodo.values():
                if isinstance(figlio, (dict, list)):
                    visita(figlio)

    for blocco in blocchi_json:
        try:
            visita(json.loads(blocco))
        except ValueError:
            continue  # JSON-LD malformato: capita, non e' un errore dell'analisi
    return sorted(tipi)


def _dati_prodotto(blocchi_json: list[str]) -> dict:
    """Descrizione, marca, valutazioni e disponibilita' dichiarate nel primo
    JSON-LD di tipo Product (vuoto se non c'e')."""

    def e_prodotto(nodo: dict) -> bool:
        tipo = nodo.get("@type")
        return tipo == "Product" or (isinstance(tipo, list) and "Product" in tipo)

    def cerca(nodo):
        if isinstance(nodo, list):
            for elemento in nodo:
                trovato = cerca(elemento)
                if trovato:
                    return trovato
        elif isinstance(nodo, dict):
            if e_prodotto(nodo):
                return nodo
            for figlio in nodo.values():
                if isinstance(figlio, (dict, list)):
                    trovato = cerca(figlio)
                    if trovato:
                        return trovato
        return None

    for blocco in blocchi_json:
        try:
            nodo = cerca(json.loads(blocco))
        except ValueError:
            continue
        if not nodo:
            continue
        marca = nodo.get("brand")
        if isinstance(marca, dict):
            marca = marca.get("name")
        offerte = nodo.get("offers")
        offerta = offerte[0] if isinstance(offerte, list) and offerte else offerte
        disponibilita = offerta.get("availability") if isinstance(offerta, dict) else ""
        descrizione = nodo.get("description")
        return {
            "descrizione": " ".join(descrizione.split()) if isinstance(descrizione, str) else "",
            "marca": marca if isinstance(marca, str) else "",
            "con_valutazioni": bool(nodo.get("aggregateRating") or nodo.get("review")),
            "disponibilita": str(disponibilita or "").rsplit("/", 1)[-1],
        }
    return {}


def _estrai_pagina(testo: str, url: str, tipo: str, host: str) -> tuple[dict, list[str]]:
    """Campi SEO e testo di una pagina e URL dei suoi link interni (assoluti,
    senza ancore). Il testo resta nel campo interno `_blocchi` (i blocchi di
    contenuto, dopo l'H1 se c'e'), che competitor_text.analizza_testi consuma."""
    estrattore = _Estrattore()
    estrattore.feed(testo)
    estrattore.close()

    interni: list[str] = []
    n_esterni = 0
    visti: set[str] = set()
    for href in estrattore.link:
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        assoluto = urljoin(url, href).split("#")[0]
        if urlsplit(assoluto).scheme not in ("http", "https"):
            continue
        if _host_base(assoluto) == host:
            if assoluto not in visti:
                visti.add(assoluto)
                interni.append(assoluto)
        else:
            n_esterni += 1

    meta_description = estrattore.meta.get("description", "")
    pagina = {
        "url": url,
        "tipo": tipo,
        "titolo": estrattore.titolo,
        "lunghezza_titolo": len(estrattore.titolo),
        "meta_description": meta_description,
        "lunghezza_meta": len(meta_description),
        "h1": estrattore.h1[:3],
        "h2": estrattore.h2[:30],  # poi si tolgono quelle del template; il report ne mostra 5
        "n_h3": estrattore.n_h3,
        "dati_strutturati": _tipi_schema(estrattore.json_ld),
        "canonical": estrattore.canonical,
        "meta_robots": estrattore.meta.get("robots", ""),
        "og_url": estrattore.meta.get("og:url", ""),
        "open_graph": "og:title" in estrattore.meta,
        "lingua": estrattore.lingua,
        "n_parole": estrattore.parole,
        "immagini": estrattore.immagini,
        "immagini_senza_alt": estrattore.immagini_senza_alt,
        "link_interni": len(interni),
        "link_esterni": n_esterni,
        "struttura": {
            "paragrafi": estrattore.paragrafi,
            "voci_di_elenco": estrattore.voci_elenco,
            "tabelle_o_liste_specifiche": estrattore.tabelle,
            "video": estrattore.video,
        },
        "dati_prodotto": _dati_prodotto(estrattore.json_ld),
        "_blocchi": estrattore.blocchi_dopo_h1 if estrattore.h1 else estrattore.blocchi,
        "_blocchi_tutti": estrattore.blocchi,
    }
    return pagina, interni


# --- sitemap e scelta del campione ------------------------------------------


def _estrai_loc(testo: str) -> list[str]:
    return [html.unescape(u).strip() for u in re.findall(r"<loc>\s*(.*?)\s*</loc>", testo, re.S)]


def _tipo_da_percorso(url: str) -> str | None:
    percorso = urlsplit(url).path.lower()
    if any(f in percorso for f in _FRAGMENT_PRODOTTO):
        return "prodotto"
    if any(f in percorso for f in _FRAGMENT_CATEGORIA + _FRAGMENT_COLLEZIONE):
        return "categoria"
    return None


def _tipo_da_nome_sitemap(url: str) -> str | None:
    nome = urlsplit(url).path.lower()
    if any(k in nome for k in ("product_cat", "product-cat", "categor", "collection")):
        return "categoria"
    if ("product" in nome or "prodott" in nome) and "tag" not in nome:
        return "prodotto"
    return None


_RE_PREFISSO_LINGUA = re.compile(r"^/([a-z]{2}(?:-[a-z]{2})?)(/.*)$")


def _senza_varianti_lingua(urls: list[str]) -> list[str]:
    """Toglie le versioni con prefisso di lingua (/en/..., /fr/...) di una pagina
    che esiste anche senza prefisso: sono la stessa pagina tradotta e
    sprecherebbero un posto del campione."""
    percorsi = {urlsplit(u).path for u in urls}
    return [
        u
        for u in urls
        if not ((m := _RE_PREFISSO_LINGUA.match(urlsplit(u).path)) and m.group(2) in percorsi)
    ]


def _campiona(urls: list[str], quanti: int) -> list[str]:
    """Scelta deterministica e distribuita su tutta la lista (non solo i primi
    elementi, che in una sitemap sono di solito i piu' vecchi)."""
    if quanti <= 0:
        return []
    if len(urls) <= quanti:
        return list(urls)
    if quanti == 1:
        return [urls[0]]
    passo = (len(urls) - 1) / (quanti - 1)
    return [urls[round(i * passo)] for i in range(quanti)]


def _scarica_sitemap(scaricatore: _Scaricatore, url: str) -> str | None:
    if url.endswith(".gz") or _host_base(url) != scaricatore.host:
        return None
    try:
        risposta = scaricatore.get(url)
    except ErroreAnalisi:
        return None
    if risposta.status == 200 and "<loc>" in risposta.testo:
        return risposta.testo
    return None


_SEGMENTI_NON_PRODOTTO = frozenset(
    "blog news notizie articoli articolo post posts tag tags author autore pagina pagine page "
    "pages wp-content wp-json feed amp".split()
)
MIN_URL_GRUPPO_DOMINANTE = 5


def _gruppo_dominante(urls: list[str]) -> tuple[list[str], str]:
    """Gli indirizzi che condividono il primo tratto del percorso (es. /scheda-auto/),
    se sono il gruppo piu' numeroso e abbastanza grande: per i siti i cui prodotti
    non hanno un indirizzo riconoscibile (auto, immobili, annunci). Esclude blog e
    simili. Restituisce (indirizzi, tratto) o ([], "")."""
    gruppi: dict[str, list[str]] = {}
    for url in urls:
        segmenti = [x for x in urlsplit(url).path.lower().split("/") if x]
        # un solo tratto (es. /contatti.html) e' una pagina, non un gruppo
        if len(segmenti) >= 2 and segmenti[0] not in _SEGMENTI_NON_PRODOTTO:
            gruppi.setdefault(segmenti[0], []).append(url)
    if not gruppi:
        return [], ""
    nome, elenco = max(gruppi.items(), key=lambda voce: len(voce[1]))
    if len(elenco) < MIN_URL_GRUPPO_DOMINANTE or len(elenco) <= 0.3 * len(urls):
        return [], ""
    return elenco, f"/{nome}/"


def _urls_dalla_sitemap(
    scaricatore: _Scaricatore,
) -> tuple[dict[str, list[str]], str | None, list[str]]:
    """URL di categorie e prodotti trovati nella sitemap (indice o piatta), indirizzo
    della sitemap usata (None se non se ne trova nessuna) e gli altri indirizzi che
    non si riconoscono. Solo indirizzi del dominio analizzato: le sitemap a volte
    elencano anche altri domini."""
    trovati: dict[str, list[str]] = {"categoria": [], "prodotto": []}
    altri: list[str] = []

    def stesso_dominio(urls: list[str]) -> list[str]:
        return [u for u in urls if _host_base(u) == scaricatore.host]

    candidate = list(
        dict.fromkeys(
            scaricatore.sitemap_dichiarate
            + [
                f"{scaricatore.origine}{p}"
                for p in ("/sitemap.xml", "/wp-sitemap.xml", "/sitemap_index.xml")
            ]
        )
    )
    for indirizzo in candidate:
        testo = _scarica_sitemap(scaricatore, indirizzo)
        if testo is None:
            continue
        if "<sitemapindex" in testo:
            figlie: dict[str, list[str]] = {"categoria": [], "prodotto": []}
            for figlia in _estrai_loc(testo):
                tipo = _tipo_da_nome_sitemap(figlia)
                if tipo:
                    figlie[tipo].append(figlia)
            for tipo, elenco in figlie.items():
                for figlia in elenco[:MAX_SITEMAP_FIGLIE]:
                    contenuto = _scarica_sitemap(scaricatore, figlia)
                    if contenuto:
                        trovati[tipo].extend(stesso_dominio(_estrai_loc(contenuto)))
        else:
            for url in stesso_dominio(_estrai_loc(testo)):
                tipo = _tipo_da_percorso(url)
                if tipo:
                    trovati[tipo].append(url)
                else:
                    altri.append(url)
        return trovati, indirizzo, altri
    return trovati, None, altri


# --- aggregazione -----------------------------------------------------------


def _percentuale(parte: int, totale: int) -> int:
    return round(100 * parte / totale) if totale else 0


def _media(valori: list[int | float]) -> int:
    return round(sum(valori) / len(valori)) if valori else 0


def _normalizza_testo(testo: str) -> str:
    return " ".join(testo.lower().split())


def _schema_titolo(titoli: list[str]) -> dict:
    """Separatore piu' usato e segmento finale ricorrente (di solito il brand)."""
    titoli = [t for t in titoli if t]
    separatori = Counter(s.strip() for t in titoli for s in _SEPARATORI_TITOLO if s in t)
    suffissi: Counter = Counter()
    for titolo in titoli:
        for separatore in _SEPARATORI_TITOLO:
            if separatore in titolo:
                suffissi[_normalizza_testo(titolo.rsplit(separatore, 1)[1])] += 1
                break
    suffisso, volte = suffissi.most_common(1)[0] if suffissi else ("", 0)
    return {
        "lunghezza_media": _media([len(t) for t in titoli]),
        "percentuale_tra_30_e_60_caratteri": _percentuale(
            sum(30 <= len(t) <= 60 for t in titoli), len(titoli)
        ),
        "separatore_piu_comune": separatori.most_common(1)[0][0] if separatori else "",
        "suffisso_ricorrente": suffisso if volte >= max(2, len(titoli) // 2) else "",
    }


def _riepilogo_tipo(pagine: list[dict]) -> dict:
    n = len(pagine)
    h2: Counter = Counter()
    schema: Counter = Counter()
    for pagina in pagine:
        h2.update({_normalizza_testo(t) for t in pagina["h2"]})
        schema.update(pagina["dati_strutturati"])
    totale_immagini = sum(p["immagini"] for p in pagine)
    return {
        "pagine_analizzate": n,
        "titolo": _schema_titolo([p["titolo"] for p in pagine]),
        "meta_description": {
            "presente_percentuale": _percentuale(
                sum(bool(p["meta_description"]) for p in pagine), n
            ),
            "lunghezza_media": _media(
                [p["lunghezza_meta"] for p in pagine if p["meta_description"]]
            ),
        },
        "con_un_solo_h1_percentuale": _percentuale(sum(len(p["h1"]) == 1 for p in pagine), n),
        "h2_ricorrenti": [{"testo": t, "pagine": c} for t, c in h2.most_common(8) if c >= 2],
        "dati_strutturati": dict(schema.most_common()),
        "parole_medie": _media([p["n_parole"] for p in pagine]),
        "immagini_senza_alt_percentuale": _percentuale(
            sum(p["immagini_senza_alt"] for p in pagine), totale_immagini
        ),
        "link_interni_medi": _media([p["link_interni"] for p in pagine]),
    }


def _parole_ricorrenti(pagine: list[dict]) -> list[dict]:
    """Termini di titolo, H1 e H2 presenti in almeno 2 pagine (contati una
    volta per pagina)."""
    per_pagina: Counter = Counter()
    for pagina in pagine:
        testo = " ".join([pagina["titolo"], *pagina["h1"], *pagina["h2"]]).lower()
        termini = {
            t
            for t in re.findall(r"[a-zàèéìòù0-9]{4,}", testo)
            if t not in competitor_text.PAROLE_VUOTE
        }
        per_pagina.update(termini)
    return [{"termine": t, "pagine": c} for t, c in per_pagina.most_common(15) if c >= 2]


def _vista_pagina(pagina: dict, max_caratteri: int) -> dict:
    """La pagina com'e' nel report: solo i campi utili a chi legge, con il
    testo limitato all'estratto."""
    dati_prodotto = dict(pagina["dati_prodotto"])
    if dati_prodotto:
        dati_prodotto["descrizione"] = dati_prodotto["descrizione"][:max_caratteri]
    return {
        "url": pagina["url"],
        "tipo": pagina["tipo"],
        "titolo": pagina["titolo"],
        "meta_description": pagina["meta_description"],
        "h1": pagina["h1"],
        "h2": pagina["h2"][:5],
        "dati_strutturati": pagina["dati_strutturati"],
        "n_parole": pagina["n_parole"],
        "struttura": pagina["struttura"],
        "dati_prodotto": dati_prodotto,
        "estratto": pagina["estratto"],
    }


def _costruisci_report(
    sito: str,
    pagine: list[dict],
    saltate: list[dict],
    sitemap: str | None,
    urls_in_sitemap: dict[str, int],
    avvisi: list[str],
    testo: dict,
    max_caratteri: int,
) -> dict:
    per_tipo = {
        tipo: {**_riepilogo_tipo([p for p in pagine if p["tipo"] == tipo]), **dettagli}
        for tipo, dettagli in testo["per_tipo"].items()
    }
    return {
        "sito": sito,
        "data": date.today().isoformat(),
        "campione": {
            "pagine_analizzate": len(pagine),
            "categorie": sum(p["tipo"] == "categoria" for p in pagine),
            "prodotti": sum(p["tipo"] == "prodotto" for p in pagine),
            "pagine_saltate": saltate,
        },
        "sitemap": {"indirizzo": sitemap, "url_trovati": urls_in_sitemap},
        "avvisi": avvisi,
        "riepilogo_per_tipo": per_tipo,
        "parole_nei_titoli": _parole_ricorrenti(pagine),
        "messaggi_ripetuti_sul_sito": testo["messaggi_ripetuti_sul_sito"],
        "pagine": [_vista_pagina(p, max_caratteri) for p in pagine],
        "nota_uso": (
            "Gli estratti e il vocabolario servono a capire intenzione, tono e modo di "
            "descrivere i prodotti del sito analizzato: analizzali e scrivi testi "
            "originali, con parole tue. Non riutilizzare frasi, titoli o description del "
            "concorrente e scrivi solo cose vere sui nostri prodotti."
        ),
    }


def _avviso_pagine_identiche(pagine: list[dict]) -> str | None:
    """Segnala quando la maggior parte delle pagine di categoria/prodotto ha lo
    stesso H1 e la stessa lunghezza: di solito e' una pagina segnaposto
    ("negozio in arrivo", manutenzione) o una sfida anti-bot servita al posto
    del contenuto, e i numeri del report non descrivono le pagine vere."""
    gruppi = Counter(
        (tuple(p["h1"]), p["n_parole"]) for p in pagine if p["tipo"] != "home" and p["h1"]
    )
    totale = sum(p["tipo"] != "home" for p in pagine)
    if not gruppi:
        return None
    (h1, _), uguali = gruppi.most_common(1)[0]
    if uguali < 3 or uguali < 0.6 * totale:
        return None
    return (
        f"{uguali} pagine su {totale} hanno lo stesso H1 ('{h1[0]}') e la stessa lunghezza: "
        "probabilmente il sito serve una pagina segnaposto (negozio 'in arrivo', "
        "manutenzione, controllo anti-bot) invece del contenuto vero. Titoli e meta "
        "description restano validi, ma struttura, parole e immagini no."
    )


# --- entry point ------------------------------------------------------------


_SUGGERIMENTO_BROWSER = (
    "Si puo' provare con un browser vero: attiva SEO_ANALISI_USA_BROWSER=1 (o usa_browser=true "
    "per questa analisi). In alternativa salva le pagine dal tuo browser e usa "
    "analizza_pagine_salvate."
)
_SUGGERIMENTO_PAGINE_SALVATE = (
    "Anche con un browser il sito non lascia leggere le pagine: salvale dal tuo browser e usa "
    "analizza_pagine_salvate."
)


def _motivo_http(status: int) -> str:
    if status in (403, 429):
        return f"HTTP {status}: il sito non accetta richieste automatiche da questo client"
    return f"HTTP {status}"


def _avviso_javascript(home: dict) -> list[str]:
    if home["h1"] or home["n_parole"] >= 50:
        return []
    return [
        "La home ha quasi nessun testo e nessun H1 nell'HTML scaricato: il sito "
        "probabilmente costruisce le pagine con JavaScript, e questa analisi (che non "
        "esegue JavaScript) vede solo una parte di quello che vede Google."
    ]


def _chiudi_analisi(
    origine: str,
    pagine: list[dict],
    saltate: list[dict],
    sitemap: str | None,
    urls_in_sitemap: dict[str, int],
    avvisi: list[str],
    max_caratteri: int,
    in_rete: bool = True,
    sitemap_verificata: bool = True,
) -> dict:
    """Parte comune a analizza_seo_sito e analizza_pagine_salvate: analisi del
    testo, valutazione della struttura SEO, salvataggio dei testi per
    controlla_somiglianza e costruzione del report. `in_rete` e' False per le
    pagine salvate, dove sitemap e HTTPS non sono verificabili."""
    avviso_identiche = _avviso_pagine_identiche(pagine)
    if avviso_identiche:
        avvisi.append(avviso_identiche)
    testo = competitor_text.analizza_testi(pagine, max_caratteri)
    # I testi analizzati restano in locale per controlla_somiglianza.
    try:
        text_similarity.salva_corpus(origine, [{**p, "testo": p["_testo_proprio"]} for p in pagine])
        confronto = "Testi salvati in locale: usa controlla_somiglianza sui nostri testi."
    except OSError as errore:
        confronto = (
            f"Testi non salvati ({errore.__class__.__name__}): controlla_somiglianza non li avra'."
        )
    report = _costruisci_report(
        origine, pagine, saltate, sitemap, urls_in_sitemap, avvisi, testo, max_caratteri
    )
    report["controllo_somiglianza"] = confronto
    report["valutazione"] = seo_scorecard.valuta(
        pagine,
        sitemap is not None if in_rete and sitemap_verificata else None,
        origine.startswith("https://") if in_rete else None,
    )
    report["valutazione"]["nota"] = (
        "Il punteggio e' solo un riferimento per l'utilizzatore, non e' vincolante. Prima di "
        "proporre testi ispirati a questo sito, mostragli punteggio e aree e chiedigli se vuole "
        "usarlo come ispirazione, e per quali aree."
    )
    return report


def _e_pagina(url: str) -> bool:
    """L'indirizzo punta a una pagina (es. /it/category/telefoni-1001.html) e non a una
    cartella o alla radice: in quel caso la "sezione" non e' un prefisso del percorso
    ma cio' che la pagina elenca (sottocategorie e prodotti collegati)."""
    percorso = urlsplit(url).path
    return bool(percorso) and not percorso.endswith("/") and "." in percorso.rsplit("/", 1)[-1]


def _perimetro(url: str) -> str:
    """Il percorso dell'indirizzo iniziale se punta a una sezione (es. /telefonia),
    "" se punta alla radice del sito o a una singola pagina (vedi _e_pagina)."""
    return "" if _e_pagina(url) else urlsplit(url).path.lower().rstrip("/")


def _nel_perimetro(url: str, perimetro: str) -> bool:
    if not perimetro:
        return True
    percorso = urlsplit(url).path.lower().rstrip("/")
    return percorso == perimetro or percorso.startswith(perimetro + "/")


def _composizione(pagine: list[dict], perimetro: str) -> dict[str, dict[str, int]]:
    """Da dove vengono le pagine del campione: per ogni tipo, quante stanno in ciascun
    sottogruppo (il primo tratto del percorso dopo il perimetro). Mostra subito se il
    campione e' sbilanciato (es. quasi tutti accessori)."""
    saltare = len([x for x in perimetro.split("/") if x])
    composizione: dict[str, dict[str, int]] = {}
    for pagina in pagine:
        if pagina["tipo"] not in ("categoria", "prodotto"):
            continue
        segmenti = [x for x in urlsplit(pagina["url"]).path.split("/") if x]
        if not perimetro and segmenti and re.fullmatch(r"[a-z]{2}", segmenti[0]):
            segmenti = segmenti[1:]  # prefisso di lingua (/it/...)
        segmenti = segmenti[saltare:]
        gruppo = segmenti[0] if len(segmenti) > 1 else "(radice)"
        tipo = composizione.setdefault(pagina["tipo"], {})
        tipo[gruppo] = tipo.get(gruppo, 0) + 1
    return composizione


def _analizza(
    url: str,
    max_categorie: int,
    max_prodotti: int,
    max_caratteri: int,
    usa_curl: bool = False,
    browser: "_Browser | None" = None,
    ritenta_dopo_429: bool = True,
) -> dict:
    url = _normalizza_url(url)
    perimetro = _perimetro(url)
    modo_pagina = _e_pagina(url)
    campione_da_link = modo_pagina  # vero anche se si passa ai link dopo (vedi sotto)
    scaricatore = _Scaricatore(url, usa_curl, browser, ritenta_dopo_429)
    scaricatore.carica_robots()

    risposta_home = scaricatore.get(url)
    if risposta_home.status in (403, 429):
        raise SitoBloccato(
            f"Pagina iniziale: {_motivo_http(risposta_home.status)}", risposta_home.retry_after
        )
    if risposta_home.status != 200:
        raise ErroreAnalisi(f"Pagina iniziale: {_motivo_http(risposta_home.status)}")
    home, link_home = _estrai_pagina(
        risposta_home.testo,
        risposta_home.url,
        "sezione" if perimetro or modo_pagina else "home",
        scaricatore.host,
    )
    pagine = [home]
    avvisi: list[str] = []
    avvisi.extend(_avviso_javascript(home))

    if modo_pagina:
        # Il campione viene dai link della pagina: la sitemap non serve (e puo' essere enorme).
        trovati, sitemap, altri = {"categoria": [], "prodotto": []}, None, []
        avvisi.append(
            "L'indirizzo e' una pagina di categoria: il campione e' scelto fra le sottocategorie e "
            "i prodotti collegati da quella pagina, non dalla sitemap."
        )
    else:
        trovati, sitemap, altri = _urls_dalla_sitemap(scaricatore)
    link_tutti = list(link_home)
    # La pagina da cui si parte non e' un elemento del campione (la sitemap la elenca, a volte).
    iniziale = risposta_home.url.rstrip("/")
    trovati = {t: [u for u in v if u.rstrip("/") != iniziale] for t, v in trovati.items()}
    if perimetro:
        # Si analizza solo la sezione indicata: sitemap e link restano dentro il suo percorso.
        trovati = {t: [u for u in v if _nel_perimetro(u, perimetro)] for t, v in trovati.items()}
        altri = [u for u in altri if _nel_perimetro(u, perimetro)]
        link_home = [u for u in link_home if _nel_perimetro(u, perimetro)]
        altri += [u for u in link_home if not _tipo_da_percorso(u) and u not in altri]
    if sitemap is None and not modo_pagina:
        avvisi.append(
            "Nessuna sitemap trovata: le pagine di esempio sono scelte dai link della home."
        )
    # I link della home integrano la sitemap solo dove questa non ha dato nulla.
    da_home: dict[str, list[str]] = {"categoria": [], "prodotto": []}
    for link in link_home:
        tipo = _tipo_da_percorso(link)
        if tipo:
            da_home[tipo].append(link)
    for tipo in da_home:
        trovati[tipo] = _senza_varianti_lingua(trovati[tipo] or da_home[tipo])
    if perimetro and not trovati["prodotto"]:
        # Sotto il percorso indicato non ci sono prodotti (stanno altrove, es. /l/smartphone/...
        # con i prodotti in /p/...): si campiona fra cio' che la pagina stessa collega.
        da_pagina: dict[str, list[str]] = {"categoria": [], "prodotto": []}
        for link in link_tutti:
            tipo = _tipo_da_percorso(link)
            if tipo and link.rstrip("/") != iniziale:
                da_pagina[tipo].append(link)
        if da_pagina["prodotto"] or (da_pagina["categoria"] and not trovati["categoria"]):
            trovati["prodotto"] = _senza_varianti_lingua(da_pagina["prodotto"])
            if not trovati["categoria"]:
                trovati["categoria"] = _senza_varianti_lingua(da_pagina["categoria"])
            campione_da_link = True
            avvisi.append(
                "Nessun prodotto sotto il percorso indicato: il campione e' scelto fra quelli "
                "collegati da quella pagina."
            )
    if not trovati["prodotto"] and not campione_da_link:
        gruppo, tratto = _gruppo_dominante(altri)
        if gruppo:
            trovati["prodotto"] = gruppo
            avvisi.append(
                f"Nessun indirizzo di prodotto riconosciuto: ho trattato come prodotti le pagine "
                f"del gruppo piu' numeroso della sitemap ({tratto}, {len(gruppo)} indirizzi)."
            )
    urls_in_sitemap = {"categorie": len(trovati["categoria"]), "prodotti": len(trovati["prodotto"])}

    campione = [
        *((u, "categoria") for u in _campiona(trovati["categoria"], max_categorie)),
        *((u, "prodotto") for u in _campiona(trovati["prodotto"], max_prodotti)),
    ]
    saltate: list[dict] = []
    for indirizzo, tipo in campione:
        if indirizzo.rstrip("/") == risposta_home.url.rstrip("/"):
            continue
        try:
            risposta = scaricatore.get(indirizzo)
        except ErroreAnalisi as errore:
            saltate.append({"url": indirizzo, "motivo": str(errore)})
            continue
        if risposta.status != 200:
            saltate.append({"url": indirizzo, "motivo": _motivo_http(risposta.status)})
            if risposta.status == 429:
                avvisi.append(
                    "Il sito ha continuato a limitare le richieste (HTTP 429) anche dopo l'attesa "
                    "richiesta: mi sono fermato, il report copre solo le pagine gia' scaricate."
                )
                break
            continue
        pagina, _ = _estrai_pagina(risposta.testo, risposta.url, tipo, scaricatore.host)
        pagine.append(pagina)

    if len(pagine) == 1 and not saltate:
        avvisi.append(
            "Non ho trovato categorie o prodotti da analizzare: il report copre solo la home."
        )
    non_trovate = sum(s["motivo"].startswith("HTTP 404") for s in saltate)
    if non_trovate:
        avvisi.append(
            f"{non_trovate} indirizzi della sitemap su {len(campione)} campionati rispondono 404: "
            "la sitemap non e' aggiornata."
        )
    report = _chiudi_analisi(
        scaricatore.origine,
        pagine,
        saltate,
        sitemap,
        urls_in_sitemap,
        avvisi,
        max_caratteri,
        sitemap_verificata=not modo_pagina,
    )
    report["perimetro"] = f"pagina {urlsplit(url).path}" if campione_da_link else perimetro or None
    report["campione"]["composizione"] = _composizione(
        pagine, "" if campione_da_link else perimetro
    )
    return report


def _sembra_costruito_con_js(report: dict) -> bool:
    return any(a.startswith("La home ha quasi nessun testo") for a in report.get("avvisi", []))


def _analizza_con_browser(
    url, max_categorie, max_prodotti, max_caratteri, motivo: str, visibile: bool = False
) -> dict:
    browser = _Browser(visibile)
    try:
        report = _analizza(
            url, max_categorie, max_prodotti, max_caratteri, browser=browser, ritenta_dopo_429=False
        )
    except SitoBloccato as errore:
        raise ErroreAnalisi(f"{errore}. {_SUGGERIMENTO_PAGINE_SALVATE}") from errore
    finally:
        browser.chiudi()
    report["metodo"] = "browser"
    finestra = ", con la finestra visibile" if visibile else ""
    report["avvisi"].append(
        f"Pagine caricate con un browser (Chromium{finestra}) perche' {motivo}."
    )
    return report


def analizza_seo_sito(
    url: str,
    max_categorie: int = MAX_CATEGORIE_DEFAULT,
    max_prodotti: int = MAX_PRODOTTI_DEFAULT,
    caratteri_per_pagina: int = CARATTERI_DEFAULT,
    usa_curl: bool = False,
    usa_browser: bool = False,
    browser_visibile: bool = False,
) -> dict:
    """Analisi SEO a campione del sito `url`; vedi la docstring del modulo.
    I limiti sono accettati entro un tetto massimo (`caratteri_per_pagina` e'
    la lunghezza dell'estratto di testo di ogni pagina, 0 = nessun estratto).

    Metodi, dal piu' leggero: richieste HTTP (o curl, se `usa_curl`); se la home
    risponde 403/429 o sembra costruita con JavaScript e il browser e' attivo
    (`usa_browser` o SEO_ANALISI_USA_BROWSER=1), si riprova con un Chromium vero,
    dopo aver aspettato il Retry-After; se non basta, restano le pagine salvate
    (analizza_pagine_salvate). Il report dice il `metodo` usato. In caso di
    problemi prevedibili restituisce {"errore": ...} invece di sollevare."""
    max_categorie = max(0, min(max_categorie, TETTO_CATEGORIE))
    max_prodotti = max(0, min(max_prodotti, TETTO_PRODOTTI))
    caratteri_per_pagina = max(0, min(caratteri_per_pagina, TETTO_CARATTERI))
    visibile = browser_visibile or os.environ.get("SEO_ANALISI_BROWSER_VISIBILE") == "1"
    con_browser = visibile or usa_browser or os.environ.get("SEO_ANALISI_USA_BROWSER") == "1"
    try:
        try:
            report = _analizza(
                url,
                max_categorie,
                max_prodotti,
                caratteri_per_pagina,
                usa_curl,
                ritenta_dopo_429=not con_browser,
            )
        except SitoBloccato as bloccato:
            if not con_browser:
                raise ErroreAnalisi(f"{bloccato}. {_SUGGERIMENTO_BROWSER}") from bloccato
            # Il sito ha chiesto di aspettare: lo si fa prima di qualsiasi altra richiesta.
            time.sleep(min(bloccato.retry_after or 0, RETRY_AFTER_MASSIMO_SECONDI))
            return _analizza_con_browser(
                url,
                max_categorie,
                max_prodotti,
                caratteri_per_pagina,
                "il sito rifiuta le richieste automatiche semplici",
                visibile,
            )
        report["metodo"] = "curl" if usa_curl else "http"
        if con_browser and _sembra_costruito_con_js(report):
            try:
                return _analizza_con_browser(
                    url,
                    max_categorie,
                    max_prodotti,
                    caratteri_per_pagina,
                    "le pagine sembrano costruite con JavaScript",
                    visibile,
                )
            except ErroreAnalisi as errore:
                report["avvisi"].append(f"Provato anche con il browser, senza riuscirci: {errore}")
        return report
    except ErroreAnalisi as errore:
        return {"errore": str(errore)}


# --- pagine salvate dall'utente ---------------------------------------------

_ESTENSIONI_HTML = (".html", ".htm", ".xhtml")
TETTO_PAGINE_SALVATE = 40


def _file_html(percorsi: list[str]) -> list[Path]:
    trovati: list[Path] = []
    for percorso in percorsi:
        voce = Path(percorso).expanduser()
        if voce.is_dir():
            trovati += sorted(
                f for f in voce.iterdir() if f.is_file() and f.suffix.lower() in _ESTENSIONI_HTML
            )
        elif voce.is_file() and voce.suffix.lower() in _ESTENSIONI_HTML:
            trovati.append(voce)
        else:
            raise ErroreAnalisi(
                f"{percorso}: non e' un file .html/.htm ne' una cartella che ne contiene"
            )
    unici = list(dict.fromkeys(trovati))
    if not unici:
        raise ErroreAnalisi("Nessun file .html trovato nei percorsi indicati")
    return unici[:TETTO_PAGINE_SALVATE]


def _leggi_html(file: Path) -> str:
    with file.open("rb") as aperto:
        dati = aperto.read(MAX_BYTE)
    try:
        return dati.decode("utf-8")
    except UnicodeDecodeError:
        return dati.decode("cp1252", errors="replace")


def _tipo_pagina_salvata(pagina: dict) -> str:
    """Tipo dedotto dall'indirizzo che la pagina dichiara e, se non basta, dai
    suoi dati strutturati."""
    percorso = urlsplit(pagina["url"]).path
    if urlsplit(pagina["url"]).scheme in ("http", "https") and percorso in ("", "/"):
        return "home"
    tipo = _tipo_da_percorso(pagina["url"])
    if tipo:
        return tipo
    schema = set(pagina["dati_strutturati"])
    if schema & {"Product", "ProductGroup"}:
        return "prodotto"
    if schema & {"CollectionPage", "OfferCatalog", "ItemList"}:
        return "categoria"
    return "altro"


def _analizza_salvate(percorsi: list[str], sito: str, max_caratteri: int) -> dict:
    pagine: list[dict] = []
    avvisi = [
        "Analisi di pagine salvate dall'utente: nessuna richiesta al sito, nessuna sitemap; "
        "il campione e' quello che e' stato salvato."
    ]
    senza_indirizzo = 0
    origine = ""
    for file in _file_html(percorsi):
        testo = _leggi_html(file)
        prima, _ = _estrai_pagina(testo, file.as_uri(), "altro", "")
        url = prima["canonical"] or prima["og_url"]
        if urlsplit(url).scheme not in ("http", "https"):
            url = file.as_uri()
            senza_indirizzo += 1
        host = _host_base(url)
        pagina, _ = _estrai_pagina(testo, url, "altro", host)
        pagina["tipo"] = _tipo_pagina_salvata(pagina)
        if host and not origine:
            parti = urlsplit(url)
            origine = f"{parti.scheme}://{parti.netloc}"
        pagine.append(pagina)

    if senza_indirizzo:
        avvisi.append(
            f"{senza_indirizzo} pagine non dichiarano il proprio indirizzo (canonical/og:url): "
            "tipo dedotto solo dai dati strutturati, e non e' possibile riconoscere la home."
        )
    for home in (p for p in pagine if p["tipo"] == "home"):
        avvisi.extend(_avviso_javascript(home))
    origine = origine or sito.strip() or "pagine_salvate"
    return _chiudi_analisi(origine, pagine, [], None, {}, avvisi, max_caratteri, in_rete=False)


def analizza_pagine_salvate(
    percorsi: list[str],
    sito: str = "",
    caratteri_per_pagina: int = CARATTERI_DEFAULT,
) -> dict:
    """Stessa analisi di analizza_seo_sito su pagine .html salvate dall'utente
    dal proprio browser (file singoli o cartelle), senza nessuna richiesta di
    rete. Per i siti che non vogliono essere letti da strumenti automatici o che
    costruiscono le pagine con JavaScript. Il tipo di pagina (home, categoria,
    prodotto) si deduce dall'indirizzo che la pagina dichiara; `sito` e' solo
    un'etichetta per le pagine che non lo dichiarano."""
    caratteri_per_pagina = max(0, min(caratteri_per_pagina, TETTO_CARATTERI))
    try:
        return _analizza_salvate(percorsi, sito, caratteri_per_pagina)
    except (ErroreAnalisi, OSError) as errore:
        return {"errore": str(errore)}
