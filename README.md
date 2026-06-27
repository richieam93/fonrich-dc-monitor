# Fonrich DC Monitor

Custom Integration für Home Assistant / HACS für Fonrich FR-DCMG-MMPS DC-Monitoring über einen HF2211 im **Modbus-TCP-Gateway-Modus**.

## Funktionen

- UI-Konfiguration über Geräte & Dienste
- Bis zu 3 Controller als eigene Home-Assistant-Geräte
- Automatische Sensoren für:
  - Spannung, Temperaturen, DI-Status
  - Total-/Kanalströme 1-8
  - Trip- und Alarmstatus
  - Lichtbogen-Alarmmaske und Historie
  - weitere Alarmmasken
  - Leistung und Energie-Wörter
  - optionale Lichtbogen-Intensitätsregister
- Binary-Sensoren für Kanalalarme
- Buttons für Alarm/Trip löschen, Lichtbogen-Historie löschen und Selbsttest
- Gestaffelte Abfrage über Kategorien, damit der RS485-Bus nicht auf einmal belastet wird

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
4. IP/Port und Controller-Adressen eintragen.

## Beispiel für deine Anlage

- Host: `192.168.0.41`
- Port: `4002`
- Controller 1: `240`
- Controller 2: `241`
- Controller 3: `242`
- Alarm: `10 s`
- Basiswerte: `30 s`
- Leistung: `60 s`
- Energie/History: `300 s`
- Lichtbogen-Intensität: optional

## Hinweis

Lichtbogen-/Trip-Alarme sind sicherheitsrelevant. Vor dem Quittieren immer DC-seitig prüfen lassen.
