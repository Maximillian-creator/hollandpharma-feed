"""
Holland Pharma — add-feed (nieuwe producten aanmaken) voor Stock Sync
=====================================================================
Zelfde witte lijst en leeslaag als scraper.py, maar met alles wat een nieuw product
nodig heeft: titel, merk, type, tags, foto en een beschrijving met de etiketinformatie.

Snoep is een levensmiddel: wie het online verkoopt, moet de verplichte informatie vóór
de aankoop tonen (EU 1169/2011 art. 14): ingrediënten, voedingswaarde, bewaaradvies en
wie het in de handel brengt. Die komen hier letterlijk van het etiket (Holland Pharma),
zodat het product ook zonder Nova-tekst klopt. Een product zonder ingrediëntenlijst
komt NIET in de add-feed (wel in de update-feed): eerst het etiket, dan de winkel.

- tags: `drempelvuller` (voor de winkelwagen-collectie), `hollandpharma`, btw-tag
- published=false: Max zet ze zelf live na Nova en Themis
- price = adviesprijs incl. btw; voorraad loopt via de update-feed
"""
from __future__ import annotations

import html
import xml.etree.ElementTree as ET

import hp
from scraper import save_xml

OUTPUT_FILE = "hollandpharma_add_feed.xml"


def beschrijving(p: dict) -> str:
    e = html.escape
    delen = [f"<p>{e(p['merk'])} {e(p['omschrijving'])}, {e(p['inhoud'].lower())}.</p>"]
    delen.append(f"<p><strong>Ingrediënten:</strong> {e(p['ingredienten'])}</p>")
    if p.get("allergenen"):
        delen.append(f"<p><strong>Allergenen:</strong> {e(p['allergenen'])}</p>")
    waarden = p.get("voedingswaarde") or []
    if waarden:
        kop = next((w for n, w in waarden if not n), "Voedingswaarde")
        regels = "".join(f"<li>{e(n)}: {e(w)}</li>" for n, w in waarden if n)
        delen.append(f"<p><strong>{e(kop)}</strong></p><ul>{regels}</ul>")
    if p.get("gebruik"):
        delen.append(f"<p><strong>Gebruik:</strong> {e(p['gebruik'])}</p>")
    if p.get("bewaren"):
        delen.append(f"<p><strong>Bewaren:</strong> {e(p['bewaren'])}</p>")
    if p.get("verantwoordelijk"):
        delen.append(f"<p><strong>In de handel gebracht door:</strong> {e(p['verantwoordelijk'])}</p>")
    return "\n".join(delen)


def bouw(artikelen: list[str], gelezen: dict[str, dict]) -> tuple[ET.Element, list[str]]:
    root = ET.Element("products")
    zonder_etiket = []
    for artikel in artikelen:
        p = gelezen.get(artikel) or {}
        if not p or not p.get("avp"):
            continue
        if not p.get("ingredienten"):
            zonder_etiket.append(f"{artikel} {p['merk']} {p['omschrijving']}")
            continue
        leverbaar, _ = hp.beschikbaar(p)
        tags = ", ".join(t for t in ("drempelvuller", "hollandpharma", p["artikelgroep"].lower(), hp.btw_tag(p)) if t)
        item = ET.SubElement(root, "product")
        for tag, waarde in (("handle", hp.handle(p)), ("title", hp.titel(p)), ("vendor", p["merk"]),
                            ("brand", p["merk"]), ("product_type", p["artikelgroep"]), ("tags", tags),
                            ("published", "false"), ("btw", p["btw"]), ("description", beschrijving(p)),
                            ("ingredienten", p["ingredienten"]), ("bewaren", p.get("bewaren", "")),
                            ("waarschuwingen", p.get("gebruik", ""))):
            ET.SubElement(item, tag).text = waarde
        ET.SubElement(ET.SubElement(ET.SubElement(item, "images"), "image"), "src").text = p["foto"]
        variant = ET.SubElement(ET.SubElement(item, "variants"), "variant")
        for tag, waarde in (("sku", hp.sku(p)), ("barcode", p["ean"]), ("price", f"{p['avp']:.2f}"),
                            ("compare_at_price", ""), ("available", "true" if leverbaar else "false"),
                            ("variant_title", "Default"), ("option1", "Default"), ("image", p["foto"])):
            ET.SubElement(variant, tag).text = waarde
    return root, zonder_etiket


def main() -> None:
    artikelen = hp.lees_witte_lijst()
    print(f"Holland Pharma add-feed: {len(artikelen)} artikelen op de witte lijst")
    gelezen = hp.haal_alles(artikelen)
    hp.rem(gelezen)
    root, zonder_etiket = bouw(artikelen, gelezen)
    for regel in zonder_etiket:
        print(f"   NIET in de add-feed (geen ingrediëntenlijst op de pagina): {regel}")
    print(f"{len(root.findall('product'))} producten in de add-feed")
    save_xml(root, OUTPUT_FILE)
    print(f"https://raw.githubusercontent.com/Maximillian-creator/hollandpharma-feed/main/{OUTPUT_FILE}")


if __name__ == "__main__":
    main()
