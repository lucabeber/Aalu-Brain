# Hardware inventory

Fill in from real parts. **TBD** = not yet known; nothing in the software assumes a value
for a TBD item beyond configurable defaults.

| Item | Known | TBD / to verify | Software impact |
|---|---|---|---|
| Raspberry Pi 5 16 GB | confirmed | case, cooling, DC/DC 12→5.1 V, RTC battery | `system` adapter reads temp/throttling |
| OS | Raspberry Pi OS 64-bit (Trixie) planned | exact image date, SD vs SSD boot | Python 3.13, CI tests 3.13 |
| GNSS receiver | NMEA at 115200 baud received, no fix yet | model, USB or UART, antenna, update rate, talker IDs | `adapters.gnss` = `serial`, port by-id path |
| Touchscreen drive | planned | size, resolution, orientation, touch controller (USB HID?) | `[ui.drive]` screen/size; canvas scales from 800×480 up |
| Touchscreen camper | planned | as above | `[ui.camper]` |
| SSD | proposed | USB vs PCIe HAT, capacity | `system.data_dir`; video retention (M3) |
| Rear / front cameras | planned | UVC? codec (H.264/MJPEG), resolution, night quality | video service (M3) |
| USB DAC / class-D amp | to select | model | audio output adapter (wpctl) |
| Speakers | 2 × 6.5" woofers + 2 tweeters | drivers, crossovers | none |
| Victron devices | system being defined | SmartShunt? MPPT model? Orion (engine charging)? MultiPlus? ports (VE.Direct vs VE.Bus) | `adapters.victron`: sources `house_battery`, `solar`, `dcdc` |
| House battery | 300 Ah LiFePO4, 10 % reserve (confirmed) | BMS model, charge profile, low-temperature charging limits | `[battery]` capacity_ah, reserve_soc_pct |
| Water tank senders | planned | type (resistive, capacitive), ranges | via MCU |
| I/O MCU | to choose (ESP32/STM32) | I/O count, CAN?, link protocol | `adapters.mcu`, frame protocol (M5) |
| ACC / reverse inputs | needed | isolation circuit, debounce | via MCU only, never GPIO direct |
| Power supervisor | needed before installation | hold-up time, shutdown signal | `POWER_FAIL` mode event |
