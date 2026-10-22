import pytest
import requests

from push_contempt_mcp import product_tools


class _RispostaFinta:
    def __init__(self, dati):
        self._dati = dati

    def raise_for_status(self):
        pass

    def json(self):
        return self._dati


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("WP_SITE_URL", "https://localhost")
    monkeypatch.setenv("WP_APP_USER", "Andrea")
    monkeypatch.setenv("WP_APP_PASSWORD", "segreto")


def test_crea_prodotto_carica_immagini_e_chiama_endpoint_prodotti(monkeypatch, tmp_path):
    foto1 = tmp_path / "foto1.jpg"
    foto2 = tmp_path / "foto2.jpg"
    foto1.write_bytes(b"finta-immagine-1")
    foto2.write_bytes(b"finta-immagine-2")

    chiamate_post = []

    def post_finto(url, auth, verify, timeout, headers=None, data=None, json=None):
        chiamate_post.append({"url": url, "headers": headers, "data": data, "json": json})
        if url.endswith("/wp-json/wp/v2/media"):
            attachment_id = 100 + len(chiamate_post)
            return _RispostaFinta({"id": attachment_id})
        return _RispostaFinta({"stato": "creato_in_bozza", "prodotto_id": 42})

    monkeypatch.setattr(requests, "post", post_finto)

    risultato = product_tools.crea_prodotto(
        titolo="Sedia da giardino",
        descrizione="<h2>Sedia da giardino</h2><p>Sedia da giardino comoda. "
        '<a href="/categoria-prodotto/sedie/">sedie</a> Sedia da giardino robusta.</p>',
        prezzo_regolare="39.90",
        categoria="Sedie",
        percorsi_immagini=[str(foto1), str(foto2)],
        alt_immagini=["vista frontale", "vista laterale"],
        frase_chiave_focus="sedia da giardino",
        titolo_seo="Sedia da giardino | Negozio di prova",
        meta_description="Scopri la nostra sedia da giardino.",
    )

    chiamate_media = [c for c in chiamate_post if c["url"].endswith("/wp/v2/media")]
    assert len(chiamate_media) == 2
    assert chiamate_media[0]["headers"] == {
        "Content-Disposition": 'attachment; filename="foto1.jpg"',
        "Content-Type": "image/jpeg",
    }

    chiamata_prodotto = next(c for c in chiamate_post if c["url"].endswith("/v1/prodotti"))
    assert chiamata_prodotto["json"]["immagine_evidenza_id"] == 101
    assert chiamata_prodotto["json"]["galleria_ids"] == [102]
    assert chiamata_prodotto["json"]["alt_immagini"] == {
        101: "vista frontale",
        102: "vista laterale",
    }
    assert chiamata_prodotto["json"]["categoria"] == "Sedie"

    assert risultato["prodotto_id"] == 42
    assert risultato["avvisi_seo"] == []


def test_crea_prodotto_richiede_stessa_lunghezza_di_alt_e_immagini(tmp_path):
    foto = tmp_path / "foto.jpg"
    foto.write_bytes(b"finta-immagine")

    with pytest.raises(ValueError):
        product_tools.crea_prodotto(
            titolo="X",
            descrizione="X",
            prezzo_regolare="1.00",
            categoria="X",
            percorsi_immagini=[str(foto)],
            alt_immagini=[],
            frase_chiave_focus="x",
            titolo_seo="x",
            meta_description="x",
        )


def test_prodotti_in_bozza_chiama_endpoint_giusto(monkeypatch):
    chiamate = []

    def get_finto(url, auth, verify, timeout):
        chiamate.append(url)
        return _RispostaFinta([{"id": 42, "titolo": "Sedia da giardino", "creato": "2026-10-21"}])

    monkeypatch.setattr(requests, "get", get_finto)

    risultato = product_tools.prodotti_in_bozza()

    assert chiamate[0] == "https://localhost/wp-json/push-contempt/v1/prodotti/bozze"
    assert risultato == [{"id": 42, "titolo": "Sedia da giardino", "creato": "2026-10-21"}]


def test_elenco_prodotti_chiama_endpoint_e_passa_ricerca_e_limite(monkeypatch):
    chiamate = []

    def get_finto(url, params, auth, verify, timeout):
        chiamate.append({"url": url, "params": params})
        return _RispostaFinta([{"id": 58, "titolo": "Gimbal S5", "stato": "publish"}])

    monkeypatch.setattr(requests, "get", get_finto)

    risultato = product_tools.elenco_prodotti(ricerca="gimbal", limite=5)

    assert risultato == [{"id": 58, "titolo": "Gimbal S5", "stato": "publish"}]
    assert chiamate[0]["url"] == "https://localhost/wp-json/push-contempt/v1/prodotti"
    assert chiamate[0]["params"] == {"ricerca": "gimbal", "limite": 5}


def test_elenco_prodotti_propaga_errori_http(monkeypatch):
    class RispostaErrore:
        def raise_for_status(self):
            raise requests.HTTPError("500")

    monkeypatch.setattr(requests, "get", lambda *a, **k: RispostaErrore())

    with pytest.raises(requests.HTTPError):
        product_tools.elenco_prodotti()
