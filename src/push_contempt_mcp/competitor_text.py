"""Analisi del testo delle pagine di un sito: formule ripetute su tutto il sito,
vocabolario, segnali di stile e di intenzione. Solo funzioni pure (nessuna
rete), usate da competitor_seo.py.

Il codice estrae quello che si puo' misurare (parole e coppie di parole
ricorrenti, quanto spesso compaiono inviti all'acquisto o rassicurazioni,
quanto sono tecniche le descrizioni, tono, lunghezza delle frasi). Il
giudizio su intenzione e modo di descrivere i prodotti lo da' l'assistente AI
leggendo i brevi estratti: qui non c'e' nessuna AI.

Le formule che si ripetono identiche su meta' delle pagine sono il template
del sito (menu, avvisi, spedizioni, "aggiungi al carrello"): vengono tolte da
estratti e vocabolario, che cosi' descrivono i contenuti veri dei prodotti, e
riportate a parte come "messaggi ripetuti".
"""

import math
import re
from collections import Counter

MAX_MESSAGGI_RIPETUTI = 8
MAX_CARATTERI_MESSAGGIO = 140

PAROLE_VUOTE = frozenset(
    """
    della delle degli dello dell alla alle agli allo dalla dalle dagli dallo nella nelle negli
    nello sulla sulle sugli sullo come anche con per tra fra che non una uno gli del dei nel
    nei sul sui questo questa questi queste quello quella quelli tutti tutte tutto ogni
    dal dai piu piu' più pure poi gia già sono sia siamo hai ha ho hanno sei essere stato
    suo sua suoi sue loro cui dove quando mentre perche perché cosi così molto molti molte
    solo anche ancora oltre senza sotto sopra dopo prima fino verso circa invece dello
    the and for with from your you our this that are not all new can will has have more
    one its their been was were but also any only each than then them they into out over
    shop store online home sito pagina
    """.split()
)

_UNITA = r"gb|tb|mb|mp|mah|hz|ghz|mhz|mm|cm|kg|pollici|inch|fps|nm|wh|w|v"
_RE_MISURA = re.compile(rf"\b\d[\d.,]*\s?({_UNITA})\b")
_RE_TOKEN = re.compile(r"[a-zàèéìòù0-9][a-zàèéìòù0-9+\-]+")
_RE_SEGMENTO = re.compile(r"[.!?;:\n|•·()\[\]]+")
_RE_FRASE = re.compile(r"[.!?]+(?:\s|$)")

# Elenchi di formule, in italiano e inglese: volutamente corti e di uso comune.
# Contano quanto spesso compaiono, non decidono da soli l'intenzione.
_SEGNALI = {
    "inviti_all_azione": (
        r"\b(?:acquista\w*|compra\w*|ordina\w*|aggiungi al carrello|scopri\w*|prenota\w*"
        r"|richiedi\w*|contattaci|approfitta\w*|non perdere|buy now|add to cart|shop now"
        r"|order now)\b"
    ),
    "fiducia_e_servizio": (
        r"\b(?:spedizione (?:gratuita|gratis|rapida|veloce|express)"
        r"|spedizion\w*|consegn\w*|ritiro|pagament\w*|resi?|rimbors\w*|garanzia"
        r"|ufficial\w*|original\w*|assistenza|chat|recension\w*"
        r"|free shipping|shipping|delivery|payment|warranty|returns?|support)\b"
    ),
    "offerta_e_urgenza": (
        r"(?:\b(?:offert\w*|sconto|sconti|risparmi\w*|promo\w*|solo oggi|ultimi pezzi"
        r"|ultimi disponibili|limitat\w*|disponibil\w*|in stock|discount|limited)\b"
        r"|-\s?\d+\s?%)"
    ),
    "confronto_e_guida": (
        r"\b(?:confront\w*|differenz\w*|come scegliere|guida|quale|migliore|migliori"
        r"|alternativ\w*|perch[eé]|vs|versus|domande frequenti|faq)\b"
    ),
    "rivolto_al_cliente": r"\b(?:tu|ti|tuo|tua|tuoi|tue|you|your)\b",
    "parla_di_se": r"\b(?:noi|nostro|nostra|nostri|nostre|we|our)\b",
}
_RE_SEGNALI = {nome: re.compile(modello) for nome, modello in _SEGNALI.items()}


_RE_IMPORTO = re.compile(r"(?:[€$£]\s?\d[\d.,]*|\d[\d.,]*\s?(?:€|(?:eur|euro)\b))", re.IGNORECASE)


def _norm(testo: str) -> str:
    """Testo in minuscolo, con gli spazi ridotti e gli importi in valuta sostituiti da
    "€#": cosi' "Prezzo di listino €16,50" e "Prezzo di listino €19,90" risultano
    lo stesso blocco (etichetta del sito) e non due contenuti diversi."""
    return " ".join(_RE_IMPORTO.sub("€#", testo.lower()).split())


def _termine_valido(token: str) -> bool:
    if token in PAROLE_VUOTE or token.isdigit():
        return False
    return len(token) >= 3 or (any(c.isdigit() for c in token) and any(c.isalpha() for c in token))


# --- template del sito -------------------------------------------------------


# "ETICHETTA: valore" (es. "CONDIZIONI: 9/10"): un campo della scheda, anche se il
# valore si ripete su molti prodotti. Non e' template.
_RE_ETICHETTA_VALORE = re.compile(r"^[^:]{2,40}:\s*\S.{0,40}$")


def _e_campo_della_scheda(blocco: str) -> bool:
    return len(blocco.split()) <= 8 and bool(_RE_ETICHETTA_VALORE.match(blocco))


def blocchi_ripetuti(blocchi_per_pagina: list[list[str]]) -> dict[str, int]:
    """Blocchi di testo identici presenti in almeno meta' delle pagine (e in non
    meno di 3): il template del sito. Con meno di 4 pagine non si decide:
    nessun blocco e' considerato ripetuto. Restituisce blocco normalizzato ->
    numero di pagine."""
    if len(blocchi_per_pagina) < 4:
        return {}
    conteggio: Counter = Counter()
    for blocchi in blocchi_per_pagina:
        conteggio.update({_norm(b) for b in blocchi if not _e_campo_della_scheda(b)})
    soglia = max(3, math.ceil(len(blocchi_per_pagina) / 2))
    return {blocco: n for blocco, n in conteggio.items() if n >= soglia}


# Frasi di interfaccia e accessibilita' (non messaggi commerciali) che i temi
# ripetono ovunque.
_RE_RUMORE_INTERFACCIA = re.compile(
    r"si apre in una nuova finestra|opens in a new window|aggiornamento completo della pagina"
    r"|full page refresh|vai direttamente ai contenuti|skip to content|consenso ai cookie"
    r"|cookie consent",
    re.IGNORECASE,
)


def messaggi_ripetuti(ripetuti: dict[str, int]) -> list[dict]:
    """I blocchi ripetuti che sembrano messaggi (da 3 a 25 parole), i piu'
    diffusi per primi: inviti all'acquisto, spedizioni, resi, garanzie. Le frasi
    di interfaccia (accessibilita', cookie) sono escluse."""
    messaggi = [
        (b, n)
        for b, n in ripetuti.items()
        if 3 <= len(b.split()) <= 25 and not _RE_RUMORE_INTERFACCIA.search(b)
    ]
    messaggi.sort(key=lambda coppia: -coppia[1])
    return [
        {"testo": blocco[:MAX_CARATTERI_MESSAGGIO], "pagine": n}
        for blocco, n in messaggi[:MAX_MESSAGGI_RIPETUTI]
    ]


def senza_ripetuti(blocchi: list[str], ripetuti: dict[str, int]) -> list[str]:
    return [b for b in blocchi if _norm(b) not in ripetuti]


def intestazioni_ripetute(liste: list[list[str]]) -> set[str]:
    """Intestazioni (H2) presenti in almeno meta' delle pagine (e in non meno di
    3), come "Consenso ai cookie" o "Lingua": sono del template, non del
    contenuto. Anche qui servono almeno 4 pagine."""
    if len(liste) < 4:
        return set()
    conteggio: Counter = Counter()
    for intestazioni in liste:
        conteggio.update({_norm(h) for h in intestazioni})
    soglia = max(3, math.ceil(len(liste) / 2))
    return {h for h, n in conteggio.items() if n >= soglia}


# --- estratto e segnali di una pagina ----------------------------------------


def estratto(blocchi_propri: list[str], max_caratteri: int, escludi: set[str] = frozenset()) -> str:
    """Primi blocchi di testo "vero", tagliati a fine parola: abbastanza per
    capire tono e intenzione, non per copiare una descrizione. Si tengono anche
    le righe brevi ("TAGLIA: M"), che in molte schede sono il contenuto; si
    saltano prezzi, ripetizioni dentro la pagina e i testi in `escludi` (titoli)."""
    if max_caratteri <= 0:
        return ""
    scelti: list[str] = []
    visti: set[str] = set(escludi)
    lunghezza = 0
    for blocco in blocchi_propri:
        chiave = _norm(blocco)
        if chiave in visti or len(chiave) < 3 or _e_prezzo(chiave):
            continue
        visti.add(chiave)
        scelti.append(blocco)
        lunghezza += len(blocco) + 1
        if lunghezza >= max_caratteri:
            break
    testo = " ".join(scelti)
    if len(testo) <= max_caratteri:
        return testo
    return testo[:max_caratteri].rsplit(" ", 1)[0] + "…"


def _e_prezzo(chiave: str) -> bool:
    """Blocco breve che contiene un importo (gia' normalizzato a "€#")."""
    return "€#" in chiave and len(chiave.split()) <= 8


def segnali_pagina(blocchi: list[str], blocchi_propri: list[str]) -> dict:
    """Conteggi grezzi per una pagina. Le formule si contano su tutto il testo
    (anche il template: una spedizione gratuita nel footer fa parte di come il
    sito vende); le frasi sul solo testo proprio."""
    testo = "\n".join(blocchi).lower()
    proprio = "\n".join(blocchi_propri)
    frasi = [f for f in _RE_FRASE.split(proprio) if f.split()]
    conteggi = {nome: len(r.findall(testo)) for nome, r in _RE_SEGNALI.items()}
    conteggi["misure_tecniche"] = len(_RE_MISURA.findall(testo))
    conteggi["esclamazioni"] = testo.count("!")
    conteggi["domande"] = testo.count("?")
    return {
        "parole": len(testo.split()),
        "frasi": len(frasi),
        "parole_nelle_frasi": sum(len(f.split()) for f in frasi),
        **conteggi,
    }


def riepilogo_stile(segnali: list[dict]) -> dict:
    """Segnali di piu' pagine sommati e riportati ogni 1000 parole."""
    parole = sum(s["parole"] for s in segnali)
    frasi = sum(s["frasi"] for s in segnali)

    def ogni_mille(chiave: str) -> float:
        return round(1000 * sum(s[chiave] for s in segnali) / parole, 1) if parole else 0.0

    chiavi = [*_SEGNALI, "misure_tecniche", "esclamazioni", "domande"]
    return {
        "ogni_1000_parole": {chiave: ogni_mille(chiave) for chiave in chiavi},
        "lunghezza_media_frase_in_parole": (
            round(sum(s["parole_nelle_frasi"] for s in segnali) / frasi, 1) if frasi else 0.0
        ),
    }


# --- vocabolario -------------------------------------------------------------


def vocabolario(testi: list[str]) -> dict:
    """Termini, coppie di parole adiacenti e unita' di misura presenti in almeno
    il 20% delle pagine (e in non meno di 2), ordinati per diffusione. I testi
    sono quelli propri delle pagine (senza template), con i blocchi separati da
    a capo; le coppie non attraversano punteggiatura."""
    minimo = max(2, math.ceil(0.2 * len(testi)))
    pagine_termine: Counter = Counter()
    occorrenze: Counter = Counter()
    pagine_coppia: Counter = Counter()
    pagine_misura: Counter = Counter()
    for testo in testi:
        minuscolo = testo.lower()
        termini: set[str] = set()
        coppie: set[str] = set()
        for segmento in _RE_SEGMENTO.split(minuscolo):
            token = _RE_TOKEN.findall(segmento)
            validi = [_termine_valido(t) for t in token]
            for i, termine in enumerate(token):
                if not validi[i]:
                    continue
                termini.add(termine)
                occorrenze[termine] += 1
                if i + 1 < len(token) and validi[i + 1]:
                    coppie.add(f"{termine} {token[i + 1]}")
        pagine_termine.update(termini)
        pagine_coppia.update(coppie)
        pagine_misura.update(set(_RE_MISURA.findall(minuscolo)))

    def migliori(conteggio: Counter, quanti: int, chiave: str, secondario=None) -> list[dict]:
        ordinati = sorted(
            (voce for voce in conteggio.items() if voce[1] >= minimo),
            key=lambda voce: (-voce[1], -(secondario[voce[0]] if secondario else 0), voce[0]),
        )
        return [{chiave: voce, "pagine": n} for voce, n in ordinati[:quanti]]

    return {
        "termini": migliori(pagine_termine, 25, "termine", occorrenze),
        "coppie_di_parole": migliori(pagine_coppia, 15, "coppia"),
        "unita_di_misura": migliori(pagine_misura, 8, "unita"),
    }


# --- insieme -----------------------------------------------------------------


def analizza_testi(pagine: list[dict], max_caratteri: int) -> dict:
    """Arricchisce le pagine (in place) con `estratto`, `_segnali` e
    `_testo_proprio` (campi interni, usati per i riepiloghi), toglie dalle
    intestazioni H2 quelle del template e consuma `_blocchi` (contenuto dopo
    l'H1) e `_blocchi_tutti` (tutto il testo, usato per riconoscere il template,
    perche' avvisi e banner stanno prima dell'H1). Restituisce i messaggi
    ripetuti del sito e, per ogni tipo di pagina diverso dalla home,
    stile/intenzione e vocabolario."""
    ripetuti = blocchi_ripetuti([p["_blocchi_tutti"] for p in pagine])
    intestazioni = intestazioni_ripetute([p["h2"] for p in pagine])
    for pagina in pagine:
        blocchi = pagina.pop("_blocchi")
        pagina.pop("_blocchi_tutti")
        propri = senza_ripetuti(blocchi, ripetuti)
        pagina["h2"] = [h for h in pagina["h2"] if _norm(h) not in intestazioni]
        titoli = {_norm(t) for t in [pagina["titolo"], *pagina["h1"]] if t}
        pagina["estratto"] = estratto(propri, max_caratteri, titoli)
        pagina["_segnali"] = segnali_pagina(blocchi, propri)
        pagina["_testo_proprio"] = "\n".join(propri)

    per_tipo = {}
    for tipo in ("categoria", "prodotto"):
        gruppo = [p for p in pagine if p["tipo"] == tipo]
        if gruppo:
            per_tipo[tipo] = {
                "stile_e_intenzione": riepilogo_stile([p["_segnali"] for p in gruppo]),
                "vocabolario": vocabolario([p["_testo_proprio"] for p in gruppo]),
            }
    return {"messaggi_ripetuti_sul_sito": messaggi_ripetuti(ripetuti), "per_tipo": per_tipo}
