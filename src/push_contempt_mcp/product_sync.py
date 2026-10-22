"""Scansione della cartella prodotti locale e confronto con il catalogo WooCommerce.

Solo lettura: non crea né modifica nulla. Struttura attesa
`<cartella>/<Categoria>/<Prodotto>/` con le foto e un file .txt in testo
libero (descrizione/prezzo). Qui c'è solo la parte deterministica (scansione
filesystem, confronto nomi col DB): l'estrazione del prezzo dal testo e la
scrittura della descrizione impaginata sono un compito per l'AI che chiama
questo tool e poi `crea_prodotto`, non per questo modulo.
"""

import re
import unicodedata
from pathlib import Path

from push_contempt_mcp import product_tools

ESTENSIONI_IMMAGINE = {".jpg", ".jpeg", ".png", ".webp"}
FILE_IGNORATI = {"media_ids.json"}


def _normalizza_nome(nome: str) -> str:
    """Nome comparabile: minuscolo, senza accenti, solo lettere/numeri.

    Evita che un prodotto già caricato con una grafia leggermente diversa
    (maiuscole, accenti, punteggiatura) risulti "nuovo" solo per questo.
    """
    nome = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", nome.lower())


def _nomi_prodotti_esistenti() -> set[str]:
    prodotti = product_tools.elenco_prodotti(limite=-1)
    return {
        _normalizza_nome(p["titolo"]) for p in prodotti if p["stato"] != "trash"
    }


def _file_prodotto(cartella: Path) -> tuple[list[str], str | None]:
    """Foto e testo dentro la cartella di un prodotto, ignorando file di
    servizio (nascosti, script .py, media_ids.json, __pycache__...)."""
    immagini: list[str] = []
    testo: str | None = None
    for voce in sorted(cartella.iterdir()):
        if voce.name.startswith(".") or voce.name in FILE_IGNORATI:
            continue
        if voce.is_dir():
            continue
        suffisso = voce.suffix.lower()
        if suffisso in ESTENSIONI_IMMAGINE:
            immagini.append(str(voce))
        elif suffisso == ".txt":
            testo = voce.read_text(encoding="utf-8")
    return immagini, testo


def scansiona_cartella_prodotti(percorso_cartella: str) -> dict:
    """Confronta `<percorso_cartella>/<Categoria>/<Prodotto>/` con il catalogo
    WooCommerce e divide i prodotti trovati in nuovi e già presenti.

    Il nome prodotto è il nome della sua sottocartella, la categoria è la
    cartella superiore. Il confronto coi prodotti esistenti è per nome
    normalizzato (minuscolo, senza accenti/punteggiatura) e ignora il cestino.

    Non crea né modifica nulla. Per ciascun prodotto nuovo restituisce i
    materiali grezzi (categoria, percorsi immagini, testo non interpretato):
    tocca a chi chiama questo tool leggere il testo, capire prezzo e
    descrizione, e poi chiamare `crea_prodotto` — non è un'estrazione
    deterministica, quindi questo tool non ci prova.
    """
    radice = Path(percorso_cartella)
    if not radice.is_dir():
        return {"errore": f"Cartella non trovata: {percorso_cartella}"}

    esistenti = _nomi_prodotti_esistenti()
    nuovi = []
    gia_presenti = []

    for cartella_categoria in sorted(radice.iterdir()):
        if not cartella_categoria.is_dir() or cartella_categoria.name.startswith("."):
            continue
        for cartella_prodotto in sorted(cartella_categoria.iterdir()):
            if not cartella_prodotto.is_dir() or cartella_prodotto.name.startswith("."):
                continue

            nome_prodotto = cartella_prodotto.name
            if _normalizza_nome(nome_prodotto) in esistenti:
                gia_presenti.append(nome_prodotto)
                continue

            immagini, testo = _file_prodotto(cartella_prodotto)
            nuovi.append(
                {
                    "nome": nome_prodotto,
                    "categoria": cartella_categoria.name,
                    "percorsi_immagini": immagini,
                    "testo_grezzo": testo,
                    "avviso": None
                    if (immagini and testo)
                    else "Mancano foto o il file .txt: controllare prima di caricare.",
                }
            )

    return {
        "cartella": str(radice),
        "nuovi": nuovi,
        "gia_presenti": gia_presenti,
    }
