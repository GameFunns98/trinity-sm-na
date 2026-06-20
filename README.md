# EMS / RP evidence směn a nákupů

Lokální webová aplikace pro evidenci aktivních směn a nákupů vybavení pro EMS / RP organizaci. Aplikace používá Python 3, Flask a SQLite, takže nepotřebuje Docker ani externí databázi.

## Funkce

- Aktivní časovač směny v pravém horním rohu aplikace.
- Zahájení směny přes modální okno: jméno, volací znak, vozidlo a volitelná poznámka.
- Ukončení směny jedním tlačítkem, automatický zápis konce, výpočet délky a vytvoření Discord zprávy.
- Pokus o automatické zkopírování Discord zprávy do schránky přes `navigator.clipboard.writeText(text)`.
- Evidence nákupů napojená na aktivní směnu.
- Katalog položek s výchozí cenou a váhou.
- Více položek v jednom nákupu, automatické doplnění ceny/váhy a živé součty.
- Dashboard se stavem aktuální směny, nákupy ve směně, celkovou cenou, celkovou váhou a posledními nákupy.
- Přidání, úprava a smazání nákupů, smazání směn, vyhledávání, filtrování podle data a CSV export.
- Responzivní tmavé administrátorské GUI.

## Struktura projektu

```text
app.py
requirements.txt
README.md
instance/database.db          # vytvoří se automaticky po spuštění
templates/base.html
templates/dashboard.html
templates/shifts.html
templates/shift_form.html
templates/purchases.html
templates/purchase_form.html
templates/_purchase_item_row.html
static/css/style.css
static/js/main.js
```

## Instalace na Windows

1. Nainstalujte Python 3.
2. Otevřete PowerShell nebo CMD ve složce projektu.
3. Vytvořte virtuální prostředí:

```powershell
python -m venv .venv
```

4. Aktivujte virtuální prostředí:

```powershell
.venv\Scripts\activate
```

5. Nainstalujte závislosti:

```powershell
pip install -r requirements.txt
```

## Spuštění

```powershell
python app.py
```

Poté otevřete prohlížeč na adrese:

```text
http://127.0.0.1:5000
```

Databáze SQLite se vytvoří automaticky v souboru `instance/database.db`.

## Výchozí katalog položek

- Rádio — cena 500, váha 100g
- Tazer — cena 3000, váha 227g
- Medibag — cena 10, váha 220g
- Bandáže — cena 10, váha 100g
- Defibrilátor — cena 10, váha 100g
- Pinzeta — cena 10, váha 100g
- Krém na popálení — cena 10, váha 100g
- Šicí souprava — cena 10, váha 100g
- Chladící obklad — cena 1, váha 200g

## Poznámky

- Nelze zahájit druhou směnu, pokud jedna už probíhá.
- Nákup bez aktivní směny je možný pouze po potvrzení uživatelem.
- CSV export používá středník jako oddělovač a UTF-8 BOM pro lepší otevření v Excelu.
