# Changelog

## 1.0.0

- Fehler der alten Karte `custom:fonrich-modern-production-card` behoben
- Karten erkennen sowohl die stabilen Fonrich-Metadaten als auch bestehende Entity-IDs wie `sensor.kasten_v1_gesamtleistung`
- Bestehende YAML-Konfiguration mit `controllers`, `channel_count`, `max_current` und `show_buttons` bleibt kompatibel
- Online-Status wird direkt über `binary_sensor.kasten_vX_status_online` erkannt und nicht mehr aus Leistung oder Spannung geraten
- Gesamtleistung, Gesamtstrom und aktive Strings werden aus den tatsächlichen V1/V2/V3-Entities berechnet
- Alte Kartentypen als funktionsfähige Kompatibilitäts-Aliase wiederhergestellt
- Neue Karte **Fonrich Solar Monitor** mit visuellen Solarzellen pro Kanal
- Neue Karte **Fonrich Solar Energiefluss** für Strings, Kästen, DC-Gesamt und optionale Wechselrichter-, Haus-, Netz- und Batterie-Entities
- Visual Editor um Kastenreihenfolge, Kanalzahl, Stromskala und optionale Energiefluss-Entities erweitert
- Karten-Vorschläge für Fonrich-Entities nach Home-Assistant-2026.6-Schnittstelle ergänzt
- Doppelte Custom-Element-Registrierungen weiterhin verhindert
- Die stabile Ressource bleibt `/fonrich_dc_monitor/fonrich-dashboard.js`

## 0.9.0

- Alte und nicht gepflegte Kartentypen entfernt
- Sechs Karten im visuellen Karteneditor
- Schutz-, Alarm- und Testfunktionen ergänzt

## 1.0.1
- Karten-Picker-Registrierung repariert: `window.customCards` wird nicht mehr ersetzt, sondern in-place aktualisiert.
- Mehrstufige, duplikatfreie Nachregistrierung für den Home-Assistant-Karten-Picker.
- Karten-Preview im Picker deaktiviert, damit keine Vorschau ohne vollständige Konfiguration die Auswahl blockiert.
- Debug-Helfer `FonrichDashboardDebug.listPickerCards()` und `registerCardsInPicker()` ergänzt.
