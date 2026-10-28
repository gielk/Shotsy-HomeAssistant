# GLP-1 Tracker voor Home Assistant

Een vervanger voor de Shotsy-app, helemaal lokaal in Home Assistant. Houd je injecties bij, zie hoeveel medicatie
er naar schatting in je lichaam zit, laat je herinneren op je telefoon en volg je gewicht vanuit Apple Gezondheid.

Gemaakt voor retatrutide, maar werkt ook met tirzepatide (Mounjaro, Zepbound), semaglutide (Ozempic, Wegovy) of een
medicijn met een eigen halfwaardetijd.

## Wat het doet

- **Injecties registreren** met dosis, tijdstip, prikplek, pijn en notitie. Met één knop, vanuit een melding op je
  telefoon of met een actie.
- **Geschat medicatieniveau** nu, per dag en een verwachting voor de komende weken, ook met je geplande injecties erbij.
- **Planning**: volgende injectie een aantal dagen na de vorige, of op een vaste weekdag en tijd. Eenmalig verzetten kan.
- **Prikplekken afwisselen**: stelt de plek voor die het langst niet is gebruikt.
- **Gewicht** uit een sensor (bijvoorbeeld Apple Gezondheid via de companion app). Elke nieuwe waarde wordt bewaard.
  Totale verandering, procent, BMI, gemiddelde per week, afstand tot je doel en gewichtsverlies per dosis.
- **Agenda per dag**: bijwerkingen (0-10), notitie, calorieën en eiwitten. Plus een agenda-entiteit met alle injecties.
- **Shotsy-import**: neemt injecties, gewichten, bijwerkingen en notities over uit een Shotsy CSV-export.
- **Export** van alle gegevens als back-up.

Alles staat in Home Assistant zelf (`.storage/glp1_tracker.<id>`), dus ook in je gewone back-ups.

## Installatie

Via HACS: *HACS → ⋮ → Aangepaste repositories*, voeg deze repository toe als type *Integratie* en download
**GLP-1 Tracker**. Herstart Home Assistant.

Zonder HACS: kopieer `custom_components/glp1_tracker` naar de map `custom_components` in je config-map en herstart.

Daarna: *Instellingen → Apparaten en diensten → Integratie toevoegen → GLP-1 Tracker*.

| Veld | Uitleg |
| --- | --- |
| Medicatie | Bepaalt hoe het niveau wordt geschat. *Anders* vraagt om halfwaardetijd en tijd tot piek. |
| Naam | Komt in de entiteitnamen, standaard de medicatie (`sensor.retatrutide_...`). |
| Standaarddosis | Alleen voor de eerste injectie; daarna geldt de laatste dosis. |
| Dagen tussen injecties | Meestal 7. |
| Vaste weekdag / tijdstip | Optioneel. Met zaterdag 11:00 wordt het de zaterdag die het dichtst bij een week na de vorige ligt. |
| Gewichtsensor | Bijvoorbeeld `sensor.<iphone>_weight`. |
| Lengtesensor of lengte | Voor de BMI. |

Prikplekken en bijwerkingen pas je aan via *Configureren* bij de integratie.

## Gegevens uit Shotsy overnemen

Exporteer in Shotsy een CSV en zet het bestand in je config-map, bijvoorbeeld als `shotsy.csv`. Voer dan de actie uit:

```yaml
action: glp1_tracker.import_shotsy_csv
data:
  file_path: shotsy.csv
```

Of plak de inhoud van het bestand in `csv_text`. Met `replace: true` (standaard) worden de injecties en daglogs
vervangen; gewichten uit de sensor blijven staan. Bijwerkingen uit de export die je nog niet had, worden toegevoegd.

## Entiteiten

Met de naam *Retatrutide*:

| Entiteit | Wat |
| --- | --- |
| `sensor.retatrutide_medicatieniveau` | Geschat niveau nu (mg). Attributen: daggemiddelde, piek komende week, grafiekdata. |
| `sensor.retatrutide_volgende_injectie` | Tijdstip van de volgende injectie, met dosis, prikplek en nummer. |
| `sensor.retatrutide_laatste_injectie`, `_laatste_dosis`, `_aantal_injecties` | De laatste injectie en het totaal (met de hele lijst als attribuut). |
| `sensor.retatrutide_gewicht`, `_gewicht_verandering`, `_gewicht_verandering_procent`, `_bmi`, `_gewicht_per_week`, `_tot_doel` | Gewicht en resultaten. |
| `sensor.retatrutide_dagoverzicht` | Alles van de dag die in de agenda openstaat. |
| `button.retatrutide_injectie_registreren` | Registreert nu een injectie met de geplande dosis en plek. |
| `number.retatrutide_volgende_dosis`, `select.retatrutide_volgende_prikplek`, `datetime.retatrutide_volgende_injectie` | De volgende injectie aanpassen. |
| `number.retatrutide_interval`, `_doelgewicht`, `_startgewicht` | Instellingen. |
| `date.retatrutide_agendadag` | De dag in de agenda. De bijwerking-, calorie-, eiwit- en notitie-entiteiten volgen deze dag. |
| `number.retatrutide_bijwerking_<naam>`, `number.retatrutide_calorieen`, `_eiwitten`, `text.retatrutide_dagnotitie` | Daglog. |
| `calendar.retatrutide_agenda` | Injecties, geplande injectie en dagen met bijwerkingen. |

## Acties

| Actie | Wat |
| --- | --- |
| `glp1_tracker.log_injection` | Injectie registreren. Lege velden: geplande dosis, voorgestelde plek, nu. Geeft het ID terug. |
| `glp1_tracker.update_injection` | Injectie aanpassen (`injection_id`, of `last`). |
| `glp1_tracker.delete_injection` | Injectie verwijderen (`injection_id`, of `last`). |
| `glp1_tracker.log_day` | Bijwerkingen, notitie, calorieën of eiwitten voor een dag. |
| `glp1_tracker.log_weight` | Gewicht met de hand invoeren. |
| `glp1_tracker.import_shotsy_csv` | Shotsy-export importeren. |
| `glp1_tracker.export_data` | Alle gegevens teruggeven, als back-up. |

## Dashboard

`dashboard/glp1_dashboard.yaml` is een dashboard met tabbladen *Overzicht*, *Injecties*, *Resultaten*, *Agenda* en
*Instellingen*. Het heeft deze HACS-kaarten nodig: button-card, apexcharts-card, Simple Tabs Card, expander-card,
Stack In Card en config-template-card.

Maak een nieuw dashboard, open de *Raw configuration editor* en plak de inhoud. Voor een andere naam dan
*Retatrutide*, of met een kaart voor gezondheidsgegevens van je telefoon, maak je het opnieuw aan:

```sh
python dashboard/generate_dashboard.py --prefix retatrutide \
  --health-prefix sensor.iphone_van_jan --yaml dashboard/glp1_dashboard.yaml
```

## Herinnering

`examples/injectie_herinnering.yaml` is een automatisering die een melding stuurt op het geplande tijdstip, met de
knoppen *Gezet* (registreert de injectie) en *Over 1 uur*. Vervang `notify.mobile_app_jouw_telefoon` door je eigen
telefoon en plak hem in een nieuwe automatisering (*Bewerken in YAML*).

## Hoe het niveau wordt geschat

Elke injectie levert een curve op: hoeveel van de dosis na een bepaalde tijd nog in het lichaam zit. Het geschatte
niveau is de som van die curves van alle injecties.

- **Retatrutide**: een curve die is afgeleid van 13 maanden Shotsy-export (74 injecties). Piek na ongeveer anderhalve
  dag, daarna een halfwaardetijd van ongeveer 7 dagen. De uitkomst wijkt gemiddeld 0,12 mg af van wat Shotsy toont.
  De gepubliceerde halfwaardetijd is ongeveer 6 dagen (Urva e.a., *The Lancet* 2022).
- **Tirzepatide**: halfwaardetijd 5 dagen, piek na 1 dag (productinformatie Mounjaro).
- **Semaglutide**: halfwaardetijd 7 dagen, piek na 2 dagen (productinformatie Ozempic).
- **Anders**: je eigen halfwaardetijd en tijd tot piek.

Dit is een schatting om je schema te volgen, geen bloedwaarde en geen medisch advies.

## Ontwikkelen

```sh
pip install pytest-homeassistant-custom-component
pytest
```
