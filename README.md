# Fonrich DC Monitor für Home Assistant

Custom Integration für Fonrich FR-DCMG-MMPS über einen TCP/RS485-Gateway wie den HF2211.

## Version 1.0.1

Diese Version repariert zusätzlich die Registrierung im Home-Assistant-Karten-Picker und behebt weiterhin die fehlerhafte Nullanzeige der bisherigen Karte `custom:fonrich-modern-production-card` und ergänzt moderne Solar-Monitor- und Energieflusskarten.

Die Karten erkennen jetzt zwei Varianten:

1. neue stabile Fonrich-Attribute wie `fonrich_role` und `controller_slave`
2. bestehende Entity-IDs wie `sensor.kasten_v1_gesamtleistung`, `sensor.kasten_v2_kanal_01_ampere` und `binary_sensor.kasten_v3_status_online`

Damit funktionieren auch bestehende Installationen und ältere Entity-Registrierungen.


### Karten-Picker-Fix in 1.0.1

Die Ressource ersetzt `window.customCards` nicht mehr durch ein neues Array. Stattdessen wird die bestehende Registrierung direkt aktualisiert, damit der geöffnete Home-Assistant-Karten-Picker die Fonrich-Karten zuverlässig sieht. Die Registrierung wird kurz nach dem Laden nochmals duplikatfrei geprüft.

## Entitäten pro Kasten

Jeder konfigurierte Controller erscheint als eigenes Home-Assistant-Gerät, zum Beispiel **Kasten V1**, **Kasten V2** und **Kasten V3**.

Pro Kasten stehen bereit:

- Status Online/Offline
- eine lesbare Meldungs-Entity
- Spannung
- Gesamtstrom
- Gesamtleistung
- DI1 bis DI4
- Schutz-Teststatus
- Alarm und Trip zurücksetzen
- Lichtbogen-Historie löschen
- Lichtbogen-Selbsttest starten
- optional abgesicherter Hauptschalter-Test
- Blitzschutz-Meldetest nur für Home Assistant

## Entitäten pro Kanal

Pro aktivem Kanal werden erstellt:

- Ampere aktuell
- Spannung in Volt
- Leistung in Watt
- maximale Ampere seit lokalem Tagesbeginn
- frei einstellbare Kanalbeschreibung

Der FR-DCMG-MMPS liefert eine gemeinsame Busspannung pro Kasten. Deshalb zeigt der Kanal-Spannungssensor die Spannung des zugehörigen Kastens.

## Gemeinsamer Meldungssensor

Der Sensor **Fonrich Meldungen** fasst alle aktiven Meldungen aller Kästen zusammen. Beispiele:

- `Lichtbogen bei Kasten V1, Kanal 02`
- `Lichtbogen bei Kasten V2, Kanal 05 (Terrasse Süd)`
- `Unterspannung bei Kasten V1`
- `Remote-Hauptschalter-Auslösung aktiv bei Kasten V2`
- `Kasten V3 offline`

Die vollständige Liste steht zusätzlich im Attribut `active_messages`.

## Dashboard-Karten

Die stabile Ressource lautet:

`/fonrich_dc_monitor/fonrich-dashboard.js`

Im visuellen Karteneditor werden angeboten:

1. **Fonrich Gesamtübersicht**
2. **Fonrich Kasten und Kanäle**
3. **Fonrich Modern Produktion**
4. **Fonrich Solar Monitor**
5. **Fonrich Solar Energiefluss**
6. **Fonrich Schutz, Alarm und Tests**
7. **Fonrich Kanaltabelle**
8. **Fonrich Kanalvergleich**
9. **Fonrich Busdiagnose**

### Verbesserte bestehende Modern-Karte

Diese bestehende Konfiguration bleibt gültig:

```yaml
 type: custom:fonrich-modern-production-card
 title: Fonrich Modern
 controllers:
   - V1 / Kasten 1
   - V2 / Kasten 2
   - V3 / Kasten 3
 max_current: 15
 channel_count: 8
 show_buttons: true
```

Die Bezeichnungen unter `controllers` werden anhand der V-Nummer den tatsächlichen Geräten **Kasten V1**, **Kasten V2** und **Kasten V3** zugeordnet.

### Solar Monitor

```yaml
 type: custom:fonrich-solar-monitor-card
 title: Solarzellen Übersicht
 controllers:
   - V1 / Kasten 1
   - V2 / Kasten 2
   - V3 / Kasten 3
 channel_count: 8
 max_current: 15
 show_inactive: true
```

Die Karte zeigt jeden String als Solarzelle mit:

- Leistung
- Ampere
- Spannung
- Tagesmaximum
- Aktiv-/Inaktivzustand

### Solar Energiefluss

Minimal:

```yaml
 type: custom:fonrich-solar-flow-card
 title: Solar Energiefluss
 controllers:
   - V1 / Kasten 1
   - V2 / Kasten 2
   - V3 / Kasten 3
 channel_count: 8
 show_panels: true
```

Optional können im visuellen Editor oder per YAML zusätzliche Home-Assistant-Entities eingetragen werden:

```yaml
 inverter_power_entity: sensor.inverter_gesamt_pv
 house_power_entity: sensor.power_meter_active_power_1
 grid_power_entity: sensor.energie_hv_p
 battery_power_entity: sensor.battery_charge_discharge_power_2
 battery_soc_entity: sensor.battery_state_of_capacity_2
```

Ohne zusätzliche Entities zeigt die Karte bereits den vollständigen Fonrich-DC-Fluss von den Solarstrings über V1/V2/V3 bis zur DC-Gesamtleistung.

## Kompatibilität alter Kartentypen

Alte Typen wie `custom:fonrich-production-overview-card`, `custom:fonrich-strings-card`, `custom:fonrich-energy-card` und `custom:fonrich-alarms-card` werden als Aliase auf die neuen funktionsfähigen Karten abgebildet. Im Karten-Picker werden nur die aktuellen Namen angezeigt.

## Hauptschalter-Test pro Kasten

Die Sicherheits-Testbuttons sind standardmässig deaktiviert und müssen unter **Integration → Konfigurieren → Abfrage und Funktionen** ausdrücklich aktiviert werden.

Der Button **Hauptschalter-Schutz auslösen (Test)** kann den real angeschlossenen Shunt-Auslöser betätigen. Deshalb gelten mehrere Sperren:

- Funktion muss ausdrücklich aktiviert sein.
- Der Kasten muss online sein.
- Zuerst muss die zeitlich begrenzte Freigabe gedrückt werden.
- Die Dashboard-Karte verlangt zusätzlich die Eingabe `AUSLOESEN`.
- Vor dem Schreiben prüft die Integration Register 2849 Bit 14 und Register 2852 Bit 14.
- Die Integration verändert diese Schutzkonfiguration niemals automatisch.

## Blitzschutz-Test

**Blitzschutz-Meldetest (nur HA)** erzeugt ausschliesslich eine markierte Home-Assistant-Testmeldung. Die Blitzschutz-Hardware wird nicht elektrisch ausgelöst.

## Empfohlene Grundeinstellungen

- HF2211 Protocol: `Modbus`
- Integrationsmodus: `modbus_tcp_gateway`
- Baudrate auf HF2211 und allen Controllern identisch
- Alarmabfrage: 10 bis 15 Sekunden
- Spannung/Ampere: 20 bis 30 Sekunden
- Leistung: 30 bis 60 Sekunden
- Pause zwischen Requests: 100 bis 200 ms
- Pause zwischen Controllern: 200 bis 400 ms
- Offline nach Fehlern: 2 oder 3

## RS485

Mehrere Controller am gleichen Bus sind vorgesehen. Die Verdrahtung sollte als Linie ausgeführt werden:

`HF2211 → Kasten V1 → Kasten V2 → Kasten V3`

A auf A, B auf B und nach Möglichkeit gemeinsames Bezugspotential. Keine langen Sternabzweige. Abschlusswiderstände nur an den beiden Busenden.

## Installation über HACS

Repository als benutzerdefiniertes HACS-Repository vom Typ **Integration** hinzufügen:

`https://github.com/richieam93/fonrich-dc-monitor`

Danach Home Assistant neu starten und unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** nach **Fonrich DC Monitor** suchen.

## Nach einem Kartenupdate

1. Home Assistant vollständig neu starten.
2. Unter **Einstellungen → Dashboards → Ressourcen** nur `/fonrich_dc_monitor/fonrich-dashboard.js` behalten.
3. Alte Ressourcen wie `/fonrich_dc_monitor/fonrich-cards.js` entfernen, falls Home Assistant sie nicht automatisch bereinigt hat.
4. Browser mit `Ctrl + F5` vollständig neu laden.
5. Bereits geöffnete Dashboard-Editoren schliessen und erneut öffnen.

## Sicherheit

Lichtbogen-, Trip- und Hauptschalterfunktionen sind sicherheitsrelevant. Elektrische Auslösetests dürfen nur bei sicherem Anlagenzustand und durch entsprechend qualifizierte Personen durchgeführt werden.
