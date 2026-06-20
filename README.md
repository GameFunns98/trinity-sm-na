# EMS / RP evidence směn a nákupů

Lokální webová aplikace pro evidenci směn a nákupů vybavení pro EMS / RP organizaci. Aplikace používá Python 3, Flask a SQLite, takže nepotřebuje Docker ani externí databázi.

## Funkce

- Dashboard s počtem směn, nákupů a celkovým počtem odpracovaných hodin.
- Evidence směn s automatickým výpočtem délky směny.
- Evidence nákupů s více položkami v jednom záznamu.
- Přidání, úprava a smazání záznamů.
- Potvrzení před smazáním.
- Vyhledávání a filtrování podle data.
- Export směn a nákupů do CSV.
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

## Poznámky

- Povinná pole jsou označena hvězdičkou.
- Směna se uloží pouze tehdy, pokud je čas do větší než čas od.
- U nákupu musí být vyplněna alespoň jedna položka.
- CSV export používá středník jako oddělovač a UTF-8 BOM pro lepší otevření v Excelu.
