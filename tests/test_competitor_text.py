from push_contempt_mcp.competitor_text import (
    analizza_testi,
    blocchi_ripetuti,
    estratto,
    messaggi_ripetuti,
    riepilogo_stile,
    segnali_pagina,
    senza_ripetuti,
    vocabolario,
)

SPEDIZIONE = "Spedizione gratuita in 24 ore per tutti gli ordini"


def test_blocchi_ripetuti_servono_almeno_4_pagine_e_meta_di_esse():
    pagine = [[SPEDIZIONE, f"Testo proprio {i}"] for i in range(4)]
    assert blocchi_ripetuti(pagine) == {SPEDIZIONE.lower(): 4}
    assert blocchi_ripetuti(pagine[:3]) == {}  # troppo poche per decidere

    # presente solo in 2 pagine su 6: non e' template
    sei = [[SPEDIZIONE] if i < 2 else [f"Altro {i}"] for i in range(6)]
    assert blocchi_ripetuti(sei) == {}
    # il confronto ignora maiuscole e spazi multipli
    varie = [
        ["Spedizione  GRATUITA in 24 ore per tutti gli ordini"],
        [SPEDIZIONE],
        [SPEDIZIONE],
        [SPEDIZIONE],
    ]
    assert list(blocchi_ripetuti(varie).values()) == [4]


def test_messaggi_ripetuti_solo_frasi_di_3_25_parole_le_piu_diffuse_prima():
    ripetuti = {
        "carrello": 9,
        SPEDIZIONE.lower(): 7,
        "reso entro 30 giorni senza spiegazioni": 9,
        " ".join(["parola"] * 30): 9,
    }
    messaggi = messaggi_ripetuti(ripetuti)
    assert [m["testo"] for m in messaggi] == [
        "reso entro 30 giorni senza spiegazioni",
        SPEDIZIONE.lower(),
    ]
    assert messaggi[0]["pagine"] == 9


def test_senza_ripetuti_toglie_i_blocchi_del_template():
    ripetuti = {SPEDIZIONE.lower(): 5}
    assert senza_ripetuti([SPEDIZIONE, "Descrizione vera del prodotto"], ripetuti) == [
        "Descrizione vera del prodotto"
    ]


def test_estratto_salta_i_blocchi_corti_e_taglia_a_fine_parola():
    blocchi = ["€ 1.299,00", "Aggiungi al carrello", "Un telefono potente con display luminoso"]
    assert estratto(blocchi, 500) == "Un telefono potente con display luminoso"
    assert estratto(blocchi, 22) == "Un telefono potente…"  # niente parole tagliate a meta'
    assert estratto(blocchi, 0) == ""
    assert estratto([], 100) == ""


def test_segnali_pagina_conta_formule_misure_e_punteggiatura():
    blocchi = [
        "Acquista ora il tuo nuovo smartphone!",
        "Batteria da 5000 mAh e 12 GB di RAM, display a 120 Hz.",
        "Spedizione gratuita e garanzia ufficiale: offerta -20%. Perché scegliere noi?",
    ]
    s = segnali_pagina(blocchi, blocchi)

    assert s["inviti_all_azione"] == 1
    assert s["rivolto_al_cliente"] == 1  # "tuo"
    assert s["parla_di_se"] == 1  # "noi"
    assert s["misure_tecniche"] == 3
    assert s["fiducia_e_servizio"] == 3  # spedizione gratuita, garanzia, ufficiale
    assert s["offerta_e_urgenza"] == 2  # offerta, -20%
    assert s["confronto_e_guida"] == 1  # perché
    assert s["esclamazioni"] == 1
    assert s["domande"] == 1
    assert s["frasi"] == 4
    assert s["parole"] == sum(len(b.split()) for b in blocchi)


def test_segnali_fiducia_conta_anche_il_template_ma_le_frasi_no():
    tutti = [SPEDIZIONE, "Un telefono bellissimo con uno schermo enorme."]
    propri = tutti[1:]
    s = segnali_pagina(tutti, propri)
    assert s["fiducia_e_servizio"] == 1
    assert s["frasi"] == 1


def test_riepilogo_stile_ogni_mille_parole():
    a = segnali_pagina(
        ["Acquista subito questo telefono."] * 5, ["Acquista subito questo telefono."]
    )
    riepilogo = riepilogo_stile([a])
    assert riepilogo["ogni_1000_parole"]["inviti_all_azione"] == round(
        1000 * 5 / 20, 1
    )  # 5 inviti in 20 parole
    assert riepilogo["lunghezza_media_frase_in_parole"] == 4.0
    assert riepilogo_stile([])["ogni_1000_parole"]["inviti_all_azione"] == 0.0


def test_vocabolario_per_diffusione_con_coppie_che_non_attraversano_la_punteggiatura():
    testi = [
        "Display AMOLED luminoso. Batteria da 5000 mAh con ricarica rapida.",
        "Il display amoled consuma poco. Ricarica rapida da 45 W.",
        "Display amoled e fotocamera doppia, ricarica rapida inclusa.",
        "Fotocamera da 50 MP.",
        "Custodia in silicone.",
    ]
    v = vocabolario(testi)

    termini = {t["termine"]: t["pagine"] for t in v["termini"]}
    assert termini["display"] == 3
    assert termini["ricarica"] == 3
    assert termini["fotocamera"] == 2
    assert "custodia" not in termini  # una sola pagina: sotto la soglia
    assert "della" not in termini and "da" not in termini  # parole vuote

    coppie = {c["coppia"]: c["pagine"] for c in v["coppie_di_parole"]}
    assert coppie["display amoled"] == 3
    assert coppie["ricarica rapida"] == 3
    assert "luminoso batteria" not in coppie  # c'e' un punto in mezzo

    assert {"unita": "mah", "pagine": 1} not in v["unita_di_misura"]  # soglia: 2 pagine
    assert {"unita": "mp", "pagine": 1} not in v["unita_di_misura"]


def test_vocabolario_unita_di_misura_e_sigle_con_cifre():
    testi = ["Memoria da 12 GB e rete 5G.", "Ram 8 GB con 5G e 4K.", "Telefono 5G da 256 GB."]
    v = vocabolario(testi)
    assert {"unita": "gb", "pagine": 3} in v["unita_di_misura"]
    assert {"termine": "5g", "pagine": 3} in v["termini"]


def test_analizza_testi_arricchisce_le_pagine_e_consuma_i_blocchi():
    def pagina(tipo, i):
        return {
            "tipo": tipo,
            "_blocchi": [SPEDIZIONE, f"Il modello {i} ha una batteria enorme e un display nitido."],
        }

    pagine = [pagina("home", 0)] + [pagina("prodotto", i) for i in range(1, 5)]
    risultato = analizza_testi(pagine, 200)

    assert all("_blocchi" not in p for p in pagine)
    assert pagine[1]["estratto"] == "Il modello 1 ha una batteria enorme e un display nitido."
    assert pagine[1]["_testo_proprio"] == pagine[1]["estratto"]
    assert risultato["messaggi_ripetuti_sul_sito"] == [{"testo": SPEDIZIONE.lower(), "pagine": 4}]
    assert list(risultato["per_tipo"]) == ["prodotto"]  # niente "home" ne' tipi senza pagine
    termini = [t["termine"] for t in risultato["per_tipo"]["prodotto"]["vocabolario"]["termini"]]
    assert "batteria" in termini and "spedizione" not in termini
