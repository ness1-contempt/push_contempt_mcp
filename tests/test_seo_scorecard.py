from push_contempt_mcp import seo_scorecard
from push_contempt_mcp.seo_scorecard import _sembra_scheda_incollata, valuta


def pagina(tipo="prodotto", i=0, **campi):
    """Una pagina fatta bene; i campi passati la peggiorano."""
    base = {
        "tipo": tipo,
        "titolo": f"Smartphone Esempio Modello {i} 256GB | Negozio",  # 45 caratteri
        "meta_description": (
            f"Scopri lo smartphone Esempio Modello {i}: display luminoso, batteria che dura due "
            "giorni e consegna in 24 ore. Acquistalo ora."
        ),
        "h1": [f"Modello {i}"],
        "h2": ["Caratteristiche"],
        "dati_strutturati": ["Product", "Offer", "BreadcrumbList"],
        "dati_prodotto": {"descrizione": "Un telefono", "con_valutazioni": True},
        "struttura": {"paragrafi": 5, "voci_di_elenco": 6, "tabelle_o_liste_specifiche": 1},
        "parole_proprie": 200,
        "righe_scheda": 5,
        "immagini": 4,
        "immagini_senza_alt": 0,
        "canonical": f"https://esempio.it/p/{i}/",
        "lingua": "it",
        "meta_robots": "index, follow",
        "open_graph": True,
    }
    if tipo == "categoria":
        base["dati_strutturati"] = ["CollectionPage", "BreadcrumbList"]
    if tipo == "home":
        base["dati_strutturati"] = ["WebSite", "Organization"]
    return {**base, **campi}


def sito_buono():
    return [
        pagina("home", 0),
        pagina("categoria", 1),
        *[pagina("prodotto", i) for i in range(2, 8)],
    ]


def sito_scadente():
    """Come Casual Bay: titoli corti e uguali, meta incollate o assenti, niente schema."""
    cattive = dict(
        titolo="Casual Bay",
        meta_description="",
        h1=[],
        h2=[],
        dati_strutturati=["Organization"],
        dati_prodotto={},
        struttura={"paragrafi": 0, "voci_di_elenco": 0, "tabelle_o_liste_specifiche": 0},
        parole_proprie=10,
        righe_scheda=0,
        immagini_senza_alt=4,
        canonical="",
        lingua="",
        open_graph=False,
    )
    return [pagina("home", 0, **cattive), *[pagina("prodotto", i, **cattive) for i in range(1, 6)]]


def test_un_sito_curato_prende_un_punteggio_alto_in_ogni_area():
    risultato = valuta(sito_buono(), sitemap_trovata=True, https=True)

    assert risultato["punteggio"] >= 8
    assert {nome: a["punteggio"] for nome, a in risultato["aree"].items()} == {
        "titoli": 9,
        "meta_description": 9,
        "intestazioni": 9,
        "dati_strutturati": 9,
        "contenuto": 9,
        "tecnico": 9,
    }
    assert risultato["significato"] == seo_scorecard.SIGNIFICATO[risultato["punteggio"]]
    assert risultato["pagine_valutate"] == 8


def test_un_sito_scadente_prende_un_punteggio_basso_con_le_prove():
    risultato = valuta(sito_scadente(), sitemap_trovata=False, https=True)

    assert risultato["punteggio"] <= 3
    aree = risultato["aree"]
    assert aree["meta_description"]["punteggio"] == 0
    assert aree["dati_strutturati"]["punteggio"] <= 1
    evidenze = {c["criterio"]: c["evidenza"] for a in aree.values() for c in a["criteri"]}
    assert evidenze["meta description utile"].startswith(
        "pagine con una meta description utile: 0 su 6"
    )
    assert "home: nessuna" in evidenze["meta description utile"]
    assert evidenze["titoli diversi fra loro"] == "titoli distinti: 1 su 6"
    assert evidenze["sitemap"] == "nessuna sitemap trovata"
    assert evidenze["immagini con testo alternativo"] == "immagini senza ALT: 24 su 24"


def test_si_puo_essere_bravi_su_un_area_e_scarsi_sulle_altre():
    """E' il motivo per cui il punteggio e' per area: spunto solo da dove il sito e' forte."""
    pagine = [
        pagina("home", 0, meta_description=""),
        *[
            pagina(
                "prodotto",
                i,
                meta_description="",
                dati_strutturati=["Organization"],
                dati_prodotto={},
            )
            for i in range(1, 7)
        ],
    ]
    aree = valuta(pagine, True, True)["aree"]
    assert aree["titoli"]["punteggio"] == 9
    assert aree["contenuto"]["punteggio"] >= 7
    assert aree["meta_description"]["punteggio"] == 0
    assert aree["dati_strutturati"]["punteggio"] <= 3


def test_meta_incollata_dalla_scheda_pesa_sul_punteggio():
    assert _sembra_scheda_incollata("CODICE ARTICOLO: 12167TAGLIA: MCOLORE: BluBRAND: Vintage")
    assert not _sembra_scheda_incollata("Scopri la felpa grafica: comoda e resistente. Taglia M.")
    assert not _sembra_scheda_incollata("")

    scheda = "CODICE ARTICOLO: 12167TAGLIA: MCOLORE: Blu BRAND: Vintage CONDIZIONI: 9/10 chat"
    pagine = [pagina("prodotto", i, meta_description=scheda + f" {i}") for i in range(6)]
    meta = valuta(pagine, True, True)["aree"]["meta_description"]
    evidenze = {c["criterio"]: c["evidenza"] for c in meta["criteri"]}
    # presente ma inutile: non vale come meta description, e non guadagna credito per
    # lunghezza o unicita'
    assert evidenze["meta description utile"] == (
        "pagine con una meta description utile: 0 su 6 (6 presenti, 6 sembrano la scheda incollata)"
    )
    assert [c["criterio"] for c in meta["criteri"]] == ["meta description utile"]
    assert meta["punteggio"] == 0


def test_aree_senza_dati_non_hanno_punteggio_e_non_contano_nel_totale():
    # solo la home: nessun prodotto ne' categoria
    risultato = valuta([pagina("home", 0)], True, True)
    assert risultato["aree"]["contenuto"]["punteggio"] == 9  # restano le immagini con ALT
    solo_titolo = [pagina("home", 0, immagini=0, meta_description="", dati_strutturati=[], h1=[])]
    risultato = valuta(solo_titolo, True, True)
    assert risultato["aree"]["contenuto"] == {
        "punteggio": None,
        "criteri": [],
        "nota": "Non misurabile con i dati raccolti.",
    }
    assert isinstance(risultato["punteggio"], int)  # il totale si calcola sulle altre aree


def test_pagine_salvate_non_penalizzate_per_sitemap_e_https_non_verificabili():
    con = valuta(sito_buono(), sitemap_trovata=False, https=False)["aree"]["tecnico"]
    senza = valuta(sito_buono(), sitemap_trovata=None, https=None)["aree"]["tecnico"]
    nomi = [c["criterio"] for c in senza["criteri"]]
    assert "sitemap" not in nomi and "HTTPS" not in nomi
    assert senza["punteggio"] == 9
    assert con["punteggio"] < senza["punteggio"]  # HTTPS e sitemap assenti pesano, se verificati


def test_senza_pagine_il_punteggio_e_zero_senza_errori():
    risultato = valuta([], True, True)
    assert risultato["punteggio"] == 0
    assert all(a["punteggio"] is None or a["punteggio"] >= 0 for a in risultato["aree"].values())


def test_i_valori_dei_criteri_stanno_fra_0_e_1_e_il_punteggio_fra_0_e_9():
    for pagine in (sito_buono(), sito_scadente()):
        risultato = valuta(pagine, True, True)
        assert 0 <= risultato["punteggio"] <= 9
        for area in risultato["aree"].values():
            if area["punteggio"] is not None:
                assert 0 <= area["punteggio"] <= 9
            for criterio in area["criteri"]:
                assert (
                    0 <= criterio["valore"] <= 1 and criterio["peso"] > 0 and criterio["evidenza"]
                )


def test_scheda_organizzata_si_misura_su_righe_etichetta_valore_tabelle_o_testo():
    vuota = {"paragrafi": 0, "voci_di_elenco": 0, "tabelle_o_liste_specifiche": 0}

    def organizzata(**campi):
        base = {"parole_proprie": 10, "righe_scheda": 0, "struttura": vuota}
        pagine = [pagina("prodotto", i, **{**base, **campi}) for i in range(4)]
        contenuto = valuta(pagine, True, True)["aree"]["contenuto"]
        return next(
            c for c in contenuto["criteri"] if c["criterio"] == "scheda organizzata o ricca"
        )

    assert organizzata()["valore"] == 0  # poco testo, niente righe, niente tabella
    assert organizzata(righe_scheda=5)["valore"] == 1  # scheda a campi fissi
    assert organizzata(struttura={**vuota, "voci_di_elenco": 40})["valore"] == 0  # menu non contano
    assert organizzata(struttura={**vuota, "tabelle_o_liste_specifiche": 1})["valore"] == 1
    assert organizzata(parole_proprie=90)["valore"] == 1  # abbastanza testo proprio


def test_l_area_tecnica_pesa_meno_perche_e_di_serie_sulle_piattaforme():
    assert seo_scorecard.PESI_AREE["tecnico"] < min(
        peso for area, peso in seo_scorecard.PESI_AREE.items() if area != "tecnico"
    )
