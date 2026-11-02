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
from push_contempt_mcp.varianti import varianti_dal_testo

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
    return {_normalizza_nome(p["titolo"]) for p in prodotti if p["stato"] != "trash"}


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


def _sottocartelle(cartella: Path) -> list[Path]:
    return sorted(v for v in cartella.iterdir() if v.is_dir() and not v.name.startswith("."))


def _ha_file_prodotto(cartella: Path) -> bool:
    """La cartella ha foto o un file .txt (i file di un prodotto)."""
    immagini, testo = _file_prodotto(cartella)
    return bool(immagini) or testo is not None


def _contiene_prodotti(cartella: Path) -> bool:
    """La cartella, o una cartella sotto di lei, e' un prodotto."""
    return _ha_file_prodotto(cartella) or any(
        _contiene_prodotti(f) for f in _sottocartelle(cartella)
    )


def _cerca_prodotti(cartella: Path, percorso: list[str], trovati: list, da_controllare: list):
    """Visita l'albero: una cartella con foto o .txt e' un prodotto e il percorso delle
    cartelle sopra di lei e' il suo percorso di categorie; una cartella con solo
    sottocartelle e' una categoria. Casi dubbi vanno in `da_controllare`."""
    for sub in _sottocartelle(cartella):
        nuovo = [*percorso, sub.name]
        figli = _sottocartelle(sub)
        ha_file = _ha_file_prodotto(sub)
        figli_con_prodotti = any(_contiene_prodotti(f) for f in figli)

        if ha_file and figli_con_prodotti:
            da_controllare.append(
                {
                    "cartella": str(sub),
                    "motivo": "Ha foto o testo e anche sottocartelle con altri prodotti: non so "
                    "se e' un prodotto o una categoria. Separa le due cose.",
                }
            )
        elif ha_file or (not figli and percorso):
            # Un prodotto (anche una cartella vuota, che segnaliamo piu' sotto).
            if not percorso:
                da_controllare.append(
                    {
                        "cartella": str(sub),
                        "motivo": "E' un prodotto fuori da una cartella di categoria: mettilo "
                        "dentro la cartella della sua categoria.",
                    }
                )
            else:
                trovati.append((sub, percorso))
        elif figli:
            _cerca_prodotti(sub, nuovo, trovati, da_controllare)


def _nome_in_conflitto(percorso: list[str], conflitti: list[dict]) -> list[str]:
    """I nomi di categoria in conflitto fra cartelle che toccano questo percorso."""

    def chiave(testo: str) -> str:
        return " ".join(testo.lower().split())

    suoi = {chiave(" > ".join(percorso[: i + 1])) for i in range(len(percorso))}
    return [
        conflitto["nome"]
        for conflitto in conflitti
        if any(chiave(posto) in suoi for posto in conflitto["posti"])
    ]


def scansiona_cartella_prodotti(percorso_cartella: str) -> dict:
    """Confronta la cartella dei prodotti con il catalogo WooCommerce e divide i prodotti
    trovati in nuovi e già presenti.

    La struttura delle cartelle rispecchia l'albero delle categorie di WooCommerce, a
    qualsiasi profondità: `<cartella>/Indumenti/Magliette/Maglietta rossa/` (con foto e
    un .txt) è il prodotto «Maglietta rossa» nella categoria Magliette, dentro Indumenti.
    Una cartella con foto o .txt è un prodotto; le cartelle sopra, fino alla radice, sono
    il suo `percorso_categoria`. Il confronto coi prodotti esistenti è per nome
    normalizzato (minuscolo, senza accenti/punteggiatura) e ignora il cestino.

    Non crea né modifica nulla. Per ciascun prodotto nuovo restituisce i materiali grezzi
    (categoria, percorso di categorie, percorsi immagini, testo non interpretato): tocca a
    chi chiama questo tool leggere il testo, capire prezzo e descrizione, e poi chiamare
    `crea_prodotto` (passando `percorso_categoria`) — non è un'estrazione deterministica,
    quindi questo tool non ci prova.

    Unica eccezione: la riga `varianti: Colore: Nero, Bianco | Memoria: 256 GB, 512 GB`
    (se c'e' nel testo) viene letta qui in modo deterministico e restituita in `varianti`
    (`riga`, `attributi`, `errori`); senza la riga `varianti` e' None e le eventuali
    varianti sono da ricavare dal testo. Per un prodotto con varianti si usa
    `crea_prodotto_variabile`.

    CATEGORIE: un nome di categoria deve esistere UNA volta sola in tutto l'albero. Il
    tool confronta i percorsi con le categorie del sito (`piano_categorie`: per ogni livello
    esiste / da_creare / conflitto) e segnala in `problemi_categorie` e in `avviso` i casi
    in cui lo stesso nome compare in due punti (fra le cartelle o fra cartelle e sito):
    per quei prodotti non creare niente e riporta il problema all'utente. Le cartelle dubbie
    (file e sottocartelle insieme, prodotto senza categoria) sono in `da_controllare` e non
    vanno caricate.
    """
    radice = Path(percorso_cartella)
    if not radice.is_dir():
        return {"errore": f"Cartella non trovata: {percorso_cartella}"}

    esistenti = _nomi_prodotti_esistenti()
    trovati: list[tuple[Path, list[str]]] = []
    da_controllare: list[dict] = []
    _cerca_prodotti(radice, [], trovati, da_controllare)

    nuovi = []
    gia_presenti = []
    for cartella_prodotto, percorso in trovati:
        nome_prodotto = cartella_prodotto.name
        if _normalizza_nome(nome_prodotto) in esistenti:
            gia_presenti.append(nome_prodotto)
            continue

        immagini, testo = _file_prodotto(cartella_prodotto)
        nuovi.append(
            {
                "nome": nome_prodotto,
                "categoria": percorso[-1],
                "percorso_categoria": percorso,
                "percorsi_immagini": immagini,
                "testo_grezzo": testo,
                "varianti": varianti_dal_testo(testo),
                "avviso": None
                if (immagini and testo)
                else "Mancano foto o il file .txt: controllare prima di caricare.",
            }
        )

    risultato = {
        "cartella": str(radice),
        "nuovi": nuovi,
        "gia_presenti": gia_presenti,
        "da_controllare": da_controllare,
    }
    risultato.update(_confronta_categorie(nuovi))
    return risultato


def _confronta_categorie(nuovi: list[dict]) -> dict:
    """Confronta i percorsi di categorie dei prodotti nuovi con l'albero del sito (una
    sola chiamata al plugin, sola lettura) e segna i prodotti con un problema."""
    if not nuovi:
        return {"categorie_da_creare": [], "conflitti_categorie": []}
    percorsi = []
    for prodotto in nuovi:
        if prodotto["percorso_categoria"] not in percorsi:
            percorsi.append(prodotto["percorso_categoria"])
    try:
        verifica = product_tools.verifica_categorie(percorsi)
    except Exception as errore:  # noqa: BLE001 - la scansione resta utile anche senza il confronto
        for prodotto in nuovi:
            prodotto["piano_categorie"] = None
            prodotto["problemi_categorie"] = []
        return {
            "categorie_da_creare": [],
            "conflitti_categorie": [],
            "avviso_categorie": f"Confronto con le categorie del sito non riuscito: {errore}",
        }

    piani = {tuple(voce["percorso"]): voce for voce in verifica["percorsi"]}
    conflitti = verifica.get("conflitti", [])
    da_creare: list[str] = []
    for prodotto in nuovi:
        voce = piani.get(tuple(prodotto["percorso_categoria"]), {"livelli": [], "errori": []})
        problemi = list(voce["errori"])
        for nome in _nome_in_conflitto(prodotto["percorso_categoria"], conflitti):
            problemi.append(f"Il nome «{nome}» compare in piu' punti delle cartelle.")
        prodotto["piano_categorie"] = voce["livelli"]
        prodotto["problemi_categorie"] = problemi
        if problemi:
            prodotto["avviso"] = "PROBLEMA CON LE CATEGORIE, non caricare: " + " ".join(problemi)
        for livello in voce["livelli"]:
            if livello["stato"] == "da_creare" and livello["percorso"] not in da_creare:
                da_creare.append(livello["percorso"])
    return {"categorie_da_creare": da_creare, "conflitti_categorie": conflitti}
