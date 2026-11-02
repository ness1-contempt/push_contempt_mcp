from push_contempt_mcp.varianti import (
    analizza_riga_varianti,
    trova_riga_varianti,
    varianti_dal_testo,
)


def test_legge_attributi_e_valori():
    esito = analizza_riga_varianti("Colore: Nero, Bianco | Memoria: 256 GB, 512 GB")

    assert esito["errori"] == []
    assert esito["attributi"] == [
        {"nome": "Colore", "valori": ["Nero", "Bianco"]},
        {"nome": "Memoria", "valori": ["256 GB", "512 GB"]},
    ]


def test_un_solo_attributo_e_spazi_in_piu():
    esito = analizza_riga_varianti("  Taglia :  S ,  M,L  ")

    assert esito["attributi"] == [{"nome": "Taglia", "valori": ["S", "M", "L"]}]


def test_valori_con_due_punti_dentro_restano_interi():
    esito = analizza_riga_varianti("Rapporto: 16:9, 4:3")

    assert esito["attributi"] == [{"nome": "Rapporto", "valori": ["16:9", "4:3"]}]


def test_errori_di_forma_sono_chiari_e_si_riportano_tutti():
    esito = analizza_riga_varianti(
        "Colore Nero, Bianco | : Rosso | Memoria: 256 GB,, 512 GB | Taglia:"
    )

    assert esito["attributi"] == []
    assert len(esito["errori"]) == 4
    assert "manca il due punti" in esito["errori"][0]
    assert "manca il nome" in esito["errori"][1]
    assert "valore vuoto" in esito["errori"][2]
    assert "valore vuoto" in esito["errori"][3]


def test_riga_vuota_e_un_errore():
    assert analizza_riga_varianti("   ")["errori"]
    assert analizza_riga_varianti("")["attributi"] == []


def test_trova_la_riga_solo_se_comincia_con_varianti_due_punti():
    testo = (
        "prezzo: 702 euro\n"
        "Disponibile in molte varianti: scegli il colore che preferisci.\n"
        "  VARIANTI : Colore: Nero, Bianco\n"
        "DESCRIZIONE\n"
    )

    assert trova_riga_varianti(testo) == "Colore: Nero, Bianco"


def test_senza_riga_non_trova_niente():
    assert trova_riga_varianti("prezzo: 5 euro\nuna frase sulle varianti del modello\n") is None
    assert trova_riga_varianti("") is None
    assert trova_riga_varianti(None) is None


def test_varianti_dal_testo_unisce_riga_e_analisi():
    assert varianti_dal_testo("nessuna riga qui") is None
    esito = varianti_dal_testo("varianti: Colore: Nero | Taglia: S, M\n")
    assert esito["riga"] == "Colore: Nero | Taglia: S, M"
    assert esito["errori"] == []
    assert len(esito["attributi"]) == 2
    assert varianti_dal_testo("varianti: Colore Nero")["errori"]
