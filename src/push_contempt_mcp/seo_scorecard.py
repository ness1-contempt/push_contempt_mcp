"""Valutazione della struttura SEO di un sito analizzato, da 0 a 9, per area.

Serve a decidere se conviene prendere spunto da un sito: un concorrente che fa
male la SEO non e' un buon modello, ma puo' essere un buon modello solo su
alcune cose (Casual Bay ha una scheda a campi fissi che funziona, e meta
description e dati strutturati da evitare). Per questo il punteggio e' per area
(titoli, meta description, intestazioni, dati strutturati, contenuto, aspetti
tecnici) e c'e' poi un punteggio complessivo come riassunto.

Ogni area e' una media pesata di criteri misurabili sul campione di pagine
analizzato, e ogni criterio riporta la prova ("titoli fra 30 e 60 caratteri:
8 su 9"): il punteggio si puo' controllare riga per riga. Il giudizio e' solo
un riferimento per l'utilizzatore, non vincolante: decide lui se e per quali
aree usare il sito come ispirazione.

Oltre alla media dei criteri ci sono i "tetti": regole esplicite che limitano il voto
di un'area quando c'e' un difetto grave, qualunque sia la media (immagini senza ALT
oltre il 35% -> contenuto al massimo 6; H3 senza H2 su piu' della meta' delle pagine ->
intestazioni al massimo 6). Il report mostra sempre ogni tetto con la sua misura, anche
quando non scatta, e l'effetto che ha avuto. Le soglie sono costanti in testa al modulo.

Cosa NON misura: posizionamento, autorevolezza, velocita', qualita' dei testi
(solo struttura e quantita'). Funzioni pure: nessuna rete.
"""

# Soglie e pesi: tutto quello che si puo' voler cambiare e' qui.
TITOLO_MIN, TITOLO_MAX = 30, 60
META_MIN, META_MAX = 110, 160
PAROLE_PROPRIE_PIENE = 150  # descrizioni di prodotto con almeno cosi' tante parole: punteggio pieno
MARCHIO_COERENTE_DA = 0.8  # quota di titoli con lo stesso finale per dirli coerenti
PESI_AREE = {
    "titoli": 2,
    "meta_description": 2,
    "intestazioni": 1,
    "dati_strutturati": 2,
    "contenuto": 2,
    "tecnico": 0.5,  # HTTPS, canonical, lingua... sono di serie su ogni piattaforma moderna
}
RIGHE_SCHEDA_MIN = 3  # righe "etichetta: valore" per dire che la scheda e' organizzata
PAROLE_PROPRIE_MIN = 60  # in alternativa: abbastanza testo proprio

SIGNIFICATO = {
    0: "Struttura SEO quasi assente: non e' un modello.",
    1: "Molto carente: poco o nulla da imparare.",
    2: "Carente: pochi elementi in regola.",
    3: "Debole: parecchie lacune importanti.",
    4: "Insufficiente: meta' delle cose misurate non funziona.",
    5: "Discreta: base presente, con lacune evidenti.",
    6: "Buona: la maggior parte delle cose e' in regola.",
    7: "Molto buona: poche lacune.",
    8: "Ottima: struttura curata, lacune minori.",
    9: "Eccellente: modello su quasi tutti i punti misurati.",
}

# Tetti: un difetto grave limita il voto di un'area, qualunque sia la media dei criteri.
# Il report li mostra sempre (regola, misura, se scatta e con quale effetto).
ALT_MANCANTE_OLTRE = 0.35  # quota di immagini senza ALT oltre la quale scatta il tetto
TETTO_ALT = 6  # voto massimo dell'area contenuto
PAGINE_H3_SENZA_H2_OLTRE = 0.5  # quota di pagine con H3 ma senza H2 oltre la quale scatta
TETTO_GERARCHIA = 6  # voto massimo dell'area intestazioni

PAGINE_MINIME = 5  # sotto questo numero di pagine il punteggio complessivo non e' significativo

LIMITI = (
    "Valutazione della sola struttura, su un campione di pagine: non misura "
    "posizionamento, autorevolezza, velocita' ne' qualita' dei testi."
)


def _criterio(nome: str, valore: float, evidenza: str, peso: float = 1.0) -> dict:
    return {
        "criterio": nome,
        "valore": round(max(0.0, min(1.0, valore)), 2),
        "evidenza": evidenza,
        "peso": peso,
    }


def _quota(parte: int, totale: int) -> float:
    return parte / totale if totale else 0.0


def _tetto(regola: str, misura: str, scatta: bool, voto_massimo: int) -> dict:
    return {"regola": regola, "misura": misura, "scatta": scatta, "voto_massimo": voto_massimo}


def _area(criteri: list[dict], tetti: list[dict] | None = None) -> dict:
    """Punteggio 0-9 dell'area: media pesata dei criteri, poi limitata dai tetti che
    scattano (non possono mai alzarlo). Senza criteri misurabili l'area non ha punteggio."""
    if not criteri:
        return {"punteggio": None, "criteri": [], "nota": "Non misurabile con i dati raccolti."}
    peso = sum(c["peso"] for c in criteri)
    media = round(9 * sum(c["valore"] * c["peso"] for c in criteri) / peso)
    punteggio = media
    for tetto in tetti or []:
        if tetto["scatta"]:
            punteggio = min(punteggio, tetto["voto_massimo"])
            tetto["effetto"] = (
                f"abbassa il voto da {media} a {tetto['voto_massimo']}"
                if media > tetto["voto_massimo"]
                else "nessun effetto: il voto era gia' dentro il limite"
            )
    area: dict = {"punteggio": punteggio, "criteri": criteri}
    if tetti:
        area["tetti"] = tetti
    if punteggio != media:
        area["punteggio_prima_dei_tetti"] = media
    return area


def _per_tipo(pagine: list[dict], *tipi: str) -> list[dict]:
    return [p for p in pagine if p["tipo"] in tipi]


# --- aree -------------------------------------------------------------------


def _titoli(pagine: list[dict]) -> list[dict]:
    titoli = [p["titolo"] for p in pagine if p["titolo"]]
    if not titoli:
        return [_criterio("titoli presenti", 0.0, "nessuna pagina ha un titolo", peso=3)]
    giusti = sum(TITOLO_MIN <= len(t) <= TITOLO_MAX for t in titoli)
    finali: dict[str, int] = {}
    for titolo in titoli:
        for separatore in (" | ", " – ", " — ", " - ", " • "):
            if separatore in titolo:
                finale = titolo.rsplit(separatore, 1)[1].strip().lower()
                finali[finale] = finali.get(finale, 0) + 1
                break
    coerenti = max(finali.values(), default=0)
    quota_marchio = _quota(coerenti, len(titoli))
    return [
        _criterio(
            "lunghezza adatta",
            _quota(giusti, len(titoli)),
            f"titoli fra {TITOLO_MIN} e {TITOLO_MAX} caratteri: {giusti} su {len(titoli)}",
            peso=2,
        ),
        _criterio(
            "titoli diversi fra loro",
            _quota(len(set(titoli)), len(titoli)),
            f"titoli distinti: {len(set(titoli))} su {len(titoli)}",
            peso=2,
        ),
        _criterio(
            "marchio coerente nel titolo",
            1.0 if quota_marchio >= MARCHIO_COERENTE_DA else quota_marchio,
            f"{coerenti} titoli su {len(titoli)} finiscono con lo stesso segmento",
        ),
    ]


def _sembra_scheda_incollata(meta: str) -> bool:
    """Meta description fatta di campi della scheda ("CODICE: 12TAGLIA: M...")."""
    campi = [parola for parola in meta.replace(":", ": ").split() if parola.endswith(":")]
    return sum(c[:-1].isupper() and len(c) > 3 for c in campi) >= 2


def _meta(pagine: list[dict]) -> list[dict]:
    """Una meta description conta solo se e' scritta per essere letta: una scheda
    incollata ("CODICE: 12TAGLIA: M...") e' presente ma inutile, e non guadagna
    credito per lunghezza o unicita'."""
    if not pagine:
        return []
    con_meta = [p for p in pagine if p["meta_description"]]
    utili = [p for p in con_meta if not _sembra_scheda_incollata(p["meta_description"])]
    incollate = len(con_meta) - len(utili)
    dettaglio = f"{len(con_meta)} presenti"
    if incollate:
        dettaglio += f", {incollate} sembrano la scheda incollata"
    dettaglio += _dettaglio_per_tipo(pagine)
    criteri = [
        _criterio(
            "meta description utile",
            _quota(len(utili), len(pagine)),
            f"pagine con una meta description utile: {len(utili)} su {len(pagine)} ({dettaglio})",
            peso=3,
        )
    ]
    if utili:
        nel_range = sum(META_MIN <= len(p["meta_description"]) <= META_MAX for p in utili)
        distinte = len({p["meta_description"] for p in utili})
        criteri += [
            _criterio(
                "lunghezza adatta",
                _quota(nel_range, len(utili)),
                f"meta fra {META_MIN} e {META_MAX} caratteri: {nel_range} su {len(utili)}",
            ),
            _criterio(
                "diversa da pagina a pagina",
                _quota(distinte, len(utili)),
                f"meta description distinte: {distinte} su {len(utili)}",
            ),
        ]
    return criteri


def _dettaglio_per_tipo(pagine: list[dict]) -> str:
    """Dove manca la meta description, per tipo di pagina (se manca ovunque in un tipo)."""
    senza = []
    for tipo in ("home", "categoria", "prodotto"):
        gruppo = _per_tipo(pagine, tipo)
        if gruppo and not any(p["meta_description"] for p in gruppo):
            senza.append(f"{tipo}: nessuna")
    return f" ({', '.join(senza)})" if senza else ""


def _intestazioni(pagine: list[dict]) -> list[dict]:
    if not pagine:
        return []
    un_h1 = sum(len(p["h1"]) == 1 for p in pagine)
    criteri = [
        _criterio(
            "un solo H1 per pagina",
            _quota(un_h1, len(pagine)),
            f"pagine con un solo H1: {un_h1} su {len(pagine)}",
            peso=2,
        )
    ]
    contenuto = _per_tipo(pagine, "categoria", "prodotto")
    if contenuto:
        con_h2 = sum(bool(p["h2"]) for p in contenuto)
        criteri.append(
            _criterio(
                "sottotitoli di contenuto",
                _quota(con_h2, len(contenuto)),
                f"categorie e prodotti con almeno un H2 di contenuto: {con_h2} su {len(contenuto)}",
                peso=0.5,
            )
        )
    return criteri


def _dati_strutturati(pagine: list[dict]) -> list[dict]:
    criteri = []
    prodotti = _per_tipo(pagine, "prodotto")
    if prodotti:
        con = lambda p, *tipi: any(t in p["dati_strutturati"] for t in tipi)  # noqa: E731
        n = len(prodotti)
        scheda = sum(con(p, "Product", "ProductGroup") for p in prodotti)
        offerta = sum(con(p, "Offer", "AggregateOffer") for p in prodotti)
        valutazioni = sum(bool(p["dati_prodotto"].get("con_valutazioni")) for p in prodotti)
        criteri += [
            _criterio(
                "scheda prodotto (Product)",
                _quota(scheda, n),
                f"prodotti con Product: {scheda} su {n}",
                2,
            ),
            _criterio(
                "prezzo e disponibilita' (Offer)",
                _quota(offerta, n),
                f"prodotti con Offer: {offerta} su {n}",
            ),
            _criterio(
                "valutazioni dei clienti",
                _quota(valutazioni, n),
                f"prodotti con valutazioni: {valutazioni} su {n}",
            ),
        ]
    interne = [p for p in pagine if p["tipo"] != "home"]
    if interne:
        briciole = sum("BreadcrumbList" in p["dati_strutturati"] for p in interne)
        criteri.append(
            _criterio(
                "percorso di navigazione (BreadcrumbList)",
                _quota(briciole, len(interne)),
                f"pagine interne con BreadcrumbList: {briciole} su {len(interne)}",
            )
        )
    categorie = _per_tipo(pagine, "categoria")
    if categorie:
        con_schema = sum(
            any(t in p["dati_strutturati"] for t in ("CollectionPage", "ItemList", "OfferCatalog"))
            for p in categorie
        )
        criteri.append(
            _criterio(
                "dati strutturati delle categorie",
                _quota(con_schema, len(categorie)),
                f"categorie con CollectionPage o ItemList: {con_schema} su {len(categorie)}",
            )
        )
    home = _per_tipo(pagine, "home")
    if home:
        organizzazione = sum(
            any(
                t in p["dati_strutturati"]
                for t in ("Organization", "WebSite", "Store", "LocalBusiness")
            )
            for p in home
        )
        criteri.append(
            _criterio(
                "identita' del sito (Organization/WebSite)",
                _quota(organizzazione, len(home)),
                f"home con dati dell'organizzazione: {organizzazione} su {len(home)}",
                0.5,
            )
        )
    return criteri


def _contenuto(pagine: list[dict]) -> list[dict]:
    criteri = []
    prodotti = _per_tipo(pagine, "prodotto")
    if prodotti:
        n = len(prodotti)
        parole = sum(p["parole_proprie"] for p in prodotti) / n
        organizzati = sum(
            p["righe_scheda"] >= RIGHE_SCHEDA_MIN
            or p["struttura"]["tabelle_o_liste_specifiche"] >= 1
            or p["parole_proprie"] >= PAROLE_PROPRIE_MIN
            for p in prodotti
        )
        con_descrizione = sum(bool(p["dati_prodotto"].get("descrizione")) for p in prodotti)
        criteri += [
            _criterio(
                "descrizioni con una buona quantita' di testo",
                parole / PAROLE_PROPRIE_PIENE,
                f"parole proprie medie: {round(parole)} (pieno da {PAROLE_PROPRIE_PIENE})",
                peso=2,
            ),
            _criterio(
                "scheda organizzata o ricca",
                _quota(organizzati, n),
                f"prodotti con {RIGHE_SCHEDA_MIN}+ righe 'etichetta: valore', una tabella o "
                f"{PAROLE_PROPRIE_MIN}+ parole proprie: {organizzati} su {n}",
            ),
            _criterio(
                "descrizione nei dati strutturati",
                _quota(con_descrizione, n),
                f"prodotti con descrizione in Product: {con_descrizione} su {n}",
                0.5,
            ),
        ]
    immagini = sum(p["immagini"] for p in pagine)
    if immagini:
        senza_alt = sum(p["immagini_senza_alt"] for p in pagine)
        criteri.append(
            _criterio(
                "immagini con testo alternativo",
                1 - _quota(senza_alt, immagini),
                f"immagini senza ALT: {senza_alt} su {immagini}",
            )
        )
    return criteri


def _tecnico(pagine: list[dict], sitemap_trovata: bool | None, https: bool | None) -> list[dict]:
    """`sitemap_trovata` e `https` sono None quando non si sono potuti verificare
    (pagine salvate dall'utente): in quel caso il criterio si salta."""
    if not pagine:
        return []
    n = len(pagine)
    lingua = sum(bool(p["lingua"]) for p in pagine)
    canonical = sum(bool(p["canonical"]) for p in pagine)
    indicizzabili = sum("noindex" not in p["meta_robots"].lower() for p in pagine)
    og = sum(bool(p["open_graph"]) for p in pagine)
    criteri = []
    if https is not None:
        criteri.append(
            _criterio(
                "HTTPS",
                1.0 if https else 0.0,
                "il sito usa HTTPS" if https else "il sito non usa HTTPS",
                2,
            )
        )
    if sitemap_trovata is not None:
        criteri.append(
            _criterio(
                "sitemap",
                1.0 if sitemap_trovata else 0.0,
                "sitemap trovata" if sitemap_trovata else "nessuna sitemap trovata",
            )
        )
    return criteri + [
        _criterio(
            "indirizzo canonico", _quota(canonical, n), f"pagine con canonical: {canonical} su {n}"
        ),
        _criterio(
            "lingua dichiarata", _quota(lingua, n), f"pagine con lingua dichiarata: {lingua} su {n}"
        ),
        _criterio(
            "pagine indicizzabili",
            _quota(indicizzabili, n),
            f"pagine senza noindex: {indicizzabili} su {n}",
        ),
        _criterio(
            "anteprime social (Open Graph)",
            _quota(og, n),
            f"pagine con Open Graph: {og} su {n}",
            0.5,
        ),
    ]


def _tetti_intestazioni(pagine: list[dict]) -> list[dict]:
    if not pagine:
        return []
    salti = sum(p["n_h3"] > 0 and not p["h2"] for p in pagine)
    return [
        _tetto(
            f"H3 senza H2 su oltre il {round(100 * PAGINE_H3_SENZA_H2_OLTRE)}% delle pagine "
            "(salto nella gerarchia delle intestazioni)",
            f"pagine con H3 ma senza H2: {salti} su {len(pagine)}",
            salti > PAGINE_H3_SENZA_H2_OLTRE * len(pagine),
            TETTO_GERARCHIA,
        )
    ]


def _tetti_contenuto(pagine: list[dict]) -> list[dict]:
    immagini = sum(p["immagini"] for p in pagine)
    if not immagini:
        return []
    senza_alt = sum(p["immagini_senza_alt"] for p in pagine)
    return [
        _tetto(
            f"immagini senza ALT oltre il {round(100 * ALT_MANCANTE_OLTRE)}%",
            f"immagini senza ALT: {senza_alt} su {immagini} ({round(100 * senza_alt / immagini)}%)",
            senza_alt > ALT_MANCANTE_OLTRE * immagini,
            TETTO_ALT,
        )
    ]


# --- insieme ----------------------------------------------------------------


def valuta(pagine: list[dict], sitemap_trovata: bool | None, https: bool | None) -> dict:
    """Valutazione 0-9 per area e complessiva. `pagine` sono i record completi
    delle pagine analizzate (dopo analizza_testi, con `parole_proprie`)."""
    aree = {
        "titoli": _area(_titoli(pagine)),
        "meta_description": _area(_meta(pagine)),
        "intestazioni": _area(_intestazioni(pagine), _tetti_intestazioni(pagine)),
        "dati_strutturati": _area(_dati_strutturati(pagine)),
        "contenuto": _area(_contenuto(pagine), _tetti_contenuto(pagine)),
        "tecnico": _area(_tecnico(pagine, sitemap_trovata, https)),
    }
    misurate = {nome: area for nome, area in aree.items() if area["punteggio"] is not None}
    peso = sum(PESI_AREE[nome] for nome in misurate)
    complessivo = (
        round(sum(PESI_AREE[n] * a["punteggio"] for n, a in misurate.items()) / peso) if peso else 0
    )
    senza_schede = not any(p["tipo"] in ("prodotto", "categoria") for p in pagine)
    if len(pagine) < PAGINE_MINIME or senza_schede:
        # Con una pagina o con la sola home un punteggio complessivo sarebbe fuorviante.
        motivo = "nessuna scheda prodotto o categoria" if senza_schede else "ne servono almeno 5"
        return {
            "punteggio": None,
            "significato": (
                f"Campione troppo piccolo per un punteggio complessivo: {len(pagine)} pagine, "
                f"{motivo}."
            ),
            "affidabilita": "bassa",
            "aree": aree,
            "pagine_valutate": len(pagine),
            "limiti": LIMITI,
        }
    return {
        "punteggio": complessivo,
        "significato": SIGNIFICATO[complessivo],
        "affidabilita": "adeguata",
        "aree": aree,
        "pagine_valutate": len(pagine),
        "limiti": LIMITI,
    }
