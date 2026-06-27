# Fonrich DC Monitor

Version: `0.4.0`

Custom Integration für Home Assistant / HACS für Fonrich FR-DCMG-MMPS DC-Monitoring über einen HF2211 im **Modbus-TCP-Gateway-Modus**.

## Funktionen

- UI-Konfiguration über Geräte & Dienste
- Online-Prüfung beim Hinzufügen: Gateway per TCP und Controller per Modbus Register 260
- Bus-Baudrate als Option einstellbar, z. B. 9600 oder 19200
- Beliebig viele Controller pro Gateway als eigene Home-Assistant-Geräte
- Automatische Sensoren für Spannung, Temperatur, DI, Ströme, Alarm/Trip, Masken, Leistung, Energie, Historie und optional Lichtbogen-Intensität
- Binary-Sensoren für Kanalalarme
- Buttons für Alarm/Trip löschen, Lichtbogen-Historie löschen und Selbsttest
- Services für `refresh_now`, `clear_alarm_trip`, `clear_arc_history`, `arc_selftest`
- Gestaffelte Abfrage über Kategorien, damit der RS485-Bus nicht auf einmal belastet wird
- Erweiterte Optionen für Abfrageintervalle, Pausen zwischen Requests/Controllern und maximale Register pro Modbus-Abfrage
- Lovelace Karten als `www/*.js` für den Dashboard Visual Editor
- Lovelace-Ressource wird automatisch registriert, damit keine manuelle URL-Eingabe nötig ist
- Neue String-Karte mit Balkenanzeige für Kanal 1 bis 8
- Mehrere Gateways möglich: Integration einfach pro Gateway zusätzlich hinzufügen

## Empfohlene HF2211-Einstellung

- Protocol: `Modbus`
- Baudrate: `9600` oder `19200`, gleich wie alle Fonrich-Controller
- Databits: `8`
- Stopbits: `1`
- Parity: `NONE`
- TCP Server Port: z. B. `4002`
- maxAccept: `1`
- Timeout: `30`
- KeepAlive: `15`
- Software FlowCtrl: `Disable`

## Installation manuell

1. Ordner `custom_components/fonrich_dc_monitor` nach `/config/custom_components/fonrich_dc_monitor` kopieren.
2. Home Assistant neu starten.
3. Einstellungen → Geräte & Dienste → Integration hinzufügen → `Fonrich DC Monitor`.
4. IP/Port eintragen.
5. Controller-Adressen als Zahlen eintragen, z. B. `240,241,242` oder je Zeile eine Adresse. Keine Schieberegler.
6. Optional Controller-Namen eintragen, z. B. `V1 / Kasten 1,V2 / Kasten 2,V3 / Kasten 3`.

## Dashboard Karten

Die Integration bringt diese Datei mit:

```text
custom_components/fonrich_dc_monitor/www/fonrich-dc-monitor-cards.js
```

Ab Version `0.4.0` versucht die Integration die Lovelace-Ressource automatisch zu registrieren:

```text
/fonrich_dc_monitor/fonrich-dc-monitor-cards.js
```

Normaler Ablauf nach Installation oder Update:

1. Home Assistant neu starten.
2. Dashboard öffnen.
3. Karte hinzufügen.
4. Im Visual Editor nach `Fonrich` suchen.
5. Eine dieser Karten auswählen:
   - `Fonrich DC Übersicht`
   - `Fonrich Controller`
   - `Fonrich Alarme`
   - `Fonrich String-Ströme`

Falls Home Assistant die Ressource auf deiner Version nicht automatisch annimmt, im Log erscheint ein Hinweis. Dann kann sie weiterhin manuell unter Einstellungen → Dashboards → Ressourcen als `JavaScript-Modul` hinzugefügt werden.

## Beispiel für deine Anlage

- Host: `192.168.0.41`
- Port: `4002`
- Controller-Adressen: `240,241,242`
- Controller-Namen optional: `V1 / Kasten 1,V2 / Kasten 2,V3 / Kasten 3`
- Online-Prüfung: aktiv
- Alarm: `10 s`
- Basiswerte: `30 s`
- Leistung: `60 s`
- Energie/History: `300 s`
- Lichtbogen-Intensität: zuerst aus
- Pause zwischen Requests: `80 ms`
- Pause zwischen Controllern: `150 ms`
- Start-Staffelung: `5 s`
- Max. Register pro Abfrage: `20`

## Hinweis zur Baudrate

Die Integration verbindet sich per Modbus TCP mit dem HF2211. Die Baudrate wird physisch am HF2211 und an allen Fonrich-Controllern eingestellt. Das Feld in der Integration dokumentiert/validiert die erwartete Bus-Baudrate, ändert den HF2211 aber nicht automatisch. Wenn du auf 19200 wechselst, müssen V1, V2, V3 und der HF2211 gleich eingestellt sein.

## Sicherheit

Lichtbogen-/Trip-Alarme sind sicherheitsrelevant. Vor dem Quittieren immer DC-seitig prüfen lassen.


## Mehr als 3 Controller

Im Feld **Slave-Adressen als Zahlen** können beliebig viele Modbus-Adressen eingetragen werden:

```text
240,241,242,243,244
```

oder zeilenweise:

```text
240
241
242
243
```

Jede Adresse erzeugt automatisch ein eigenes Home-Assistant-Gerät mit Sensoren, Binary-Sensoren und optional Buttons.

## Mehrere Gateways

Für mehrere HF2211-Gateways die Integration einfach mehrfach hinzufügen. Jedes Gateway bekommt eine eigene IP/Port-Kombination, eigene Controller-Liste und eigene Abfrageintervalle.


## Neu in v0.5.0

- Beim Hinzufuegen wird nach der Controller-Liste eine eigene Seite fuer die Kanalanzahl pro Controller angezeigt.
- Die Kanalanzahl wird als normales Zahlenfeld eingetragen, kein Schieberegler.
- Danach folgt eine Seite fuer Kanalbeschreibungen. Pro Controller eine Zeile pro Kanal, z. B. `Dach Ost String 1`.
- Sensoren und Binary-Sensoren werden nur fuer die aktivierte Kanalanzahl erstellt.
- Kanalbeschreibungen werden als Entity-Namen-Anhang und als Attribute `channel` und `channel_description` gesetzt.
- Die Dashboard-Karten lesen die Kanalbeschreibungen automatisch und zeigen nur die konfigurierten Kanaele an.

Beispiel:

```text
Controller: 240,241,242
Kanalanzahl 240: 8
Kanalanzahl 241: 6
Kanalanzahl 242: 4

Kanalbeschreibungen 240:
Dach Ost String 1
Dach Ost String 2
Dach West String 1
...
```
