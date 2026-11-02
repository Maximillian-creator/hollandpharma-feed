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
    lijst = hp.lees_witte_lijst(os.path.join(HIER, "witte_lijst.txt"))
    assert len(lijst) == 25 and all(a.isdigit() for a in lijst)


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
    root, zonder = add_scraper.bouw(["932561", "910213"], gelezen)
    assert len(root.findall("product")) == 2 and zonder == []
    k = root.find("product")
    assert k.findtext("published") == "false"
    assert "drempelvuller" in k.findtext("tags")
    oms = k.findtext("description")
    assert "<strong>Ingrediënten:</strong> Suiker" in oms
    assert "<li>Energie: 1471 kJ / 346 kcal</li>" in oms
    assert "In de handel gebracht door" in oms
    xml = ET.tostring(root, encoding="unicode").lower()
    assert "inkoop" not in xml and "aip" not in xml


def test_add_feed_slaat_product_zonder_ingredienten_over():
    p = dict(hp.lees_product(pagina("932561"), "932561"))
    p.pop("ingredienten")
    root, zonder = add_scraper.bouw(["932561"], {"932561": p})
    assert len(root.findall("product")) == 0 and len(zonder) == 1


def test_aroma_apostrof():
    assert hp._tekst("aroma&quot;s, glansmiddel") == "aroma's, glansmiddel"
