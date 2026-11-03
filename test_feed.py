"""Tests op echte (uitgelogde) Holland Pharma-pagina's in testdata/. Geen netwerk."""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET

import add_scraper
import hp
import scraper

HIER = os.path.dirname(os.path.abspath(__file__))


def pagina(artikel: str) -> str:
    with open(os.path.join(HIER, "testdata", f"{artikel}_uitgelogd.html"), "rb") as f:
        return hp.decodeer(f.read())


def test_decodeer_mengt_utf8_en_cp1252():
    assert hp.decodeer("Ingrediënten ".encode("utf-8") + b"Ingredi\xebnten 12-25\xb0C") == \
        "Ingrediënten Ingrediënten 12-25°C"


def test_klepper_velden():
    p = hp.lees_product(pagina("932561"), "932561")
    assert p["merk"] == "Klepper & Klepper"
    assert p["omschrijving"] == "De beste drop ooit honing"
    assert p["ean"] == "8719326064444"
    assert p["avp"] == 4.25
    assert p["balk"] == 3 and hp.beschikbaar(p) == (True, 2)
    assert hp.btw_tag(p) == "vat-low"
    assert p["foto"].endswith("/photos/932561/photo.jpg")
    assert p["ingredienten"].startswith("Suiker, glucosestroop")
    assert "honing (12%)" in p["ingredienten"]
    assert "hoge bloeddruk" in p["gebruik"]
    assert p["bewaren"] == "Droog, afgesloten en koel (12-25°C) bewaren."
    assert p["verantwoordelijk"] == "Klepper & Klepper"


def test_voedingswaarde_per_regel_gesplitst():
    p = hp.lees_product(pagina("932561"), "932561")
    w = dict(p["voedingswaarde"])
    assert w[""] == "Voedingswaarde per 100 gram"
    assert w["Energie"] == "1471 kJ / 346 kcal"
    assert w["- waarvan suikers"] == "58 gram"
    assert w["Koolhydraten"] == "85 gram"
    assert w["Zout"] == "0,14 gram"


def test_barkleys_ruim_voorraad():
    p = hp.lees_product(pagina("910213"), "910213")
    assert p["merk"] == "Barkleys" and p["avp"] == 1.99
    assert hp.beschikbaar(p) == (True, 20)
    assert p["ean"] == "87313260"


def test_verkeerd_artikel_geeft_leeg():
    assert hp.lees_product(pagina("932561"), "910213") == {}


def test_titel_en_handle():
    p = hp.lees_product(pagina("932561"), "932561")
    assert hp.titel(p) == "De beste drop ooit honing - 200 gram"
    assert hp.handle(p) == "klepper-klepper-de-beste-drop-ooit-honing-200-gram"
    assert hp.sku(p) == "HP-932561"


def test_voorraadbalk():
    for balk, verwacht in ((6, (True, 20)), (5, (True, 10)), (4, (True, 5)), (3, (True, 2)),
                           (2, (False, 0)), (1, (False, 0)), (None, (False, 0))):
        assert hp.beschikbaar({"balk": balk}) == verwacht


def test_witte_lijst_geldig():
    merken, los, weg = hp.lees_witte_lijst(os.path.join(HIER, "witte_lijst.txt"))
    assert merken == ["Klepper&Klepper", "Barkleys", "Pukka", "Yogi Tea", "Piramide"]
    assert all(a.isdigit() for a in los) and all(a.isdigit() for a in weg)


def test_witte_lijst_vormen(tmp_path):
    pad = tmp_path / "wl.txt"
    pad.write_text("merk: Yogi Tea  # thee\n932561\n-290647\n\n# commentaar\n", encoding="utf-8")
    assert hp.lees_witte_lijst(str(pad)) == (["Yogi Tea"], ["932561"], {"290647"})
    pad.write_text("Yogi Tea\n", encoding="utf-8")
    import pytest
    with pytest.raises(SystemExit):
        hp.lees_witte_lijst(str(pad))


def test_zoekpagina():
    with open(os.path.join(HIER, "testdata", "zoek_pukka_p1.html"), "rb") as f:
        tot, ids = hp.lees_zoekpagina(hp.decodeer(f.read()))
    assert tot == 28 and len(ids) == 25 and ids[0] == "932166"
    with open(os.path.join(HIER, "testdata", "zoek_pukka_p2.html"), "rb") as f:
        tot2, ids2 = hp.lees_zoekpagina(hp.decodeer(f.read()))
    assert tot2 == 28 and len(ids2) == 3 and not set(ids) & set(ids2)


class _Nep:
    """Nep-sessie die de twee opgeslagen Pukka-pagina's teruggeeft."""
    def __init__(self, paginas):
        self.paginas = paginas

    def get(self, url, params=None, timeout=None):
        class R:
            pass
        r = R()
        r.content = self.paginas.get(params["page"], b"")
        r.raise_for_status = lambda: None
        return r


def test_zoek_merk_alle_paginas_en_stop_bij_half():
    import pytest
    p = {}
    for n in (1, 2):
        with open(os.path.join(HIER, "testdata", f"zoek_pukka_p{n}.html"), "rb") as f:
            p[n] = f.read()
    hp.PAUZE_S = 0
    assert len(hp.zoek_merk(_Nep(p), "Pukka")) == 28
    with pytest.raises(SystemExit):
        hp.zoek_merk(_Nep({1: p[1]}), "Pukka")       # pagina 2 weg → 25 van 28 → STOP


def test_update_feed_houdt_onleesbare_regel_vast():
    vorig_root = ET.fromstring("<products><product><sku>HP-910213</sku><price>1.99</price></product></products>")
    vorig = {"HP-910213": vorig_root[0]}
    gelezen = {"932561": hp.lees_product(pagina("932561"), "932561"), "910213": {}}
    root = scraper.bouw(["932561", "910213"], gelezen, vorig)
    skus = [el.findtext("sku") for el in root.iter("product")]
    assert skus == ["HP-932561", "HP-910213"]
    eerste = root.find("product")
    assert eerste.findtext("price") == "4.25" and eerste.findtext("available") == "true"
    assert eerste.findtext("quantity") == "2"


def test_rem_stopt_bij_te_veel_onleesbaar():
    import pytest
    with pytest.raises(SystemExit):
        hp.rem({"1": {}, "2": {}, "3": {"x": 1}})
    hp.rem({str(i): {"x": 1} for i in range(9)} | {"9": {}})   # 10% mag


def test_add_feed_bevat_etiket_en_geen_inkoop():
    gelezen = {a: hp.lees_product(pagina(a), a) for a in ("932561", "910213")}
    root, zonder, niet = add_scraper.bouw(["932561", "910213"], gelezen)
    assert len(root.findall("product")) == 2 and zonder == [] and niet == []
    k = root.find("product")
    assert k.findtext("published") == "false"
    assert "drempelvuller" in k.findtext("tags")
    oms = k.findtext("description")
    assert "<strong>Ingrediënten:</strong> Suiker" in oms
    assert "<li>Energie: 1471 kJ / 346 kcal</li>" in oms
    assert "In de handel gebracht door" in oms
    xml = ET.tostring(root, encoding="unicode").lower()
    assert "inkoop" not in xml and "aip" not in xml


def test_add_feed_is_plat():
    # Stock Sync slaat een <variants> met één <variant> stil over (Kala 24-09).
    gelezen = {a: hp.lees_product(pagina(a), a) for a in ("932561", "910213")}
    root, _, _ = add_scraper.bouw(["932561", "910213"], gelezen)
    assert root.find(".//variants") is None and root.find(".//images") is None
    k = root.find("product")
    assert k.findtext("sku") == "HP-932561" and k.findtext("price") == "4.25"
    assert k.findtext("option1") == "Default Title" and k.findtext("image").endswith("/photo.jpg")


def test_add_feed_slaat_product_zonder_ingredienten_over():
    p = dict(hp.lees_product(pagina("932561"), "932561"))
    p.pop("ingredienten")
    root, zonder, _ = add_scraper.bouw(["932561"], {"932561": p})
    assert len(root.findall("product")) == 0 and len(zonder) == 1


def test_add_feed_drempelvuller_tag_tot_15_en_niet_leverbaar_overslaan():
    basis = hp.lees_product(pagina("932561"), "932561")
    duur = dict(basis, avp=18.99)
    op = dict(basis, artikel="1", balk=1)
    root, _, niet = add_scraper.bouw(["932561", "2", "1"], {"932561": basis, "2": dict(duur, artikel="2"), "1": op})
    tags = [el.findtext("tags") for el in root.iter("product")]
    assert len(tags) == 2 and "drempelvuller" in tags[0] and "drempelvuller" not in tags[1]
    assert len(niet) == 1


def test_aroma_apostrof():
    assert hp._tekst("aroma&quot;s, glansmiddel") == "aroma's, glansmiddel"
