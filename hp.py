"""
Holland Pharma — gedeelde leeslaag voor de update- en de add-feed (02-11-2026)
=============================================================================
Holland Pharma (klant.hollandpharma.nl) is de drogisterijgroothandel van de winkel in
Beverwijk. Er is geen feed of API; per artikelnummer is er een productpagina. Die toont
ook ZONDER inloggen: merk, omschrijving, inhoud, EAN, adviesprijs (AVP, incl. btw),
btw-code, voorraadbalk, artikelgroep, foto en de etiketinformatie (ingrediënten,
voedingswaarde, gebruik, bewaaradvies). Alleen de inkoopprijs zit achter de inlog, en
die hoort niet in een openbare feed. Deze scraper logt dus niet in en heeft geen
secrets nodig.

Welke producten erin komen bepaalt `witte_lijst.txt` (keuze Max), niet de catalogus:
Holland Pharma voert duizenden drogisterijartikelen, wij willen alleen de drempelvullers.

Tekencodering: de pagina is UTF-8, maar het blok Productinformatie komt er als
Windows-1252 in ("Ingredi\\xebnten", "12-25\\xb0C"). `decodeer()` leest UTF-8 en valt per
ongeldige byte terug op cp1252, zodat beide delen goed uitkomen.
"""
from __future__ import annotations

import codecs
import html
import os
import re
import time

BASIS = "https://klant.hollandpharma.nl"
UA = "Mozilla/5.0 (GoodForYou voorraadfeed; klant van Holland Pharma)"
PAUZE_S = 0.6
WITTE_LIJST = "witte_lijst.txt"

# Voorraadbalk 1-6 → beschikbaar + een aantal voor Stock Sync. Holland Pharma geeft geen
# stuks, alleen een balk; het aantal is dus een schatting, geen telling.
VOORRAAD = {6: 20, 5: 10, 4: 5, 3: 2}

# Merknaam zoals hij op de pagina staat → zoals hij in onze winkel heet.
MERKNAAM = {"Klepper&Klepper": "Klepper & Klepper"}


def _cp1252_terugval(fout: UnicodeDecodeError):
    stuk = fout.object[fout.start:fout.end]
    return stuk.decode("cp1252", errors="replace"), fout.end


codecs.register_error("hp_cp1252", _cp1252_terugval)


def decodeer(ruw: bytes) -> str:
    return ruw.decode("utf-8", errors="hp_cp1252")


# ── lezen ────────────────────────────────────────────────────────────────────

def lees_witte_lijst(pad: str = WITTE_LIJST) -> list[str]:
    """Artikelnummers, één per regel; alles na # is commentaar."""
    uit = []
    with open(pad, encoding="utf-8") as f:
        for regel in f:
            nr = regel.split("#", 1)[0].strip()
            if nr:
                if not nr.isdigit():
                    raise SystemExit(f"STOP: '{nr}' in {pad} is geen artikelnummer.")
                uit.append(nr)
    if len(uit) != len(set(uit)):
        raise SystemExit(f"STOP: dubbel artikelnummer in {pad}.")
    return uit


def _tekst(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = html.unescape(fragment).replace("\xa0", " ")
    fragment = re.sub(r'(\w)"s\b', r"\1's", fragment)          # de bron schrijft aroma"s
    regels = [re.sub(r"[ \t]+", " ", r).strip() for r in fragment.split("\n")]
    return "\n".join(r for r in regels if r).strip()


def _dl(pagina: str) -> dict[str, str]:
    return {_tekst(k): _tekst(v) for k, v in re.findall(r"<dt>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", pagina, re.S)}


def _bedrag(s: str) -> float | None:
    m = re.search(r"(\d+)[.,](\d{2})", s)
    return float(f"{m.group(1)}.{m.group(2)}") if m else None


def _voedingswaarde(tabel: str) -> list[tuple[str, str]]:
    """De tabel als (naam, waarde)-paren; cellen met <br> worden per regel gesplitst."""
    paren = []
    for rij in re.findall(r"<tr>(.*?)</tr>", tabel, re.S):
        cellen = [_tekst(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", rij, re.S)]
        if len(cellen) < 2:
            continue
        if cellen[0] and not cellen[1]:                 # kopregel: 'Voedingswaarde per 100 gram'
            paren.append(("", cellen[0]))
            continue
        namen, waarden = cellen[0].split("\n"), cellen[1].split("\n")
        if len(namen) == len(waarden):
            paren += [(n.strip(), w.strip()) for n, w in zip(namen, waarden)]
        else:
            paren.append((cellen[0].replace("\n", " "), cellen[1].replace("\n", " ")))
    return [(n, w) for n, w in paren if w]


def _productinformatie(pagina: str) -> dict:
    """Het blok onder 'Productinformatie': kopjes in <strong>, tekst erna, één tabel."""
    m = re.search(r'<section class="product_extra_information">.*?<div>(.*?)</div>\s*</section>', pagina, re.S)
    if not m:
        return {}
    blok = m.group(1)
    uit: dict = {}
    tabel = re.search(r"<table.*?</table>", blok, re.S)
    if tabel:
        uit["voedingswaarde"] = _voedingswaarde(tabel.group(0))
        blok = blok.replace(tabel.group(0), "")
    delen = re.split(r"<strong>(.*?)</strong>", blok, flags=re.S)
    # delen = [voor, kop1, tekst1, kop2, tekst2, ...]
    for i in range(1, len(delen) - 1, 2):
        kop = _tekst(delen[i]).rstrip(":").lower()
        tekst = _tekst(delen[i + 1])
        if kop.startswith("ingredi"):
            uit["ingredienten"] = tekst
        elif kop.startswith("gebruik") or kop.startswith("waarschuw"):
            uit["gebruik"] = tekst
        elif kop.startswith("bewaar"):
            uit["bewaren"] = tekst
        elif kop.startswith("verantwoordelijk"):
            uit["verantwoordelijk"] = tekst
        elif kop.startswith("allergen"):
            uit["allergenen"] = tekst
    return uit


def lees_product(pagina: str, artikel: str) -> dict:
    """Alles wat de feeds nodig hebben uit één productpagina. Leeg dict = niet te lezen."""
    if f"<dd id=\"product_details_code\">{artikel}</dd>" not in pagina:
        return {}
    dl = _dl(pagina)
    balk = re.search(r'class="product_stock">\s*<img src="/include/product/bar/(\d)\.svg"', pagina)
    avp = re.search(r"<span>Advies verkoopprijs</span>\s*<strong>(.*?)</strong>", pagina, re.S)
    btw = re.search(r"<span>BTW</span>\s*<strong>(.*?)</strong>", pagina, re.S)
    merk = dl.get("Merk", "")
    p = {
        "artikel": artikel,
        "merk": MERKNAAM.get(merk, merk),
        "omschrijving": dl.get("Omschrijving", ""),
        "inhoud": dl.get("Inhoud", ""),
        "ean": dl.get("EAN code", ""),
        "artikelgroep": dl.get("Artikelgroep", ""),
        "beschikbaarheid": dl.get("Beschikbaarheid", ""),
        "balk": int(balk.group(1)) if balk else None,
        "avp": _bedrag(html.unescape(avp.group(1))) if avp else None,
        "btw": _tekst(btw.group(1)) if btw else "",
        "foto": f"{BASIS}/photos/{artikel}/photo.jpg" if f"/photos/{artikel}/photo.jpg" in pagina else "",
    }
    p.update(_productinformatie(pagina))
    return p


def beschikbaar(p: dict) -> tuple[bool, int]:
    aantal = VOORRAAD.get(p.get("balk") or 0, 0)
    return aantal > 0, aantal


def sku(p: dict) -> str:
    return f"HP-{p['artikel']}"


def titel(p: dict) -> str:
    """'De beste drop ooit honing - 200 gram': merk staat apart in vendor."""
    inhoud = re.sub(r"\b(Gram|Stuks|Milliliter)\b", lambda m: m.group(1).lower(), p.get("inhoud", ""))
    return f"{p['omschrijving']} - {inhoud}" if inhoud else p["omschrijving"]


def handle(p: dict) -> str:
    """Merk + titel, zoals de rest van de winkel (geen 'hp-': de URL is voor de klant)."""
    tekst = f"{p['merk']} {titel(p)}".lower()
    for a, b in (("ë", "e"), ("é", "e"), ("è", "e"), ("ï", "i"), ("ö", "o"), ("ü", "u"), ("&", " ")):
        tekst = tekst.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", tekst).strip("-")


def btw_tag(p: dict) -> str:
    return "vat-low" if "9%" in p.get("btw", "") else "vat-high" if "21%" in p.get("btw", "") else ""


# ── ophalen ──────────────────────────────────────────────────────────────────

def sessie():
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = UA
    return s


def haal(s, artikel: str) -> dict:
    """Eén product; leeg dict als de pagina niet te lezen is (na één herhaling)."""
    for poging in (1, 2):
        try:
            r = s.get(f"{BASIS}/nl/assortiment/{artikel}/x", timeout=60)
            if r.status_code == 200:
                p = lees_product(decodeer(r.content), artikel)
                if p:
                    return p
        except Exception as fout:                      # netwerk: één keer opnieuw
            print(f"   {artikel}: {type(fout).__name__}")
        time.sleep(PAUZE_S * 3 * poging)
    return {}


def haal_alles(artikelen: list[str]) -> dict[str, dict]:
    s = sessie()
    uit = {}
    for i, artikel in enumerate(artikelen, 1):
        uit[artikel] = haal(s, artikel)
        if not uit[artikel]:
            print(f"   {artikel}: niet te lezen")
        if i < len(artikelen):
            time.sleep(PAUZE_S)
    return uit


def rem(gelezen: dict[str, dict], max_onleesbaar_pct: float = 20) -> None:
    """Een halve feed laat Stock Sync producten archiveren (les 31-08): niet wegschrijven."""
    if os.environ.get("FORCE_FEED") == "1":
        print("FORCE_FEED=1 — rem overgeslagen.")
        return
    n = len(gelezen)
    mis = sum(1 for p in gelezen.values() if not p)
    if n == 0:
        raise SystemExit("STOP: witte lijst leeg — geen feed weggeschreven.")
    if mis * 100 / n > max_onleesbaar_pct:
        raise SystemExit(f"STOP: {mis} van de {n} producten niet te lezen (> {max_onleesbaar_pct:.0f}%). "
                         "Vorige feed blijft staan.")
