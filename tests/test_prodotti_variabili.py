import pytest
import requests

from push_contempt_mcp import product_sync, product_tools


class _Risposta:
    def __init__(self, dati, status_code=200):
        self._dati = dati
        self.status_code = status_code
        self.text = str(dati)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error", response=self)

    def json(self):
        return self._dati


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("WP_SITE_URL", "https://localhost")
    monkeypatch.setenv("WP_APP_USER", "Andrea")
    monkeypatch.setenv("WP_APP_PASSWORD", "segreto")


@pytest.fixture
def chiamate(monkeypatch):
    """Registra le POST; l'anteprima risponde come il plugin, la creazione con un id."""
    registro = []

    def post_finto(url, auth, verify, timeout, headers=None, data=None, json=None):
        registro.append({"url": url, "json": json})
        if url.endswith("/wp/v2/media"):
            return _Risposta({"id": 100 + len(registro)})
        if json.get("solo_anteprima"):
            return _Risposta({"stato": "anteprima", "numero_varianti": 4, "varianti": []})
        return _Risposta({"stato": "creato_in_bozza", "prodotto_id": 9, "tipo": "variable"})

    monkeypatch.setattr(requests, "post", post_finto)
    return registro


def _crea(**extra):
    base = {
        "titolo": "Telefono",
        "descrizione": "<h2>Telefono</h2><p>Telefono veloce. Vedi <a href='/'>home</a>.</p>",
        "prezzo_regolare": "702",
        "categoria": "Smartphone",
        "percorsi_immagini": [],
        "alt_immagini": [],
        "frase_chiave_focus": "telefono",
        "titolo_seo": "Telefono",
        "meta_description": "Meta",
    }
    return product_tools.crea_prodotto_variabile(**{**base, **extra})


def test_serve_esattamente_uno_dei_due_modi(chiamate):
    assert "uno solo" in _crea()["errore"]
    assert (
        "uno solo" in _crea(attributi={"Colore": ["Nero"]}, riga_varianti="Colore: Nero")["errore"]
    )
    assert chiamate == []


def test_riga_scritta_male_da_un_errore_con_il_formato_e_non_chiama_il_plugin(chiamate):
    risultato = _crea(riga_varianti="Colore Nero, Bianco")

    assert risultato["creato"] is False
    assert "manca il due punti" in risultato["errore"]
    assert risultato["formato"].startswith("varianti: Colore:")
    assert chiamate == []


def test_anteprima_e_il_predefinito_e_non_scrive_niente(chiamate, tmp_path):
    foto = tmp_path / "foto.jpg"
    foto.write_bytes(b"x")

    risultato = _crea(
        riga_varianti="Colore: Nero, Bianco | Memoria: 256 GB, 512 GB",
        percorsi_immagini=[str(foto)],
        alt_immagini=["telefono"],
    )

    assert len(chiamate) == 1  # solo l'anteprima: nessun caricamento di immagini
    corpo = chiamate[0]["json"]
    assert corpo["solo_anteprima"] is True
    assert corpo["tipo"] == "variable"
    assert corpo["attributi"] == [
        {"nome": "Colore", "valori": ["Nero", "Bianco"]},
        {"nome": "Memoria", "valori": ["256 GB", "512 GB"]},
    ]
    assert "immagine_evidenza_id" not in corpo
    assert risultato["modalita"] == "riga"
    assert risultato["immagini"] == 1
    assert "anteprima=False" in risultato["prossimo_passo"]
    assert "avvisi_seo" in risultato


def test_anteprima_con_attributi_dell_assistente_mantiene_l_ordine(chiamate):
    risultato = _crea(attributi={"Memoria": ["256 GB"], "Colore": ["Nero", "Blu"]})

    assert [a["nome"] for a in chiamate[0]["json"]["attributi"]] == ["Memoria", "Colore"]
    assert risultato["modalita"] == "attributi"


def test_anteprima_con_immagine_inesistente_si_ferma_prima(chiamate, tmp_path):
    risultato = _crea(
        attributi={"Colore": ["Nero"]},
        percorsi_immagini=[str(tmp_path / "manca.jpg")],
        alt_immagini=["x"],
    )

    assert risultato["creato"] is False
    assert "manca.jpg" in risultato["errore"]
    assert chiamate == []


def test_creazione_carica_le_immagini_e_poi_manda_il_prodotto(chiamate, tmp_path):
    foto1, foto2 = tmp_path / "a.jpg", tmp_path / "b.jpg"
    foto1.write_bytes(b"1")
    foto2.write_bytes(b"2")

    risultato = _crea(
        attributi={"Colore": ["Nero"]},
        percorsi_immagini=[str(foto1), str(foto2)],
        alt_immagini=["alt uno", "alt due"],
        anteprima=False,
    )

    assert [c["url"].rsplit("/", 1)[-1] for c in chiamate] == ["media", "media", "prodotti"]
    corpo = chiamate[-1]["json"]
    assert "solo_anteprima" not in corpo
    assert corpo["immagine_evidenza_id"] == 101
    assert corpo["galleria_ids"] == [102]
    assert corpo["alt_immagini"] == {101: "alt uno", 102: "alt due"}
    assert risultato["prodotto_id"] == 9
    assert "avvisi_seo" in risultato


def test_creazione_senza_immagini_non_manda_immagine_evidenza(chiamate):
    _crea(attributi={"Colore": ["Nero"]}, anteprima=False)

    assert "immagine_evidenza_id" not in chiamate[-1]["json"]
    assert chiamate[-1]["json"]["galleria_ids"] == []


def test_un_rifiuto_del_plugin_torna_con_il_messaggio_vero(monkeypatch):
    def post_rifiuto(url, **kwargs):
        return _Risposta(
            {"code": "x", "message": "Le combinazioni sono 64: al massimo 50 varianti."}, 400
        )

    monkeypatch.setattr(requests, "post", post_rifiuto)

    risultato = _crea(attributi={"A": ["1"]})

    assert risultato["creato"] is False
    assert "HTTP 400" in risultato["errore"]
    assert "al massimo 50 varianti" in risultato["errore"]


def test_la_scansione_cartelle_legge_la_riga_varianti_senza_interpretare_il_resto(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(product_sync, "_nomi_prodotti_esistenti", lambda: set())
    con = tmp_path / "Smartphone" / "Telefono A"
    senza = tmp_path / "Smartphone" / "Telefono B"
    mal = tmp_path / "Smartphone" / "Telefono C"
    for cartella, testo in (
        (
            con,
            "prezzo: 700 euro\n"
            "varianti: Colore: Nero, Bianco | Memoria: 256 GB, 512 GB\n"
            "DESCRIZIONE\n",
        ),
        (senza, "prezzo: 700 euro\nDisponibile in nero e bianco.\n"),
        (mal, "varianti: Colore Nero\n"),
    ):
        cartella.mkdir(parents=True)
        (cartella / "testo.txt").write_text(testo, encoding="utf-8")
        (cartella / "foto.jpg").write_bytes(b"x")

    nuovi = {p["nome"]: p for p in product_sync.scansiona_cartella_prodotti(str(tmp_path))["nuovi"]}

    assert nuovi["Telefono A"]["varianti"]["errori"] == []
    assert nuovi["Telefono A"]["varianti"]["attributi"][1] == {
        "nome": "Memoria",
        "valori": ["256 GB", "512 GB"],
    }
    assert nuovi["Telefono B"]["varianti"] is None  # niente riga: le ricava l'assistente
    assert nuovi["Telefono C"]["varianti"]["errori"]
