import random

import pytest

from push_contempt_mcp import seo_scorecard
from push_contempt_mcp.seo_scorecard import _sembra_scheda_incollata, valuta

_LESSICO = (
    "display luminoso batteria autonomia fotocamera notturna ricarica rapida memoria veloce "
    "schermo fluido audio stereo resistente acqua leggero sottile elegante potente scatti nitidi "
    "video stabili giochi fluidi viaggi lunghi lavoro studio musica sport foto ritratti zoom "
    "sensore software aggiornato sicuro privato garantito spedizione gratuita reso facile"
).split()


def _meta_propria(i: int) -> str:
    """Una meta description con testo proprio e diverso per ogni pagina."""
    parole = random.Random(i).sample(_LESSICO, 9)
    return f"Modello {i}: " + " ".join(parole) + ". Scoprilo ora con tutte le sue caratteristiche."


def pagina(tipo="prodotto", i=0, **campi):
    """Una pagina fatta bene; i campi passati la peggiorano."""
    base = {
        "tipo": tipo,
        "titolo": f"Smartphone Esempio Modello {i} 256GB | Negozio",  # 45 caratteri
        "meta_description": _meta_propria(i),
        "h1": [f"Modello {i}"],
        "h2": ["Caratteristiche"],
        "n_h3": 0,
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
        "meta description con testo proprio: 0 su 6"
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
        "meta description con testo proprio: 0 su 6 (6 presenti, 6 scheda incollata; "
        "la formula vale 0.5)"
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
    assert risultato["punteggio"] is None  # una sola pagina: campione troppo piccolo


def test_pagine_salvate_non_penalizzate_per_sitemap_e_https_non_verificabili():
    con = valuta(sito_buono(), sitemap_trovata=False, https=False)["aree"]["tecnico"]
    senza = valuta(sito_buono(), sitemap_trovata=None, https=None)["aree"]["tecnico"]
    nomi = [c["criterio"] for c in senza["criteri"]]
    assert "sitemap" not in nomi and "HTTPS" not in nomi
    assert senza["punteggio"] == 9
    assert con["punteggio"] < senza["punteggio"]  # HTTPS e sitemap assenti pesano, se verificati


def test_senza_pagine_il_punteggio_e_zero_senza_errori():
    risultato = valuta([], True, True)
    assert risultato["punteggio"] is None and risultato["affidabilita"] == "bassa"
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


def test_campione_troppo_piccolo_non_da_il_punteggio_complessivo_ma_le_aree_restano():
    solo_home = valuta([pagina("home", 0)], True, True)
    assert solo_home["punteggio"] is None
    assert solo_home["affidabilita"] == "bassa"
    assert "nessuna scheda prodotto o categoria" in solo_home["significato"]
    assert solo_home["aree"]["titoli"]["punteggio"] is not None  # le aree si vedono comunque

    quattro = valuta([pagina("home", 0), *[pagina("prodotto", i) for i in range(1, 4)]], True, True)
    assert quattro["punteggio"] is None and "ne servono almeno 5" in quattro["significato"]

    cinque = valuta([pagina("home", 0), *[pagina("prodotto", i) for i in range(1, 5)]], True, True)
    assert isinstance(cinque["punteggio"], int) and cinque["affidabilita"] == "adeguata"

    solo_home_molte = valuta([pagina("home", i) for i in range(8)], True, True)
    assert solo_home_molte["punteggio"] is None  # tante pagine, ma nessuna scheda


# --- tetti: un difetto grave limita il voto dell'area ----------------------


def _contenuto(pagine):
    return valuta(pagine, True, True)["aree"]["contenuto"]


def _intestazioni(pagine):
    return valuta(pagine, True, True)["aree"]["intestazioni"]


def test_alt_mancante_oltre_il_35_percento_limita_il_contenuto_a_6():
    # 10 pagine con 10 immagini ciascuna: 4 su 10 senza ALT = 40% > 35%
    pagine = [pagina("prodotto", i, immagini=10, immagini_senza_alt=4) for i in range(10)]
    area = _contenuto(pagine)

    assert area["punteggio"] == 6
    assert area["punteggio_prima_dei_tetti"] > 6  # senza il tetto sarebbe piu' alto
    primo, secondo = area["tetti"]
    assert primo["scatta"] is True and primo["voto_massimo"] == 6
    assert primo["misura"] == "immagini senza ALT: 40 su 100 (40%)"
    assert primo["effetto"].startswith("abbassa il voto da ")
    assert secondo["scatta"] is False  # il 50% non e' superato


def test_alt_mancante_esattamente_al_35_percento_non_fa_scattare_il_tetto():
    pagine = [pagina("prodotto", i, immagini=20, immagini_senza_alt=7) for i in range(5)]  # 35%
    area = _contenuto(pagine)

    assert area["tetti"][0]["scatta"] is False
    assert "effetto" not in area["tetti"][0]
    assert "punteggio_prima_dei_tetti" not in area
    assert area["punteggio"] >= 8


def test_il_tetto_non_alza_mai_un_voto_gia_basso():
    vuota = {"paragrafi": 0, "voci_di_elenco": 0, "tabelle_o_liste_specifiche": 0}
    pagine = [
        pagina(
            "prodotto",
            i,
            immagini=10,
            immagini_senza_alt=10,
            parole_proprie=5,
            righe_scheda=0,
            struttura=vuota,
        )
        for i in range(6)
    ]
    area = _contenuto(pagine)

    assert area["punteggio"] < 6  # gia' sotto il limite del tetto
    assert all(t["scatta"] for t in area["tetti"])  # 100% senza ALT: scattano entrambi
    assert all(t["effetto"].startswith("nessun effetto") for t in area["tetti"])
    assert "punteggio_prima_dei_tetti" not in area


def test_h3_senza_h2_su_piu_della_meta_delle_pagine_limita_le_intestazioni_a_6():
    # 6 pagine su 10 con H3 ma senza H2 (60% > 50%)
    pagine = [pagina("prodotto", i, n_h3=3, h2=[]) for i in range(6)]
    pagine += [pagina("prodotto", i, n_h3=3, h2=["Dettagli"]) for i in range(6, 10)]
    area = _intestazioni(pagine)

    assert area["punteggio"] == 6
    [tetto] = area["tetti"]
    assert tetto["scatta"] is True
    assert tetto["misura"] == "pagine con H3 ma senza H2: 6 su 10"
    assert "salto nella gerarchia" in tetto["regola"]


def test_h3_senza_h2_su_meta_esatta_delle_pagine_non_fa_scattare_il_tetto():
    pagine = [pagina("prodotto", i, n_h3=3, h2=[]) for i in range(5)]
    pagine += [pagina("prodotto", i, n_h3=3, h2=["Dettagli"]) for i in range(5, 10)]
    area = _intestazioni(pagine)

    assert area["tetti"][0]["scatta"] is False
    assert area["punteggio"] >= 8


def test_senza_h3_nessun_tetto_sulla_gerarchia_anche_senza_h2():
    pagine = [pagina("prodotto", i, n_h3=0, h2=[]) for i in range(10)]  # nessun H3: niente salto
    area = _intestazioni(pagine)
    assert area["tetti"][0]["scatta"] is False
    assert area["tetti"][0]["misura"] == "pagine con H3 ma senza H2: 0 su 10"


def test_i_tetti_pesano_sul_punteggio_complessivo():
    buoni = valuta(sito_buono(), True, True)
    con_difetti = valuta(
        [{**p, "immagini": 10, "immagini_senza_alt": 5, "n_h3": 2, "h2": []} for p in sito_buono()],
        True,
        True,
    )
    assert con_difetti["aree"]["contenuto"]["punteggio"] == 6
    assert con_difetti["aree"]["intestazioni"]["punteggio"] == 6
    assert con_difetti["punteggio"] < buoni["punteggio"]


def test_alt_mancante_oltre_il_50_percento_limita_il_contenuto_a_5():
    pagine = [pagina("prodotto", i, immagini=10, immagini_senza_alt=6) for i in range(10)]  # 60%
    area = _contenuto(pagine)

    assert area["punteggio"] == 5
    primo, secondo = area["tetti"]
    assert primo["scatta"] and secondo["scatta"]
    assert secondo["voto_massimo"] == 5 and "oltre il 50%" in secondo["regola"]
    assert secondo["effetto"].startswith("abbassa il voto da ")


# --- meta description: quanto aggiunge al titolo -----------------------------


def _con_meta(titolo, meta, i=0):
    return pagina("prodotto", i, titolo=titolo, meta_description=meta, h1=[titolo.split(" | ")[0]])


def _credito_meta(pagine):
    area = valuta(pagine, True, True)["aree"]["meta_description"]
    utile = next(c for c in area["criteri"] if c["criterio"] == "meta description utile")
    return utile["valore"], utile["evidenza"]


def test_meta_che_ripete_solo_il_titolo_non_vale_niente():
    """AutoQuarta: 'Auto in vendita <titolo>'."""
    pagine = [
        _con_meta(
            f"AUDI A3 modello {i} TDI In Vendita | Concessionaria Auto Usate",
            f"Auto in vendita AUDI A3 modello {i} TDI",
            i,
        )
        for i in range(6)
    ]
    valore, evidenza = _credito_meta(pagine)
    assert valore == 0
    assert "6 solo il titolo" in evidenza


def test_titolo_piu_frase_generica_vale_mezzo_credito():
    """Mediaworld: '<titolo>. Acquista online su Negozio o nei nostri negozi!'."""
    pagine = [
        _con_meta(
            f"SAMSUNG Galaxy A{i} 128GB | Negozio",
            f"SAMSUNG Galaxy A{i} 128GB. Acquista online su Negozio o nei nostri negozi fisici!",
            i,
        )
        for i in range(6)
    ]
    valore, evidenza = _credito_meta(pagine)
    assert valore == 0.5
    assert "6 titolo piu' frase generica" in evidenza


def test_frase_fissa_uguale_su_piu_della_meta_delle_pagine_non_vale_niente():
    """Tomato: 'GARANZIA 12 MESI RESO GRATUITO ENTRO 14GG' su 8 pagine su 12."""
    fissa = "GARANZIA 12 MESI RESO GRATUITO ENTRO 14GG su tutti gli ordini"
    pagine = [_con_meta(f"APPLE iPhone {i} | Negozio", fissa, i) for i in range(8)]
    pagine += [_con_meta(f"Pagina {i} | Negozio", _meta_propria(i), 100 + i) for i in range(4)]
    valore, evidenza = _credito_meta(pagine)
    assert "8 frase fissa" in evidenza
    assert valore == pytest.approx(4 / 12, abs=0.01)  # solo le 4 pagine con testo proprio valgono


def test_meta_con_testo_proprio_vale_il_massimo_e_le_regole_fra_pagine_servono_4_pagine():
    pagine = [_con_meta(f"Prodotto {i} | Negozio", _meta_propria(i), i) for i in range(6)]
    assert _credito_meta(pagine)[0] == 1.0
    # con meno di 4 pagine non si puo' dire che una frase sia "uguale su molte pagine"
    uguali = [
        _con_meta(f"Prodotto {i} | Negozio", "Una frase molto generica ma uguale", i)
        for i in range(3)
    ]
    assert _credito_meta(uguali)[0] == 1.0


def test_stessa_frase_su_poche_categorie_vale_mezzo_credito():
    """Euronics: tre categorie con '<nome> in offerta su Negozio. Approfitta...' fra molti prodotti
    con meta proprie: la frase non e' su meta' delle pagine, ma e' su tutte le categorie."""
    pagine = [
        pagina(
            "categoria",
            i,
            titolo=f"Categoria {i} - offerte su Negozio",
            meta_description=f"Categoria {i} in offerta su Negozio. Approfitta dei prezzi scontati "
            "e acquista il tuo prodotto preferito.",
            h1=[f"Categoria {i}"],
        )
        for i in range(3)
    ]
    pagine += [_con_meta(f"Prodotto {i} | Negozio", _meta_propria(i), 10 + i) for i in range(8)]
    valore, evidenza = _credito_meta(pagine)
    assert "3 titolo piu' frase generica" in evidenza
    assert valore == pytest.approx((8 + 3 * 0.5) / 11, abs=0.01)


def test_la_pagina_iniziale_di_una_sezione_conta_come_categoria():
    """Back Market: la pagina iniziale e' una 'sezione' e le altre due sono categorie."""
    tipi = ["sezione", "categoria", "categoria"]
    pagine = [
        pagina(
            tipo,
            i,
            titolo=f"Categoria {i} | Negozio",
            meta_description=f"Trova il tuo articolo {i} su Negozio! Come nuovo, miglior prezzo, "
            "consegna in 24 ore, garanzia inclusa.",
            h1=[f"Categoria {i}"],
        )
        for i, tipo in enumerate(tipi)
    ]
    pagine += [_con_meta(f"Prodotto {i} | Negozio", _meta_propria(i), 10 + i) for i in range(8)]
    assert "3 titolo piu' frase generica" in _credito_meta(pagine)[1]


def test_due_categorie_con_la_stessa_frase_non_bastano():
    pagine = [
        pagina(
            "categoria",
            i,
            titolo=f"Categoria {i} - offerte su Negozio",
            meta_description=f"Categoria {i} in offerta su Negozio. Approfitta dei prezzi scontati "
            "e acquista il tuo prodotto preferito.",
            h1=[f"Categoria {i}"],
        )
        for i in range(2)
    ]
    pagine += [_con_meta(f"Prodotto {i} | Negozio", _meta_propria(i), 10 + i) for i in range(8)]
    assert _credito_meta(pagine)[0] == 1.0


def test_poche_meta_utili_pesano_meno_su_lunghezza_e_unicita():
    """Tomato: solo 2 meta proprie su 14, e per giunta fra 110 e 160 caratteri e diverse."""
    fissa = "GARANZIA 12 MESI RESO GRATUITO ENTRO 14GG"
    pagine = [_con_meta(f"APPLE iPhone {i} | Negozio", fissa, i) for i in range(10)]
    pagine += [_con_meta(f"Pagina {i} | Negozio", _meta_propria(i), 100 + i) for i in range(2)]
    area = valuta(pagine, True, True)["aree"]["meta_description"]
    pesi = {c["criterio"]: c["peso"] for c in area["criteri"]}
    assert pesi["meta description utile"] == 3
    assert pesi["lunghezza adatta"] == pytest.approx(0.4)
    assert pesi["diversa da pagina a pagina"] == pytest.approx(0.4)
    evidenze = {c["criterio"]: c["evidenza"] for c in area["criteri"]}
    assert "peso ridotto a 0.4" in evidenze["lunghezza adatta"]


def test_con_cinque_meta_utili_il_peso_e_pieno():
    pagine = [_con_meta(f"Prodotto {i} | Negozio", _meta_propria(i), i) for i in range(5)]
    area = valuta(pagine, True, True)["aree"]["meta_description"]
    assert [c["peso"] for c in area["criteri"]] == [3, 1.0, 1.0]
    assert all("peso ridotto" not in c["evidenza"] for c in area["criteri"])


# --- H1: uno, piu' uguali, piu' diversi, nessuno ----------------------------


def _valore_h1(h1_per_pagina):
    pagine = [pagina("prodotto", i, h1=h1) for i, h1 in enumerate(h1_per_pagina)]
    area = valuta(pagine, True, True)["aree"]["intestazioni"]
    criterio = next(c for c in area["criteri"] if c["criterio"] == "un solo H1 per pagina")
    return criterio["valore"], criterio["evidenza"]


def test_h1_a_livelli():
    assert _valore_h1([["Titolo"]] * 4)[0] == 1.0
    assert (
        _valore_h1([["Titolo", "Titolo"]] * 4)[0] == 0.6
    )  # doppio e uguale (Euronics, Back Market)
    assert _valore_h1([["Titolo", "Altro titolo"]] * 4)[0] == 0.3
    assert _valore_h1([[]] * 4)[0] == 0  # nessun H1 (schede di Tomato)
    # il confronto ignora maiuscole e punteggiatura
    assert _valore_h1([["Galaxy A17, 128GB", "galaxy a17 128gb"]] * 2)[0] == 0.6


def test_h1_misti_media_e_evidenza():
    valore, evidenza = _valore_h1([["A"], ["B", "B"], ["C", "D"], []])
    assert valore == pytest.approx((1.0 + 0.6 + 0.3 + 0) / 4, abs=0.01)
    assert evidenza == (
        "pagine con un solo H1: 1 su 4; piu' H1 uguali: 1; piu' H1 diversi: 1; nessun H1: 1"
    )
