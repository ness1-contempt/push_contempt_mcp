import pytest

from push_contempt_mcp import text_similarity
from push_contempt_mcp.text_similarity import (
    SIGNIFICATO,
    _livello_copertura,
    _livello_sequenza,
    carica_riferimenti,
    controlla,
    salva_corpus,
)

ORIGINALE = (
    "Il Nothing Phone 2 e' uno smartphone con retro trasparente e luci led che si illuminano "
    "alle notifiche. Il display amoled da 6,7 pollici a 120 hz rende fluida ogni schermata, "
    "mentre la batteria da 4700 mah dura facilmente un giorno e mezzo di uso intenso."
)


def _ref(testo=ORIGINALE, fonte="https://concorrente.it/p/phone-2/"):
    return [{"fonte": fonte, "testo": testo}]


@pytest.fixture(autouse=True)
def _cache_temporanea(monkeypatch, tmp_path):
    monkeypatch.setenv("SEO_ANALISI_CACHE_DIR", str(tmp_path / "cache"))


def test_testo_identico_e_copia():
    risultato = controlla(ORIGINALE, _ref())
    assert risultato["punteggio"] == 9
    assert risultato["significato"] == "Copia."
    assert risultato["copertura_percentuale"] == 100


def test_maiuscole_e_punteggiatura_non_nascondono_la_copia():
    ritoccato = ORIGINALE.upper().replace(",", " ;").replace(".", " !")
    assert controlla(ritoccato, _ref())["punteggio"] == 9


def test_testo_diverso_non_somiglia_per_niente():
    nostro = (
        "Uno schermo brillante, una batteria che regge tutto il giorno e una fotocamera "
        "pensata per chi ama fotografare di sera: questo telefono punta sulla semplicita'."
    )
    risultato = controlla(nostro, _ref())
    assert risultato["punteggio"] == 0
    assert risultato["passaggi_simili"] == []
    assert risultato["sequenza_piu_lunga_in_parole"] == 0


def test_una_frase_tecnica_in_comune_in_una_descrizione_originale_da_un_punteggio_basso():
    nostro = (
        "Abbiamo provato a lungo questo modello e ci ha convinto, soprattutto per come "
        "si comporta nell'uso di tutti i giorni. Il display amoled da 6,7 pollici a 120 hz "
        "e' fluido, ma il vero punto di forza sta altrove: il software pulito, gli "
        "aggiornamenti frequenti e un prezzo onesto per quello che offre. Chi cerca un "
        "telefono originale nell'aspetto, senza rinunciare a prestazioni solide e a una "
        "fotocamera affidabile anche con poca luce, trova qui una proposta convincente e "
        "diversa dal solito, pensata per durare nel tempo senza stancare mai."
    )
    risultato = controlla(nostro, _ref())
    assert 1 <= risultato["punteggio"] <= 4
    assert "display amoled da 6 7 pollici a 120 hz" in risultato["passaggi_simili"][0]["testo"]


def test_la_stessa_frase_in_un_testo_breve_pesa_di_piu():
    breve = "Il display amoled da 6,7 pollici a 120 hz e' fluido, ma conta soprattutto il software."
    assert controlla(breve, _ref())["punteggio"] >= 5


def test_riscrittura_appena_ritoccata_ha_un_punteggio_alto():
    ritoccato = ORIGINALE.replace("fluida", "scorrevole").replace("intenso", "continuo")
    assert controlla(ritoccato, _ref())["punteggio"] >= 7


def test_il_punteggio_non_cala_se_si_aggiunge_testo_proprio_al_copiato():
    lungo = ORIGINALE + " " + "Aggiungiamo altre cose nostre che non c'entrano affatto. " * 3
    assert (
        controlla(lungo, _ref())["punteggio"]
        >= controlla("x " * 3 + ORIGINALE, _ref())["punteggio"] - 3
    )


def test_testo_troppo_corto():
    risultato = controlla("Solo tre parole", _ref())
    assert risultato["punteggio"] == 0
    assert "troppo corto" in risultato["avviso"]


def test_soglia_decisa_dall_utilizzatore():
    ritoccato = ORIGINALE.replace("fluida", "scorrevole")
    punteggio = controlla(ritoccato, _ref())["punteggio"]
    assert controlla(ritoccato, _ref(), soglia=punteggio)["accettabile"] is True
    assert controlla(ritoccato, _ref(), soglia=punteggio - 1)["accettabile"] is False
    assert "accettabile" not in controlla(ritoccato, _ref())  # senza soglia nessun verdetto
    assert controlla("Solo tre parole", _ref(), soglia=0)["accettabile"] is True


def test_piu_fonti_la_piu_simile_e_prima_e_i_passaggi_non_si_ripetono():
    metà = ORIGINALE.split("mentre")[0]
    riferimenti = [
        {"fonte": "https://a.it/", "testo": "Niente a che vedere con il nostro testo qui."},
        {"fonte": "https://b.it/", "testo": ORIGINALE},
        {"fonte": "https://c.it/", "testo": metà},
    ]
    risultato = controlla(ORIGINALE, riferimenti)
    assert [f["fonte"] for f in risultato["fonti_piu_simili"]][0] == "https://b.it/"
    assert risultato["confrontato_con"] == 3
    # c.it copre una parte gia' coperta da b.it: il passaggio compare una volta sola
    assert len(risultato["passaggi_simili"]) == 1


def test_scala_coerente_e_monotona():
    assert [
        _livello_copertura(c) for c in (0, 0.01, 0.04, 0.09, 0.19, 0.3, 0.45, 0.6, 0.85, 0.95)
    ] == list(range(10))
    livelli = [_livello_sequenza(n) for n in (0, 4, 5, 8, 12, 18, 25, 40, 200)]
    assert livelli == sorted(livelli) and livelli[0] == 0 and max(livelli) == 6
    assert set(SIGNIFICATO) == set(range(10))


# --- testi salvati ----------------------------------------------------------


def _pagine():
    return [
        {
            "url": "https://www.concorrente.it/p/1",
            "titolo": "Phone 2 | Shop",
            "meta_description": "Il phone 2 in offerta",
            "testo": ORIGINALE,
        },
        {
            "url": "https://www.concorrente.it/p/2",
            "titolo": "",
            "meta_description": "",
            "testo": "Un altro testo.",
        },
    ]


def test_salva_e_carica_i_riferimenti_di_un_sito():
    percorso = salva_corpus("https://www.concorrente.it", _pagine())
    assert percorso.name == "concorrente.it.json"

    fonti = [r["fonte"] for r in carica_riferimenti("concorrente.it")]
    assert fonti == [
        "https://www.concorrente.it/p/1",
        "https://www.concorrente.it/p/1 (titolo)",
        "https://www.concorrente.it/p/1 (meta description)",
        "https://www.concorrente.it/p/2",
    ]
    assert carica_riferimenti("https://www.concorrente.it/qualunque/") == carica_riferimenti(
        "concorrente.it"
    )


def test_senza_sito_si_confronta_con_tutti_quelli_salvati():
    salva_corpus(
        "https://uno.it",
        [{"url": "https://uno.it/a", "titolo": "", "meta_description": "", "testo": "Testo uno."}],
    )
    salva_corpus(
        "https://due.it",
        [{"url": "https://due.it/b", "titolo": "", "meta_description": "", "testo": "Testo due."}],
    )
    assert {r["fonte"] for r in carica_riferimenti()} == {"https://uno.it/a", "https://due.it/b"}
    assert [r["fonte"] for r in carica_riferimenti("due.it")] == ["https://due.it/b"]
    assert carica_riferimenti("sconosciuto.it") == []


def test_nessuna_cache_o_file_rovinato_non_solleva():
    assert carica_riferimenti() == []
    cartella = text_similarity.cartella_cache()
    cartella.mkdir(parents=True)
    (cartella / "rotto.it.json").write_text("{ non e' json")
    assert carica_riferimenti() == []


def test_il_testo_salvato_ha_un_tetto():
    enorme = "parola " * 100_000
    salva_corpus(
        "https://grande.it",
        [{"url": "https://grande.it/", "titolo": "", "meta_description": "", "testo": enorme}],
    )
    [riferimento] = carica_riferimenti("grande.it")
    assert len(riferimento["testo"]) == text_similarity.MAX_CARATTERI_PAGINA_SALVATA


def test_il_risultato_ricorda_che_il_punteggio_non_e_vincolante():
    for risultato in (controlla(ORIGINALE, _ref()), controlla("Poche parole qui", _ref())):
        assert "non e' vincolante" in risultato["nota"]
        assert "responsabilita'" in risultato["nota"]
