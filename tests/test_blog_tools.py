import pytest
import requests

from push_contempt_mcp import blog_tools


class _Risposta:
    def __init__(self, dati, stato=200):
        self._dati = dati
        self.status_code = stato
        self.text = str(dati)

    def raise_for_status(self):
        if self.status_code >= 400:
            errore = requests.HTTPError(f"{self.status_code} Client Error")
            errore.response = self
            raise errore

    def json(self):
        return self._dati


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("WP_SITE_URL", "https://localhost")
    monkeypatch.setenv("WP_APP_USER", "Andrea")
    monkeypatch.setenv("WP_APP_PASSWORD", "segreto")


def _finto(monkeypatch, risposte):
    """Sostituisce requests.request: `risposte` mappa (metodo, percorso finale) -> _Risposta.
    Restituisce la lista delle chiamate fatte."""
    chiamate = []

    def request_finto(metodo, url, **resto):
        chiamate.append({"metodo": metodo, "url": url, **resto})
        for (m, fine), risposta in risposte.items():
            if m == metodo and url.endswith(fine):
                return risposta
        raise AssertionError(f"chiamata inattesa: {metodo} {url}")

    monkeypatch.setattr(requests, "request", request_finto)
    return chiamate


BUONO = (
    "<h2>Come scegliere lo zaino trekking</h2><p>Lo zaino trekking giusto pesa poco. "
    "Uno zaino trekking leggero stanca meno. Leggi la "
    '<a href="https://esempio.it/guida">guida</a>.</p>'
)
META_OK = (
    "Peso, volume e schienale: la guida pratica per scegliere lo zaino trekking giusto "
    "per le tue uscite in montagna, senza spendere troppo."
)


def test_articolo_in_regola_non_ha_avvisi():
    avvisi = blog_tools.valida_articolo(
        BUONO, "zaino trekking", "Scegliere lo zaino trekking", META_OK, None, 1, 1, True
    )

    assert avvisi == []


def test_senza_frase_chiave_lo_dice():
    avvisi = blog_tools.valida_articolo(BUONO, "", "Titolo", META_OK)

    assert any("Manca la frase chiave" in a for a in avvisi)


def test_frase_chiave_poco_usata_e_non_nei_sottotitoli():
    avvisi = blog_tools.valida_articolo(
        "<h2>Altro</h2><p>Un zaino trekking.</p>", "zaino trekking", "T", META_OK
    )

    assert any("compare 1 volta" in a for a in avvisi)
    assert any("Nessun H2/H3 contiene" in a for a in avvisi)


def test_struttura_h1_nel_testo_e_senza_h2():
    avvisi = blog_tools.valida_articolo("<h1>Titolo</h1><p>zaino zaino</p>", "zaino", "T", META_OK)

    assert any("Nessun sottotitolo H2" in a for a in avvisi)
    assert any("H1" in a for a in avvisi)


def test_testo_troppo_corto_rispetto_al_brief():
    avvisi = blog_tools.valida_articolo(
        BUONO, "zaino trekking", "T", META_OK, lunghezza_attesa=1200
    )

    assert any("circa 1200" in a for a in avvisi)
    assert not any(
        "circa" in a for a in blog_tools.valida_articolo(BUONO, "zaino trekking", "T", META_OK, 20)
    )


def test_lunghezze_di_titolo_seo_e_meta():
    avvisi = blog_tools.valida_articolo(BUONO, "zaino trekking", "x" * 61, "troppo breve")

    assert any("61 caratteri" in a for a in avvisi)
    assert any("12 caratteri" in a for a in avvisi)
    vuoti = blog_tools.valida_articolo(BUONO, "zaino trekking", "", "")
    assert any("Manca il titolo SEO" in a for a in vuoti)
    assert any("Manca la meta description" in a for a in vuoti)


def test_link_immagine_e_segnaposto():
    avvisi = blog_tools.valida_articolo(
        BUONO + "<p>[inserire fonte]</p>", "zaino trekking", "T", META_OK, None, 0, 0, False
    )

    assert any("Nessun link interno" in a for a in avvisi)
    assert any("Nessun link esterno" in a for a in avvisi)
    assert any("immagine in evidenza" in a for a in avvisi)
    assert any("segnaposto" in a for a in avvisi)


def test_link_sconosciuti_non_generano_avvisi():
    avvisi = blog_tools.valida_articolo(
        BUONO, "zaino trekking", "T", META_OK, None, None, None, True
    )

    assert not any("link" in a.lower() for a in avvisi)


def test_crea_articolo_manda_solo_i_campi_presenti_e_aggiunge_gli_avvisi(monkeypatch):
    chiamate = _finto(
        monkeypatch,
        {
            ("GET", "blog/brief"): _Risposta({"lunghezza_parole": 1200, "compilato": True}),
            ("POST", "blog/articoli"): _Risposta(
                {
                    "esito": "creato_in_bozza",
                    "articolo_id": 7,
                    "n_link_interni": 0,
                    "n_link_esterni": 1,
                }
            ),
        },
    )

    risultato = blog_tools.crea_articolo_bozza(
        "Titolo", BUONO, "zaino trekking", "Titolo SEO", META_OK, categoria="Guide"
    )

    invio = next(c for c in chiamate if c["metodo"] == "POST")
    assert invio["json"] == {
        "titolo": "Titolo",
        "contenuto": BUONO,
        "titolo_seo": "Titolo SEO",
        "meta_description": META_OK,
        "parola_chiave_focus": "zaino trekking",
        "categoria": "Guide",
    }
    assert invio["verify"] is False
    assert risultato["articolo_id"] == 7
    assert any("Nessun link interno" in a for a in risultato["avvisi"])
    assert any("immagine in evidenza" in a for a in risultato["avvisi"])


def test_un_titolo_duplicato_diventa_un_errore_con_l_id_esistente(monkeypatch):
    corpo = {
        "code": "push_contempt_articolo_duplicato",
        "message": "Esiste gia' un articolo con questo titolo",
        "data": {"status": 409, "articolo_id": 3},
    }
    _finto(
        monkeypatch,
        {
            ("GET", "blog/brief"): _Risposta({}),
            ("POST", "blog/articoli"): _Risposta(corpo, 409),
        },
    )

    risultato = blog_tools.crea_articolo_bozza("Titolo", BUONO, "zaino", "T", META_OK)

    assert risultato["articolo_id"] == 3
    assert "HTTP 409" in risultato["errore"]
    assert "avvisi" not in risultato


def test_aggiorna_rilegge_l_articolo_per_gli_avvisi(monkeypatch):
    completo = {
        "contenuto": BUONO,
        "parola_chiave_focus": "zaino trekking",
        "titolo_seo": "Scegliere lo zaino trekking",
        "meta_description": META_OK,
        "immagine_evidenza_id": 5,
    }
    chiamate = _finto(
        monkeypatch,
        {
            ("GET", "blog/brief"): _Risposta({"lunghezza_parole": 20}),
            ("POST", "blog/articoli/9"): _Risposta(
                {"esito": "aggiornato", "n_link_interni": 2, "n_link_esterni": 1}
            ),
            ("GET", "blog/articoli/9"): _Risposta(completo),
        },
    )

    risultato = blog_tools.aggiorna_articolo_bozza(9, titolo="Nuovo titolo")

    assert next(c for c in chiamate if c["metodo"] == "POST")["json"] == {"titolo": "Nuovo titolo"}
    assert risultato["avvisi"] == []


def test_aggiorna_di_un_articolo_pubblicato_restituisce_l_errore(monkeypatch):
    corpo = {
        "code": "push_contempt_articolo_non_in_bozza",
        "message": "e' publish",
        "data": {"status": 409},
    }
    _finto(monkeypatch, {("POST", "blog/articoli/4"): _Risposta(corpo, 409)})

    risultato = blog_tools.aggiorna_articolo_bozza(4, titolo="x")

    assert "HTTP 409" in risultato["errore"]


def test_lista_rifiuta_uno_stato_sconosciuto():
    assert "errore" in blog_tools.lista_articoli(stato="trash")


def test_salva_brief_manda_solo_i_campi_dati(monkeypatch):
    chiamate = _finto(monkeypatch, {("POST", "blog/brief"): _Risposta({"compilato": True})})

    blog_tools.salva_brief_blog(argomento="Zaini", n_articoli=4)

    assert chiamate[0]["json"] == {"argomento": "Zaini", "n_articoli": 4}


def test_carica_immagine_serve_alt_e_file(tmp_path):
    foto = tmp_path / "zaino.jpg"
    foto.write_bytes(b"x")

    assert "ALT" in blog_tools.carica_immagine_blog(str(foto), "  ")["errore"]
    assert (
        "non trovata" in blog_tools.carica_immagine_blog(str(tmp_path / "no.jpg"), "alt")["errore"]
    )


def test_carica_immagine_la_manda_a_wordpress_e_imposta_l_alt(monkeypatch, tmp_path):
    foto = tmp_path / "zaino.jpg"
    foto.write_bytes(b"finta-immagine")
    chiamate = []

    def post_finto(url, **resto):
        chiamate.append({"url": url, **resto})
        if url.endswith("/wp/v2/media"):
            return _Risposta(
                {"id": 55, "source_url": "https://localhost/wp-content/uploads/zaino.jpg"}
            )
        return _Risposta({})

    monkeypatch.setattr(requests, "post", post_finto)

    risultato = blog_tools.carica_immagine_blog(str(foto), "Zaino rosso su un sentiero")

    assert risultato == {
        "id": 55,
        "url": "https://localhost/wp-content/uploads/zaino.jpg",
        "alt": "Zaino rosso su un sentiero",
    }
    assert chiamate[0]["headers"]["Content-Type"] == "image/jpeg"
    assert chiamate[0]["data"] == b"finta-immagine"
    assert chiamate[1]["url"].endswith("/wp/v2/media/55")
    assert chiamate[1]["json"] == {"alt_text": "Zaino rosso su un sentiero"}
