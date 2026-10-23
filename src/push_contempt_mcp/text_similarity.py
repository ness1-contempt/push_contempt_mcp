"""Controllo di somiglianza fra un testo nostro e i testi di un sito analizzato
con analizza_seo_sito: rende verificabile la regola "ispirarsi, non copiare".

Il punteggio va da 0 (nessuna somiglianza) a 9 (copia) e si calcola con regole
fisse, cosi' si puo' spiegare e ripetere:
- si confrontano sequenze di almeno 5 parole consecutive (maiuscole e
  punteggiatura ignorate);
- "copertura" = quota delle parole del nostro testo che fanno parte di una
  sequenza presente anche nei testi di riferimento;
- "sequenza piu' lunga" = la piu' lunga serie di parole identiche;
- il punteggio e' il piu' alto fra il livello della copertura e quello della
  sequenza piu' lunga (vedi _livello_copertura e _livello_sequenza).

Limite noto: specifiche tecniche e nomi di prodotto uguali ("display AMOLED da
6,7 pollici") fanno salire un po' il punteggio anche in un testo originale. Per
questo il risultato elenca i passaggi coincidenti: il giudizio finale e'
dell'utilizzatore, che sceglie fino a che punto della scala accetta (`soglia`).

I testi di riferimento sono quelli delle pagine analizzate, salvati in locale
(cartella della cache dell'utente, mai sul sito WordPress) da
analizza_seo_sito; si possono aggiungere testi a mano.
"""

import json
import os
import re
from datetime import date
from pathlib import Path

PAROLE_MINIME_SEQUENZA = 5
MAX_PASSAGGI = 5
MAX_FONTI = 3
MAX_CARATTERI_PASSAGGIO = 300
MAX_CARATTERI_PAGINA_SALVATA = 30_000

SIGNIFICATO = {
    0: "Nessuna sequenza di 5 o piu' parole in comune con i testi di riferimento.",
    1: "Coincidenze occasionali (formule comuni, specifiche tecniche).",
    2: "Poche coincidenze brevi.",
    3: "Qualche frase in comune.",
    4: "Diverse frasi in comune.",
    5: "Parti consistenti molto simili.",
    6: "Parti consistenti ricalcate.",
    7: "Buona parte del testo ricalcata, con qualche modifica.",
    8: "Riscrittura appena ritoccata.",
    9: "Copia.",
}


def _parole(testo: str) -> list[str]:
    return re.findall(r"\w+", testo.lower())


def _livello_copertura(copertura: float) -> int:
    if copertura <= 0:
        return 0
    for livello, limite in enumerate((0.02, 0.05, 0.10, 0.20, 0.35, 0.50, 0.70, 0.90), start=1):
        if copertura <= limite:
            return livello
    return 9


def _livello_sequenza(parole: int) -> int:
    for livello, minimo in (
        (6, 40),
        (5, 25),
        (4, 18),
        (3, 12),
        (2, 8),
        (1, PAROLE_MINIME_SEQUENZA),
    ):
        if parole >= minimo:
            return livello
    return 0


def _sequenze_comuni(nostre: list[str], loro: list[str], k: int) -> list[tuple[int, int]]:
    """Intervalli [inizio, fine) delle nostre parole che fanno parte di una
    sequenza di almeno k parole presente anche in `loro`, uniti quando si
    sovrappongono o si toccano."""
    if len(nostre) < k or len(loro) < k:
        return []
    presenti = {tuple(loro[i : i + k]) for i in range(len(loro) - k + 1)}
    intervalli: list[tuple[int, int]] = []
    for i in range(len(nostre) - k + 1):
        if tuple(nostre[i : i + k]) in presenti:
            if intervalli and i <= intervalli[-1][1]:
                intervalli[-1] = (intervalli[-1][0], i + k)
            else:
                intervalli.append((i, i + k))
    return intervalli


def controlla(
    testo: str, riferimenti: list[dict], soglia: int | None = None, k: int = PAROLE_MINIME_SEQUENZA
) -> dict:
    """Somiglianza di `testo` con i `riferimenti` ({"fonte": ..., "testo": ...}),
    da 0 a 9. Se `soglia` (0-9) e' data, dice anche se il testo la rispetta."""
    nostre = _parole(testo)
    if len(nostre) < k:
        return {
            "punteggio": 0,
            "significato": SIGNIFICATO[0],
            "avviso": f"Testo troppo corto per il confronto (meno di {k} parole).",
            **_esito(0, soglia),
        }

    coperte = [False] * len(nostre)
    per_fonte: list[tuple[str, int]] = []
    sequenze: list[tuple[int, int, str]] = []
    for riferimento in riferimenti:
        intervalli = _sequenze_comuni(nostre, _parole(riferimento["testo"]), k)
        parole_fonte = 0
        for inizio, fine in intervalli:
            parole_fonte += fine - inizio
            sequenze.append((inizio, fine, riferimento["fonte"]))
            for i in range(inizio, fine):
                coperte[i] = True
        if parole_fonte:
            per_fonte.append((riferimento["fonte"], parole_fonte))

    copertura = sum(coperte) / len(nostre)
    sequenze.sort(key=lambda s: s[0] - s[1])  # le piu' lunghe prima
    piu_lunga = sequenze[0][1] - sequenze[0][0] if sequenze else 0
    punteggio = max(_livello_copertura(copertura), _livello_sequenza(piu_lunga))

    passaggi: list[dict] = []
    usate: set[int] = set()
    for inizio, fine, fonte in sequenze:
        if len(passaggi) == MAX_PASSAGGI:
            break
        if any(i in usate for i in range(inizio, fine)):
            continue  # gia' mostrato (stessa zona del testo, altra fonte)
        usate.update(range(inizio, fine))
        passaggi.append(
            {
                "testo": " ".join(nostre[inizio:fine])[:MAX_CARATTERI_PASSAGGIO],
                "parole": fine - inizio,
                "fonte": fonte,
            }
        )
    per_fonte.sort(key=lambda f: -f[1])
    return {
        "punteggio": punteggio,
        "significato": SIGNIFICATO[punteggio],
        "copertura_percentuale": round(100 * copertura),
        "sequenza_piu_lunga_in_parole": piu_lunga,
        "passaggi_simili": passaggi,
        "fonti_piu_simili": [
            {"fonte": fonte, "parole_in_comune": n} for fonte, n in per_fonte[:MAX_FONTI]
        ],
        "confrontato_con": len(riferimenti),
        **_esito(punteggio, soglia),
    }


def _esito(punteggio: int, soglia: int | None) -> dict:
    if soglia is None:
        return {}
    return {"soglia": soglia, "accettabile": punteggio <= soglia}


# --- testi di riferimento salvati in locale ---------------------------------


def cartella_cache() -> Path:
    percorso = os.environ.get("SEO_ANALISI_CACHE_DIR")
    return (
        Path(percorso) if percorso else Path.home() / ".cache" / "push_contempt_mcp" / "seo_analisi"
    )


def _nome_file(sito: str) -> str:
    host = re.sub(r"^https?://", "", sito.strip().lower()).split("/")[0].removeprefix("www.")
    return re.sub(r"[^a-z0-9.-]", "_", host) + ".json"


def salva_corpus(sito: str, pagine: list[dict]) -> Path:
    """Salva i testi delle pagine analizzate (url, titolo, meta description,
    testo) per i confronti successivi. Solleva OSError se non puo' scrivere."""
    cartella = cartella_cache()
    cartella.mkdir(parents=True, exist_ok=True)
    percorso = cartella / _nome_file(sito)
    contenuto = {
        "sito": sito,
        "data": date.today().isoformat(),
        "pagine": [
            {
                "url": p["url"],
                "titolo": p["titolo"],
                "meta_description": p["meta_description"],
                "testo": p["testo"][:MAX_CARATTERI_PAGINA_SALVATA],
            }
            for p in pagine
        ],
    }
    percorso.write_text(json.dumps(contenuto, ensure_ascii=False), encoding="utf-8")
    return percorso


def carica_riferimenti(sito: str | None = None) -> list[dict]:
    """Testi salvati: quelli di `sito`, o di tutti i siti analizzati se None.
    Titolo e meta description di ogni pagina sono riferimenti a parte, cosi' si
    controlla anche la SEO scritta da noi."""
    cartella = cartella_cache()
    if sito:
        file = cartella / _nome_file(sito)
        files = [file] if file.exists() else []
    else:
        files = sorted(cartella.glob("*.json")) if cartella.exists() else []
    riferimenti: list[dict] = []
    for file in files:
        try:
            dati = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for pagina in dati.get("pagine", []):
            for campo, nome in (
                ("testo", ""),
                ("titolo", " (titolo)"),
                ("meta_description", " (meta description)"),
            ):
                if pagina.get(campo):
                    riferimenti.append({"fonte": pagina["url"] + nome, "testo": pagina[campo]})
    return riferimenti
