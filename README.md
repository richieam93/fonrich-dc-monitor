# Fonrich DC Monitor für Home Assistant

Custom Integration für Fonrich FR-DCMG-MMPS über HF2211 (Modbus TCP Gateway oder RTU over TCP).

## Version 0.7.0 – Kasten- und Kanalansicht

Diese Version erzeugt standardmässig eine übersichtliche Struktur pro Fonrich-Controller:

### Kasten V1 / V2 / V3 / weitere Controller

- **Status Online**
- **Meldungen** – ein einziger lesbarer Textsensor pro Kasten
- **Spannung** in V
- **Gesamtstrom** in A
- **Gesamtleistung** in W
- Buttons:
  - Alarm und Trip zurücksetzen
  - Lichtbogen-Historie löschen
  - Lichtbogen-Selbsttest starten

### Pro Kanal

- **Kanal XX Ampere** in A
- **Kanal XX Spannung** in V
- **Kanal XX Leistung** in W
- **Kanal XX Max. Ampere heute** in A

Die Tagesmaxima werden gespeichert und um Mitternacht nach der lokalen Home-Assistant-Zeitzone zurückgesetzt.

> Der Fonrich liefert eine gemeinsame Busspannung pro Kasten und keine separate Spannung je String. Deshalb zeigt der Kanal-Spannungssensor die Busspannung des zugehörigen Kastens an.

## Gemeinsamer Meldungssensor

Zusätzlich wird ein Sensor **Fonrich Meldungen** erzeugt. Beispiele:

- `OK`
- `Lichtbogen bei Kasten V1, Kanal 02`
- `Lichtbogen bei Kasten V2, Kanal 05 (Dach West)`
- `Unterspannung bei Kasten V3`
- `Kasten V2 offline`
- mehrere Meldungen werden mit Semikolon zusammengefasst

Die detaillierten Alarm-Rohwerte und vielen einzelnen Alarm-Binary-Sensoren sind im Produktionsprofil standardmässig deaktiviert.

## Neue Dashboard-Karten

Die Ressource wird weiterhin automatisch unter folgender stabiler URL registriert:

`/fonrich_dc_monitor/fonrich-cards.js`

Im visuellen Karteneditor stehen danach zur Verfügung:

- **Fonrich Kästen und Kanäle** – alle Kästen und Kanäle in einer modernen Übersicht
- **Fonrich einzelner Kasten** – ein Kasten, auswählbar über seine Modbus-Adresse

Die Übersicht zeigt Online-Status, Meldungen, Buttons, Gesamtwerte sowie pro Kanal Ampere, Spannung, Leistung und Tagesmaximum.

## Installation über HACS

1. Repository als benutzerdefiniertes Repository in HACS hinzufügen.
2. Kategorie **Integration** wählen.
3. Integration installieren.
4. Home Assistant vollständig neu starten.
5. Unter **Einstellungen → Geräte & Dienste** die Integration **Fonrich DC Monitor** hinzufügen.

## Empfohlene Einstellungen

- HF2211 Protocol: `Modbus`
- Integration: `modbus_tcp_gateway`
- Baudrate: `9600` oder `19200`, aber identisch an HF2211 und allen Fonrich-Controllern
- Abfrage Basiswerte: 30 Sekunden
- Abfrage Meldungen: 15 Sekunden
- Pause zwischen Requests: 120 ms
- Pause zwischen Controllern: 250 ms
- Produktionsprofil
- Kanalspannung: aktiviert
- Max. Ampere heute: aktiviert
- Buttons: aktiviert

## Mehrere Controller und Gateways

- Pro Gateway können beliebig viele Controller mit eindeutigen Modbus-Adressen von 1 bis 247 eingetragen werden.
- Pro Controller sind 1 bis 24 Kanäle konfigurierbar.
- Mehrere Gateways werden durch mehrmaliges Hinzufügen der Integration eingerichtet.

## Update von älteren Versionen

Beim Update auf 0.7.0 werden ältere Einträge automatisch auf die neue kompakte Darstellung migriert. Die bisherigen Messsensoren behalten soweit möglich ihre eindeutigen IDs. Neue Sensoren für Kanalspannung, Tagesmaximum und Online-Status werden zusätzlich erstellt.
