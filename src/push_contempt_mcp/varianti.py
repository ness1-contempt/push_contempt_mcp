"""Riga "varianti:" nel file di testo di un prodotto, letta in modo deterministico.

Formato (una riga sola, attributi separati da "|", valori separati da virgola):

    varianti: Colore: Nero, Bianco | Memoria: 256 GB, 512 GB

Qui non c'e' nessuna interpretazione: o la riga e' scritta cosi' e si legge, o
si restituiscono errori chiari. Quando le varianti non sono su questa riga ma
descritte nel testo libero, le ricava l'assistente (e l'utente le controlla
nell'anteprima di crea_prodotto_variabile): questo modulo non ci prova.
"""

import re

_RIGA = re.compile(
    r"^[ \t]*varianti[ \t]*:[ \t]*(?P<contenuto>.*?)[ \t]*$", re.IGNORECASE | re.MULTILINE
)


def trova_riga_varianti(testo: str | None) -> str | None:
    """Il contenuto della prima riga che comincia con "varianti:" (senza la
    parola), o None se non c'e'. Una parola "varianti" dentro una frase non
    conta: la riga deve cominciare con "varianti:"."""
    if not testo:
        return None
    trovata = _RIGA.search(testo)
    return trovata.group("contenuto") if trovata else None


def analizza_riga_varianti(riga: str) -> dict:
    """Attributi e valori di una riga di varianti.

    Restituisce `{"attributi": [{"nome": ..., "valori": [...]}], "errori": [...]}`.
    Con errori non vuoti gli attributi vanno ignorati. Controlla solo la forma:
    valori doppi, troppe combinazioni e il resto li controlla il plugin.
    """
    errori: list[str] = []
    attributi: list[dict] = []
    if not riga or not riga.strip():
        return {"attributi": [], "errori": ["La riga delle varianti e' vuota."]}

    for posizione, parte in enumerate(riga.split("|"), start=1):
        if ":" not in parte:
            errori.append(
                f"Attributo n. {posizione} («{parte.strip()}»): manca il due punti fra il nome "
                "e i valori (formato «Colore: Nero, Bianco»)."
            )
            continue
        nome, _, elenco = parte.partition(":")
        nome = " ".join(nome.split())
        valori = [" ".join(valore.split()) for valore in elenco.split(",")]
        if not nome:
            errori.append(f"Attributo n. {posizione}: manca il nome prima del due punti.")
            continue
        if any(valore == "" for valore in valori):
            errori.append(
                f"Attributo «{nome}»: c'e' un valore vuoto (virgola in piu' o elenco mancante)."
            )
            continue
        attributi.append({"nome": nome, "valori": valori})

    if errori:
        return {"attributi": [], "errori": errori}
    return {"attributi": attributi, "errori": []}


def varianti_dal_testo(testo: str | None) -> dict | None:
    """La riga delle varianti di un testo, gia' letta: `{"riga", "attributi",
    "errori"}`, oppure None se il testo non ha nessuna riga "varianti:"."""
    riga = trova_riga_varianti(testo)
    if riga is None:
        return None
    return {"riga": riga, **analizza_riga_varianti(riga)}
