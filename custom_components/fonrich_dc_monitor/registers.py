from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class RegisterDescription:
    key: str
    name: str
    address: int
    category: str
    data_type: str = "uint16"
    scale: float = 1.0
    precision: int | None = None
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = None


@dataclass(frozen=True)
class BinaryDescription:
    key: str
    name: str
    source_key: str
    mask: int
    device_class: str = "problem"


@dataclass(frozen=True)
class ButtonDescription:
    key: str
    name: str
    address: int
    value: int = 1
    icon: str | None = None


BASE_REGISTERS: Final[list[RegisterDescription]] = [
    RegisterDescription("voltage", "Spannung", 260, "base", "uint16", 1, 0, "V", "voltage", "measurement"),
    RegisterDescription("temperature_1", "Temperatur 1", 261, "diagnostic", "int16", 0.1, 1, "°C", "temperature", "measurement"),
    RegisterDescription("temperature_2", "Temperatur 2", 262, "diagnostic", "int16", 0.1, 1, "°C", "temperature", "measurement"),
    RegisterDescription("di_status_raw", "DI Status Rohwert", 263, "alarm", "uint16"),
    RegisterDescription("online_hall_channels", "Online Hall Kanäle", 264, "diagnostic", "uint16", 1, 0, None, None, "measurement"),
    RegisterDescription("total_reverse_current", "Total Rückstrom", 265, "diagnostic", "int16", 0.01, 2, "A", "current", "measurement"),
    RegisterDescription("total_current", "Gesamtstrom", 266, "base", "int16", 0.01, 2, "A", "current", "measurement"),
    RegisterDescription("average_current", "Durchschnitt Strom", 267, "diagnostic", "int16", 0.001, 3, "A", "current", "measurement"),
]

CURRENT_REGISTERS: Final[list[RegisterDescription]] = [
    RegisterDescription(f"ch{ch}_current", f"Kanal {ch} Strom", 267 + ch, "base", "int16", 0.001, 3, "A", "current", "measurement")
    for ch in range(1, 25)
]

ALARM_REGISTERS: Final[list[RegisterDescription]] = [
    RegisterDescription("trip_status_1", "Trip Status 1", 298, "alarm", "uint16"),
    RegisterDescription("trip_status_2", "Trip Status 2", 299, "alarm", "uint16"),
    RegisterDescription("trip_status_3", "Trip Status 3", 300, "alarm", "uint16"),
    RegisterDescription("alarm_status_1", "Alarm Status 1", 301, "alarm", "uint16"),
    RegisterDescription("alarm_status_2", "Alarm Status 2", 302, "alarm", "uint16"),
    RegisterDescription("arc_alarm_ch_1_16", "Kanal 1-16 Lichtbogen Alarm Maske", 304, "alarm", "uint16"),
    RegisterDescription("arc_alarm_ch_17_24", "Kanal 17-24 Lichtbogen Alarm Maske", 305, "alarm", "uint16"),
    RegisterDescription("bus_arc_history_count", "Bus Lichtbogen Historie Anzahl", 306, "history", "uint16", 1, 0, None, None, "measurement"),
]

HISTORY_REGISTERS: Final[list[RegisterDescription]] = [
    RegisterDescription(f"ch{ch}_arc_history_count", f"Kanal {ch} Lichtbogen Historie Anzahl", 306 + ch, "history", "uint16", 1, 0, None, None, "measurement")
    for ch in range(1, 25)
]

# The manual uses one 16-bit mask for channels 1-16 and the following register
# for channels 17-24. Keep explicit keys so the readable alarm sensor can map all
# 24 channels reliably.
_MASK_PAIRS = [
    ("reverse_current_alarm", "Rückstrom Alarm", 331),
    ("no_current_alarm", "Kein Strom Alarm", 333),
    ("undercurrent_alarm", "Unterstrom Alarm", 335),
    ("overcurrent_alarm", "Überstrom Alarm", 337),
    ("current_low_alarm", "Strom zu niedrig Alarm", 339),
    ("current_high_alarm", "Strom zu hoch Alarm", 341),
    ("arc_selfcheck_fail", "Lichtbogen Selbsttest Fehler", 343),
]
MASK_REGISTERS: Final[list[RegisterDescription]] = []
for key, title, address in _MASK_PAIRS:
    MASK_REGISTERS.extend(
        [
            RegisterDescription(f"{key}_ch_1_16", f"Kanal 1-16 {title} Maske", address, "alarm", "uint16"),
            RegisterDescription(f"{key}_ch_17_24", f"Kanal 17-24 {title} Maske", address + 1, "alarm", "uint16"),
        ]
    )


SAFETY_REGISTERS: Final[list[RegisterDescription]] = [
    RegisterDescription(
        "remote_trip_alarm_enable_config",
        "Remote-Trip Alarmfreigabe Konfiguration",
        2849,
        "safety",
        "uint16",
    ),
    RegisterDescription(
        "remote_trip_action_enable_config",
        "Remote-Trip Auslösefreigabe Konfiguration",
        2852,
        "safety",
        "uint16",
    ),
]

POWER_REGISTERS: Final[list[RegisterDescription]] = [
    RegisterDescription("total_power_direct", "Gesamtleistung", 512, "power", "uint16", 100, 0, "W", "power", "measurement"),
    RegisterDescription("average_power_direct", "Durchschnitt Leistung", 513, "power", "uint16", 1, 0, "W", "power", "measurement"),
] + [
    RegisterDescription(f"ch{ch}_power_direct", f"Kanal {ch} Leistung", 513 + ch, "power", "uint16", 1, 0, "W", "power", "measurement")
    for ch in range(1, 25)
]

ENERGY_REGISTERS: Final[list[RegisterDescription]] = [
    RegisterDescription("total_energy_high_word", "Total Energie High Word", 538, "energy", "uint16", 1, 0, "Wh", None, "measurement"),
    RegisterDescription("total_energy_low_word", "Total Energie Low Word", 539, "energy", "uint16", 1, 0, "Wh", None, "measurement"),
]
for ch in range(1, 25):
    ENERGY_REGISTERS.extend(
        [
            RegisterDescription(f"ch{ch}_energy_high_word", f"Kanal {ch} Energie High Word", 538 + ch * 2, "energy", "uint16", 1, 0, "Wh", None, "measurement"),
            RegisterDescription(f"ch{ch}_energy_low_word", f"Kanal {ch} Energie Low Word", 539 + ch * 2, "energy", "uint16", 1, 0, "Wh", None, "measurement"),
        ]
    )

ARC_INTENSITY_REGISTERS: Final[list[RegisterDescription]] = []
for base, suffix, title in [
    (592, "arc_intensity", "Lichtbogen Intensität"),
    (616, "arc_intensity_max", "Lichtbogen Intensität Max"),
    (640, "arc_intensity_10min", "Lichtbogen Intensität 10 min"),
]:
    for ch in range(1, 25):
        ARC_INTENSITY_REGISTERS.append(
            RegisterDescription(f"ch{ch}_{suffix}", f"Kanal {ch} {title}", base + ch - 1, "arc_intensity", "int16", 1, 0, None, None, "measurement")
        )

ALL_SENSOR_REGISTERS: Final[list[RegisterDescription]] = (
    BASE_REGISTERS
    + CURRENT_REGISTERS
    + ALARM_REGISTERS
    + HISTORY_REGISTERS
    + MASK_REGISTERS
    + SAFETY_REGISTERS
    + POWER_REGISTERS
    + ENERGY_REGISTERS
    + ARC_INTENSITY_REGISTERS
)

BINARY_DESCRIPTIONS: Final[list[BinaryDescription]] = [
    BinaryDescription("summary_alarm", "Sammelalarm", "alarm_status_1", 0xFFFF),
    BinaryDescription("summary_trip", "Sammeltrip", "trip_status_1", 0xFFFF),
    BinaryDescription("bus_arc_alarm", "Bus Lichtbogen Alarm", "alarm_status_1", 1),
    BinaryDescription("channel_arc_summary_alarm", "Kanal Lichtbogen Sammelalarm", "alarm_status_1", 2),
    BinaryDescription("undervoltage_alarm", "Unterspannung Alarm", "alarm_status_1", 4),
    BinaryDescription("overvoltage_alarm", "Überspannung Alarm", "alarm_status_1", 8),
    BinaryDescription("temperature_1_high_alarm", "Temperatur 1 hoch Alarm", "alarm_status_1", 16),
    BinaryDescription("temperature_2_high_alarm", "Temperatur 2 hoch Alarm", "alarm_status_1", 32),
    BinaryDescription("channel_reverse_current_summary_alarm", "Kanal Rückstrom Sammelalarm", "alarm_status_1", 64),
    BinaryDescription("total_reverse_current_high_alarm", "Total Rückstrom hoch Alarm", "alarm_status_1", 128),
    BinaryDescription("total_current_low_alarm", "Total Strom niedrig Alarm", "alarm_status_1", 256),
    BinaryDescription("total_current_high_alarm", "Total Strom hoch Alarm", "alarm_status_1", 512),
    BinaryDescription("channel_no_current_summary_alarm", "Kanal Kein Strom Sammelalarm", "alarm_status_1", 1024),
    BinaryDescription("channel_undercurrent_summary_alarm", "Kanal Unterstrom Sammelalarm", "alarm_status_1", 2048),
    BinaryDescription("channel_overcurrent_summary_alarm", "Kanal Überstrom Sammelalarm", "alarm_status_1", 4096),
    BinaryDescription("channel_current_low_summary_alarm", "Kanal Strom zu niedrig Sammelalarm", "alarm_status_1", 8192),
    BinaryDescription("channel_current_high_summary_alarm", "Kanal Strom zu hoch Sammelalarm", "alarm_status_1", 16384),
]

_BINARY_MASK_GROUPS = [
    ("arc_alarm", "Lichtbogen Alarm", "arc_alarm_ch_1_16", "arc_alarm_ch_17_24"),
    ("reverse_current_alarm", "Rückstrom Alarm", "reverse_current_alarm_ch_1_16", "reverse_current_alarm_ch_17_24"),
    ("no_current_alarm", "Kein Strom Alarm", "no_current_alarm_ch_1_16", "no_current_alarm_ch_17_24"),
    ("undercurrent_alarm", "Unterstrom Alarm", "undercurrent_alarm_ch_1_16", "undercurrent_alarm_ch_17_24"),
    ("overcurrent_alarm", "Überstrom Alarm", "overcurrent_alarm_ch_1_16", "overcurrent_alarm_ch_17_24"),
    ("current_low_alarm", "Strom zu niedrig Alarm", "current_low_alarm_ch_1_16", "current_low_alarm_ch_17_24"),
    ("current_high_alarm", "Strom zu hoch Alarm", "current_high_alarm_ch_1_16", "current_high_alarm_ch_17_24"),
    ("arc_selfcheck_fail", "Lichtbogen Selbsttest Fehler", "arc_selfcheck_fail_ch_1_16", "arc_selfcheck_fail_ch_17_24"),
]
for ch in range(1, 25):
    source_offset = ch - 1 if ch <= 16 else ch - 17
    bit = 1 << source_offset
    for key, title, source_1_16, source_17_24 in _BINARY_MASK_GROUPS:
        source = source_1_16 if ch <= 16 else source_17_24
        BINARY_DESCRIPTIONS.append(BinaryDescription(f"ch{ch}_{key}", f"Kanal {ch} {title}", source, bit))

BUTTONS: Final[list[ButtonDescription]] = [
    ButtonDescription("clear_alarm_trip_status", "Alarm und Trip zurücksetzen", 3074, 1, "mdi:alarm-light-off-outline"),
    ButtonDescription("clear_arc_history", "Lichtbogen-Historie löschen", 3073, 1, "mdi:history"),
    ButtonDescription("arc_selftest", "Lichtbogen-Selbsttest starten", 3077, 1, "mdi:flash-alert-outline"),
]
