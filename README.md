# Fonrich DC Monitor

Version: `0.6.1`

Custom Integration für Home Assistant / HACS für Fonrich FR-DCMG-MMPS DC-Monitoring über einen HF2211. Unterstützt **HF2211 Protocol = Modbus** als Modbus-TCP-Gateway und optional **Protocol = NONE/Transparent** als RTU-over-TCP.

## Neu in v0.6.1

- Neues **Sensor-Profil** in Einrichtung und Optionen:
  - `production`: nur die wichtigen Produktionswerte
  - `standard`: Produktionswerte plus einfache Alarmwerte
  - `diagnostic`: alle Diagnose-/Alarm-/Historie-/Arc-Werte bei Bedarf
- Standard ist jetzt bewusst schlank: **Volt, Ampere, Watt und optional Energie**.
- Alarm-Binary-Sensoren, Alarmmasken, Historie, Arc-Intensität und Buttons sind standardmässig aus.
- Einheitlichere Kanalnamen:
  - `Kanal 01 - Dach Ost String 1 Strom`
  - `Kanal 01 - Dach Ost String 1 Leistung`
- Dashboard-Karten wurden auf Produktion angepasst:
  - `Fonrich Produktion`
  - `Fonrich Controller Produktion`
  - `Fonrich String-Leistung`
  - `Fonrich Energie`
  - `Fonrich Alarme` optional

## Funktionen

- UI-Konfiguration über Geräte & Dienste
- Online-Prüfung beim Hinzufügen: Gateway per TCP und Controller per Modbus Register 260
- HF2211 Protocol/UART-Modus einstellbar: `Modbus TCP Gateway` oder `RTU over TCP / Transparent`
- Bus-Baudrate als Option einstellbar, z. B. 9600 oder 19200
- Beliebig viele Controller pro Gateway als eigene Home-Assistant-Geräte
- Pro Controller 1 bis 24 Kanäle als Zahlenfeld
- Kanalbeschreibungen pro Kanal, z. B. `Dach Ost String 1`
- Produktionssensoren für Spannung, Kanalstrom, Kanalleistung, Totalstrom, Totalleistung und optional Energie
- Erweiterte Diagnose-/Alarmwerte optional zuschaltbar
- Gestaffelte Abfrage über Kategorien, damit der RS485-Bus nicht auf einmal belastet wird
- Mehrere HF2211-Gateways möglich: Integration pro Gateway zusätzlich hinzufügen
- Lovelace-Karten als `www/*.js` für den Dashboard Visual Editor

## Empfohlenes Sensor-Profil

Für normale PV-/String-Überwachung:

```text
Sensor-Profil: production
Watt pro Kanal: ein
Energie pro Kanal: optional ein
Alarm-Binary-Sensoren: aus
Historie: aus
Alarmmasken: aus
Lichtbogen-Intensität: aus
Buttons: aus
```

Damit werden nicht mehr hunderte unnötige Alarm-Entities erzeugt.

## Empfohlene HF2211-Einstellung

Für die bekannte Anlage empfohlen:

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
5. Controller-Adressen als Zahlen eintragen, z. B. `240,241,242` oder je Zeile eine Adresse.
6. Kanalanzahl pro Controller eintragen, z. B. `8` oder bis `24`.
7. Kanalbeschreibungen eintragen.
8. Sensor-Profil und Abfrageintervalle wählen.

## Dashboard Karten

Die Integration bringt diese Datei mit:

```text
custom_components/fonrich_dc_monitor/www/fonrich-dc-monitor-cards.js
```

Die Integration versucht die Lovelace-Ressource automatisch zu registrieren:

```text
/fonrich_dc_monitor/fonrich-dc-monitor-cards.js
```

Normaler Ablauf nach Installation oder Update:

1. Home Assistant neu starten.
2. Dashboard öffnen.
3. Karte hinzufügen.
4. Im Visual Editor nach `Fonrich` suchen.
5. Eine dieser Karten auswählen:
   - `Fonrich Produktion`
   - `Fonrich Controller Produktion`
   - `Fonrich String-Leistung`
   - `Fonrich Energie`
   - `Fonrich Alarme`

Falls Home Assistant die Ressource auf deiner Version nicht automatisch annimmt, kann sie weiterhin manuell unter Einstellungen → Dashboards → Ressourcen als `JavaScript-Modul` hinzugefügt werden.

## Beispiel

```text
Host: 192.168.0.41
Port: 4002
Controller-Adressen: 240,241,242
Controller-Namen: V1 / Kasten 1,V2 / Kasten 2,V3 / Kasten 3
Kanalanzahl: 8 je Controller
Sensor-Profil: production
Spannung/Ampere: 30 s
Watt: 60 s
Energie: 300 s
Pause zwischen Requests: 80 ms
Pause zwischen Controllern: 150 ms
Max. Register pro Abfrage: 20
```

## Hinweis zu Protocol und Baudrate

Wenn der HF2211 auf `Protocol = Modbus` steht, muss in der Integration `Modbus TCP Gateway` gewählt werden. Wenn der HF2211 auf `Protocol = NONE/Transparent` steht, muss in der Integration `RTU over TCP / Transparent` gewählt werden.

Die Baudrate wird physisch am HF2211 und an allen Fonrich-Controllern eingestellt. Das Feld in der Integration dokumentiert/validiert die erwartete Bus-Baudrate, ändert den HF2211 aber nicht automatisch. Wenn du auf 19200 wechselst, müssen alle Fonrich-Controller und der HF2211 gleich eingestellt sein.

## Sicherheit

Lichtbogen-/Trip-Alarme sind sicherheitsrelevant. Vor dem Quittieren immer DC-seitig prüfen lassen.


## 0.6.1

Fix: SensorEntityDescription compatibility for newer Home Assistant versions.
