"""
Holland Pharma — update-feed (prijs + voorraad) voor Stock Sync
================================================================
Leest de producten uit `witte_lijst.txt` van klant.hollandpharma.nl (zonder inloggen,
zie hp.py) en schrijft `hollandpharma_feed.xml`: per product sku (HP-<artikelnr>),
barcode (EAN), titel, merk, adviesprijs incl. btw, beschikbaar en een geschat aantal.

Prijs = de adviesprijs (AVP) van Holland Pharma, incl. btw, 1-op-1. De inkoopprijs komt
nooit in de feed: dit repo is openbaar.

REM (les 31-08: een halve feed laat Stock Sync archiveren):
  - > 20% van de witte lijst niet te lezen → niets wegschrijven;
  - een product dat deze run niet te lezen is, houdt zijn regel uit de vorige feed;
  - prijzen gaan door prijsrem.py (> 3% afwijking zonder btw-patroon blijft staan).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from xml.dom import minidom

import hp

OUTPUT_FILE = "hollandpharma_feed.xml"


def vorige_regels(pad: str) -> dict[str, ET.Element]:
    try:
        return {(el.findtext("sku") or ""): el for el in ET.parse(pad).getroot().iter("product")}
    except (OSError, ET.ParseError):
        return {}


def bouw(artikelen: list[str], gelezen: dict[str, dict], vorig: dict[str, ET.Element]) -> ET.Element:
    root = ET.Element("products")
    for artikel in artikelen:
        p = gelezen.get(artikel) or {}
        if not p:
            oud = vorig.get(f"HP-{artikel}")
            if oud is not None:
                root.append(oud)
            continue
        if not p.get("avp"):
            print(f"   {artikel}: geen adviesprijs op de pagina — overgeslagen")
            oud = vorig.get(hp.sku(p))
            if oud is not None:
                root.append(oud)
            continue
        leverbaar, aantal = hp.beschikbaar(p)
        item = ET.SubElement(root, "product")
        for tag, waarde in (("sku", hp.sku(p)), ("barcode", p["ean"]), ("title", hp.titel(p)),
                            ("vendor", p["merk"]), ("price", f"{p['avp']:.2f}"),
                            ("available", "true" if leverbaar else "false"), ("quantity", str(aantal)),
                            ("handle", hp.handle(p)), ("tags", hp.btw_tag(p)),
                            ("beschikbaarheid", p["beschikbaarheid"])):
            ET.SubElement(item, tag).text = waarde
    return root


def save_xml(root: ET.Element, pad: str) -> None:
    for el in root.iter():                     # regels uit de vorige feed dragen hun opmaak mee
        el.tail = None
        if el.text is not None and not el.text.strip() and len(el):
            el.text = None
    pretty = minidom.parseString(ET.tostring(root, encoding="unicode")).toprettyxml(indent="  ")
    regels = pretty.split("\n")
    regels[0] = '<?xml version="1.0" encoding="UTF-8"?>'
    with open(pad, "w", encoding="utf-8") as f:
        f.write("\n".join(r for r in regels if r.strip()) + "\n")


def main() -> None:
    s = hp.sessie()
    print("Holland Pharma update-feed: witte lijst uitvouwen")
    artikelen, _ = hp.artikelen(s)
    print(f"   {len(artikelen)} artikelen in totaal")
    gelezen = hp.haal_alles(artikelen, s)
    hp.rem(gelezen)
    root = bouw(artikelen, gelezen, vorige_regels(OUTPUT_FILE))
    import prijsrem
    print(prijsrem.verslag(prijsrem.pas_toe(root, OUTPUT_FILE)))
    n = len(root.findall("product"))
    leverbaar = sum(1 for el in root.iter("product") if el.findtext("available") == "true")
    print(f"{n} regels, waarvan {leverbaar} leverbaar")
    save_xml(root, OUTPUT_FILE)
    print(f"https://raw.githubusercontent.com/Maximillian-creator/hollandpharma-feed/main/{OUTPUT_FILE}")


if __name__ == "__main__":
    main()
