# Big Sky Laser BSS P/S RS-485 Command Reference

> Manual transcription derived from PDF pages 79-88 of the Big Sky Laser service manual (the embedded *Trouble Shooting Guide, BSS P/S*, pages 10-19 of 19).
>
> The command names, meanings, ranges, examples, and reply templates below were checked directly against the page images. Printed manual content is kept separate from behavior observed on the tested controller; several exact wire details remain unresolved. These pages do **not** specify baud rate, parity, stop bits, or other serial-port settings.

## 1. Protocol and framing

### 1.1 Command terminator

Every command in the source is followed by `CRLF`:

```text
<command>\r\n
```

In the tables below, this is written as `<CRLF>`.

### 1.2 Device addressing

For a specific device, prefix the command with `$xxx`, where `xxx` is the three-digit serial number used as the destination address.

```text
$001S<CRLF>
```

This places device `001` in standby mode.

> **Hardware verified (2026-08-07, SN 062):** the addressed form is the manual's
> `$xxx` with a three-digit zero-padded serial number. `$062SN` is answered,
> while `062SN`, `62SN`, `$62SN`, and `>062SN` all return no reply. The library
> now emits `$xxx`; the earlier unprefixed decimal form (`62SN`) elicited no
> response and was incorrect. Broadcast `>` remains answered.

To broadcast to every BSS device on the RS-485 chain, prefix the command with `>`:

```text
>S<CRLF>
```

Broadcast replies can collide when more than one BSS device responds simultaneously. The manual directs the user to disable replies with `ECH0` when using broadcast mode.

### 1.3 Reply framing

The manual describes a normal reply as:

```text
<CRLF><15-character answer>
```

It displays literal ASCII spaces as `°` for visibility. This reference preserves that notation:

- `°` = one ASCII space (`0x20`)
- `-`, `#`, `a`, `b`, etc. = variable field or status character as printed
- Numeric counters are normally zero-padded or fixed-width

The reply templates below are transcribed **as printed**. No spaces were moved or inserted merely to force a 15-character width. Several printed templates conflict with the manual's general 15-character statement; those inconsistencies are summarized in [Section 1.5](#15-printed-reply-length-inconsistencies).

### 1.4 Reply/echo control

The manual calls this setting **echo mode**, but its description indicates that it controls whether the unit sends responses:

- `ECH1<CRLF>`: replies enabled; standard mode
- `ECH0<CRLF>`: replies disabled; commands are still executed
- `ECH<CRLF>`: reads the current mode; no response is available when replies are disabled

### 1.5 Printed reply-length inconsistencies

The manual states that every answer contains 15 characters after the initial `CRLF`, but the following templates appear with a different printed length. This may reflect typographical omissions/extras in the manual rather than the device firmware.

| Printed reply template | Printed length | PDF page | Comment |
|---|---:|---:|---|
| `shutt.°at°run°-` / `shutt.°at°run°1` | 14 | 80 | Read template and programming example; a trailing pad may have been omitted |
| `I/O°connector` | 13 | 83 | Flashlamp-activation interlock message |
| `tp°CG°<°##°d` | 12 | 83 | Celsius low-temperature interlock template |
| `tp°CG°<°###°F` | 13 | 83, 85 | Fahrenheit low-temperature interlock template |
| `fire°auto°°°qs°°` / `fire°auto°°°qse°` | 16 | 84, 85 | Printed for `PQ` and `OQ` with internal lamp trigger |
| `fire°ext°°°°qs°°` / `fire°ext°°°°qse°` | 16 | 84, 85 | Printed for `PQ` and `OQ` with external lamp trigger |
| `IF°00°00°00°00` | 14 | 86 | All flashlamp interlocks OK |
| `QS°wait°:°°---` / `QS°wait°:°°100` | 14 | 87, 88 | A trailing pad may have been omitted |

For software, do not discard meaningful characters to enforce 15 bytes. Confirm actual firmware behavior before relying on fixed-width parsing for the anomalous templates.

---

<!-- PDF page 79 | Trouble Shooting Guide page 10 of 19 -->

## 2. Configuration and general status

### 2.1 Read commands

| Command | Purpose | Expected answer field | PDF page |
|---|---|---|---:|
| `X<CRLF>` | Read software revision | `SPECTRA-SC°-.--` | 79 |
| `DAT<CRLF>` | Read software revision date (`dd/mm/yy`) | `--/--/--°°°°°°°` | 79 |
| `CG<CRLF>` | Read cooling-group temperature in degrees Celsius | `temp.°CG°--°d°°` | 79 |
| `CGF<CRLF>` | Read cooling-group temperature in degrees Fahrenheit | `temp.°CG°---°F°` | 79 |
| `T<CRLF>` | Read operating-time counter; `hhhh` = hours, `mm` = minutes | `ct°time°hhhh:mm` | 79 |
| `R<CRLF>` | Read shutter state | `shutter°closed°` or `shutter°opened°` | 79 |
| `ROF<CRLF>` | Read whether the shutter is opened or closed when running | `shutt.°at°run°-` | 80 |
| `P<CRLF>` | Read cooling-group pump state | `CG°pump°°°°°°°-` | 80 |
| `ECH<CRLF>` | Read reply/echo mode | `echo°on°°°°°°°°`; no reply if disabled | 80 |
| `WOR<CRLF>` | Read compact laser operating status | `I°a°F°b°S°c°Q°d` | 80 |
| `<CRLF>` | Read lamp and Q-switch operating mode by sending an otherwise empty command line | One of the operating-state replies documented under flashlamp/Q-switch activation | 81 |

### 2.2 Programming commands

| Command form | Purpose | Argument / shown example | Expected answer field | PDF page |
|---|---|---|---|---:|
| `SAV1<CRLF>` | Save current configuration | Valid range shown: `1-1` | `Save°config.°°1` | 80 |
| `R<n><CRLF>` | Set shutter opened/closed | `n = 0-1`; example `R1` | Example: `shutter°opened°` | 80 |
| `ROF<n><CRLF>` | Set shutter behavior at run | `n = 0-1`; `1` = open shutter at run | Example: `shutt.°at°run°1` | 80 |
| `P<n><CRLF>` | Control cooling-group pump | `n = 0-1`; `0` = stop pump | Example: `CG°pump°°°°°°°1` | 80 |
| `SUC<CRLF>` | Save the current user counter | No argument shown | `user°ct°saved°°` | 80 |
| `ECH<n><CRLF>` | Enable/disable replies | `0` = off, `1` = on | `ECH1`: `echo°on°°°°°°°°`; `ECH0`: no reply | 81 |

### 2.3 `WOR` status decoding

The `WOR` reply is:

```text
I a F b S c Q d
```

The letters `I`, `F`, `S`, and `Q` are literal labels; `a-d` are status digits.

| Field | Meaning | Code | Decoded state |
|---|---|---:|---|
| `a` | Interlock | `0` | OK |
| `a` | Interlock | `1` | Fail |
| `b` | Flashlamp, internal sync | `0` | Stop |
| `b` | Flashlamp, internal sync | `1` | Single |
| `b` | Flashlamp, internal sync | `2` | Start |
| `b` | Flashlamp, external sync | `4` | Stop |
| `b` | Flashlamp, external sync | `5` | Single |
| `b` | Flashlamp, external sync | `6` | Start |
| `c` | Simmer | `0` | Off |
| `c` | Simmer | `1` | On |
| `d` | Q-switch, internal sync | `0` | Stop |
| `d` | Q-switch, internal sync | `1` | Single |
| `d` | Q-switch, internal sync | `2` | Start |
| `d` | Q-switch, external sync | `4` | Stop |
| `d` | Q-switch, external sync | `5` | Single |
| `d` | Q-switch, external sync | `6` | Start |

Code `3` is not documented on these pages.

> **Hardware verified (2026-08-07):** the tested controller prints the manual's
> `I/F/S/Q` labels (e.g. `I 0 F 4 S 0 Q 4`), not the historical simulator's
> `I/L/M/Q`. The parser still validates only structure and numeric domains (it
> requires the outer `I`/`Q` labels and alphabetic middle labels) so it stays
> compatible with both label sets across firmware revisions.

---

<!-- PDF pages 81-83 | Trouble Shooting Guide pages 12-14 of 19 -->

## 3. Flashlamp commands

### 3.1 Read flashlamp parameters

| Command | Purpose | Expected answer field | PDF page |
|---|---|---|---:|
| `V<CRLF>` | Read flashlamp voltage | `voltage°°----°V` | 81 |
| `VA<CRLF>` | Read sampled capacitor voltage; sample-and-hold after charge completes | `voltage°ac----V` | 81 |
| `VI<CRLF>` | Read instantaneous capacitor voltage | `voltage°it----V` | 81 |
| `ENE<CRLF>` | Read flashlamp energy | `energy°°°°--.-J` | 81 |
| `CAP<CRLF>` | Read capacitor value | Example: `capacity°29.3uF` | 81 |
| `LPM<CRLF>` | Read flashlamp trigger mode | `LP°synch°:°°-°°` | 81 |
| `F<CRLF>` | Read preset repetition rate | `freq.°°--.--°Hz` | 81 |
| `C<CRLF>` | Read lamp shot counter, 9 digits | `ct°LP°---------` | 81 |
| `UC<CRLF>` | Read lamp user's shot counter, 9 digits | `cu°LP°---------` | 81 |
| `VMO<CRLF>` | Read average lamp voltage | `voltage°m----°V` | 87 |
| `D<CRLF>` | Read idle-fire delay/time | `dis°charg°-.--S` | 87 |
| `E<CRLF>` | Read enable-fire delay/time | `ena°charg°-.--S` | 87 |
| `SN<CRLF>` | Read serial number | `S/Number°°°°---` | 87 |

> **Hardware verified (2026-08-07):** the tested controller replies with
> lowercase `s/number` and a three-digit zero-padded value (`s/number    062`).
> Software still accepts both capitalization variants for firmware portability.

### 3.2 Program flashlamp parameters

| Command form | Purpose | Range / shown example | Expected answer field | PDF page |
|---|---|---|---|---:|
| `LPM<n><CRLF>` | Set flashlamp trigger mode | `0` = internal trigger; `1` = external trigger. Example: `LPM0` | `LP°synch°:°°0°°` | 81 |
| `V<volts><CRLF>` | Set flashlamp voltage | `500-1800 V` and factory limits `Vmin < V < Vmax`. Example: `V1150` | `voltage°°1150°V` | 81 |
| `F<code><CRLF>` | Set repetition rate | Valid range shown: `1-9999`. Example: `F4000` produces `40.00 Hz` | `freq.°°40.00°Hz` | 82 |
| `UC0<CRLF>` | Reset lamp user's shot counter | No other value shown | `cu°LP°000000000` | 82 |
| `ENE<value><CRLF>` | Set flashlamp energy | `7-23 J`. Example: `ENE212` sets `21.2 J` | `energy°°°°21.2J` | 82 |
| `CAP<value><CRLF>` | Set capacitor value | `27-33 uF`. Example: `CAP293` sets `29.3 uF` | `capacity°29.3uF` | 82 |
| `D<n><CRLF>` | Set idle-fire interval | Example `D10` is described as `1.0 s`; `D0` = continue operating | Printed examples: `dis°charg°03.5S`, `dis°charg°00.0S` | 87 |
| `E<n><CRLF>` | Set enable-fire interval | Example `E25` is described as `2.5 s`; `E0` = continue operating | Printed examples: `ena°charg°03.5S`, `ena°charg°00.0S` | 87 |

Changing `ENE` or `CAP` affects the flashlamp voltage. The manual says the resulting voltage depends on energy, capacitor value, and average-voltage values.

> **Source inconsistency:** the printed `D10` description says `1.0 s`, but its shown response is `03.5S`. Likewise, `E25` is described as `2.5 s`, but its shown response is also `03.5S`. These examples are preserved as printed rather than corrected.

### 3.3 Flashlamp activation and deactivation

#### `A<CRLF>` - automatic lamp firing

Activates automatic flashlamp firing in the preselected lamp/Q-switch trigger modes.

| Lamp trigger | Q-switch programmed trigger | Reply as printed |
|---|---|---|
| Internal | Internal | `fire°auto°°°°°°` |
| Internal | External | `fire°auto°°°°e°` |
| External | Internal | `fire°ext°°°°°°°` |
| External | External | `fire°ext°°°°°e°` |

#### `S<CRLF>` - stop automatic lamp firing

Stops automatic internal or external lamp firing.

| Q-switch programmed trigger | Reply as printed |
|---|---|
| Internal | `standby°°°°°°°°` |
| External | `standby°°°°°°e°` |

#### `M<CRLF>` - simmer

Places the lamp in simmer mode in the preselected operating mode.

| Q-switch programmed trigger | Reply as printed |
|---|---|
| Internal | `simmer°°°°°°°°°` |
| External | `simmer°°°°°°°e°` |

### 3.4 Flashlamp-activation interlock replies

A failed interlock can replace the normal activation reply with one of these messages:

| Meaning | Reply field |
|---|---|
| Low water flow | `water°flow°°°°°` |
| Water level | `water°level°°°°` |
| Lamp connector | `lamp°connector°` |
| Auxiliary connector | `aux°connector°°` |
| External safety interlock | `I/O°connector` |
| Temperature too low, Celsius form | `tp°CG°<°##°d` |
| Temperature too low, Fahrenheit form | `tp°CG°<°###°F` |
| Cabinet cover open | `switch°cabinet°` |

---

<!-- PDF pages 83-85 and 87-88 | Trouble Shooting Guide pages 14-16 and 18-19 of 19 -->

## 4. Q-switch commands

### 4.1 Read Q-switch parameters

| Command | Purpose | Expected answer field | PDF page |
|---|---|---|---:|
| `QSM<CRLF>` | Read Q-switch mode | `QS°mode°:°°°-°°` | 83 |
| `QSF<CRLF>` | Read Q-switch `F/n` value in auto mode | `cycle°rate°F/--` | 83 |
| `QSP<CRLF>` | Read number of pulses in burst mode | `burst°QS°°°°---` | 83 |
| `QOF<CRLF>` | Read Q-switch on/off-at-run setting | `QS°at°run°°°°°-` | 83 |
| `CQ<CRLF>` | Read Q-switch shot counter, 9 digits | `ct°QS°---------` | 83 |
| `UCQ<CRLF>` | Read Q-switch user's shot counter, 9 digits | `cu°QS°---------` | 83 |
| `W<CRLF>` | Read delay between flashlamp and Q-switch | `delay°°°°---°uS` | 83 |
| `WMN<CRLF>` | Read lower factory limit for Q-switch delay | `dly°QS°m°---°uS` | 87 |
| `WMX<CRLF>` | Read upper factory limit for Q-switch delay | `dly°QS°M°---°uS` | 87 |
| `QSW<CRLF>` | Read number of pulses to wait after lamp start before enabling Q-switch | `QS°wait°:°°---` | 87 |

### 4.2 Program Q-switch parameters

| Command form | Purpose | Range / shown example | Expected answer field | PDF page |
|---|---|---|---|---:|
| `QSM<n><CRLF>` | Set Q-switch mode | `0` = Auto, `1` = Burst, `2` = External. Example: `QSM1` | `QS°mode°:°°°1°°` | 84 |
| `QSF<n><CRLF>` | Set Q-switch `F/n` value | `1-99`. Example: `QSF10` | `cycle°rate°F/10` | 84 |
| `QSP<n><CRLF>` | Set burst pulse count | `1-999`. Example: `QSP50` | `burst°QS°°°°050` | 84 |
| `QOF<n><CRLF>` | Set Q-switch on/off at run | `0` = OFF, `1` = ON. Example: `QOF1` | `QS°at°run°°°°°1` | 84 |
| `UCQ0<CRLF>` | Reset Q-switch user's shot counter | No other value shown | `cu°QS°000000000` | 84 |
| `W<delay><CRLF>` | Set flashlamp-to-Q-switch delay | `100-999 us` and factory limits `Wmin < W < Wmax`. Example: `W225` | `delay°°°°225°uS` | 84 |
| `WMN<delay><CRLF>` | Set lower Q-switch delay limit | `100-999 us`, not configuration 4, and `Wmin < W < Wmax`. Example: `WMN150` | `dly°QS°m°150°uS` | 88 |
| `WMX<delay><CRLF>` | Set upper Q-switch delay limit | `100-999 us`, not configuration 4, and `Wmin < W < Wmax`. Example: `WMX350` | `dly°QS°M°350°uS` | 88 |
| `QSW<n><CRLF>` | Set pulses to wait after lamp start before enabling Q-switch | Example: `QSW100` | `QS°wait°:°°100` | 88 |

### 4.3 Q-switch activation and deactivation

The response combines flashlamp trigger mode with Q-switch state:

- `fire auto` = lamp uses internal trigger
- `fire ext` = lamp uses external trigger
- `qs` = Q-switch active with internal trigger
- `qse` = Q-switch active with external trigger
- Spaces are shown exactly as printed; the active `PQ`/`OQ` forms print as 16 characters despite the manual's general 15-character statement

#### `PQ<CRLF>` - start Q-switch laser emission

| Lamp trigger | Q-switch trigger | Reply as printed |
|---|---|---|
| Internal | Internal | `fire°auto°°°qs°°` |
| Internal | External | `fire°auto°°°qse°` |
| External | Internal | `fire°ext°°°°qs°°` |
| External | External | `fire°ext°°°°qse°` |

#### `SQ<CRLF>` - stop Q-switch laser emission

The lamp remains in its selected firing mode; the reply returns to the corresponding flashlamp-only state:

| Lamp trigger | Q-switch programmed trigger | Reply as printed |
|---|---|---|
| Internal | Internal | `fire°auto°°°°°°` |
| Internal | External | `fire°auto°°°°e°` |
| External | Internal | `fire°ext°°°°°°°` |
| External | External | `fire°ext°°°°°e°` |

#### `OQ<CRLF>` - single Q-switch pulse

Issues a single Q-switch laser pulse in the preselected operating mode. The manual shows the same four `fire ... qs/qse` reply forms as `PQ`.

### 4.4 Q-switch activation interlock replies

| Meaning | Reply field |
|---|---|
| Waiting for the configured number of pulses after flashlamp activation | `wait°for°QS°°°°` |
| Cooling-group temperature below preset, Celsius form | `tp°CG°<°--°d°°°` |
| Cooling-group temperature below preset, Fahrenheit form | `tp°CG°<°###°F` |
| Q-switch stopped at end of timeout | `time°out°QS°°°°` |
| MPS-only interlock | `interlock°QS°°°` |
| Shutter closed | `shutter°closed°` |

---

<!-- PDF pages 86-87 | Trouble Shooting Guide pages 17-18 of 19 -->

## 5. Safety and interlock queries

### 5.1 Flashlamp interlock group 1

The manual lists `IF<CRLF>` or `IF1<CRLF>` and shows the reply:

```text
IF1°ab°cd°ef°gh
```

Bit positions and meanings:

| Position | Required value / meaning when `1` |
|---|---|
| `a` | Low water flow in the closed laser circuit managed by the cooling group |
| `b` | Shown as `0`; no meaning documented |
| `c` | Water-level fault |
| `d` | Lamp-connector head is off |
| `e` | Auxiliary-connector head is off |
| `f` | External safety interlock active/open at the I/O connector |
| `g` | Cabinet-cover switch open |
| `h` | Shown as `0`; no meaning documented |

### 5.2 Flashlamp interlock group 2

The manual lists `IF<CRLF>` or `IF2<CRLF>` and shows:

```text
IF2°ab°cd°ef°gh
```

| Position | Required value / meaning when `1` |
|---|---|
| `a` | Shown as `0`; no meaning documented |
| `b` | Shown as `0`; no meaning documented |
| `c` | Capacitor-loading failure |
| `d` | Simmer failed to initiate |
| `e` | Shown as `0`; no meaning documented |
| `f` | Laser-water temperature below preset value |
| `g` | Shown as `0`; no meaning documented |
| `h` | Shown as `0`; no meaning documented |

When all flashlamp safety interlocks are OK, the manual shows:

```text
IF°00°00°00°00
```

The scan presents `IF` as a general query and also lists `IF1` and `IF2`. A parser should therefore be prepared for the all-zero `IF ...` form as well as `IF1 ...` and `IF2 ...` group replies.

> **Hardware verified (2026-08-07):** on the tested controller a cold first `IF`
> read returns the stale one-deep sample labelled `IF1`, and every subsequent
> read returns the fresh sample labelled `IF.` (for example `IF. 00 00 00 00`).
> The library reads twice and uses the second (fresh) reply, so it must accept
> the `IF.` prefix in addition to `IF` and `IF1`. `IF2` and `IQ` (labelled
> `IQS`) kept a stable prefix across reads.

### 5.3 Q-switch safety query

Command:

```text
IQ<CRLF>
```

Reply:

```text
IQS°ab°cd°ef°gh
```

| Position | Required value / meaning when `1` |
|---|---|
| `a` | Emission inhibited for many pulses following flashlamp activation |
| `b` | Laser-water temperature below preset value |
| `c` | Shown as `0`; no meaning documented |
| `d` | Shown as `0`; no meaning documented |
| `e` | Shown as `0`; no meaning documented |
| `f` | Shown as `0`; no meaning documented |
| `g` | Shutter closed |
| `h` | Shown as `0`; no meaning documented |

> **Partly verified (2026-08-07):** the shutter-closed bit was confirmed — with
> the shutter closed the reply was `IQS 00 00 00 10`, decoding to the
> shutter-closed bit at index `6`. The emission-inhibited bit could **not** be
> captured safely: it advances only on actual flashlamp pulses, and activating
> the flashlamp in external mode with the isolator gating produced no pulses, so
> `IQ` stayed `IQS 00 00 00 10`. Water temperature requires a real thermal fault
> and was not forced. The first two indices (`0/1` vs `1/2`) therefore remain
> unresolved; the code keeps `1`, `2`, `6` unchanged.

### 5.4 HG temperature test

| Command | Purpose | Reply interpretation | PDF page |
|---|---|---|---:|
| `IHG<CRLF>` | Test HG temperature | `IHG°°°°°°°°°°°-`; final status `0` means temperature OK | 87 |

---

## 6. Examples

### Read device 001 shutter state

```text
TX: $001R\r\n
RX: "\r\nshutter opened "
```

The final space is part of the fixed 15-character answer field.

### Set device 001 flashlamp voltage to 1150 V

```text
TX: $001V1150\r\n
RX: \r\nvoltage  1150 V
```

### Broadcast standby without replies

A practical sequence inferred from the manual's collision warning is to disable replies on each addressed unit first, then broadcast standby:

```text
TX: $001ECH0\r\n
TX: $002ECH0\r\n
TX: >S\r\n
```

The manual warns that broadcast replies can collide if multiple devices answer simultaneously.

### Query and decode compact operating status

```text
TX: $001WOR\r\n
RX: \r\nI 0 F 6 S 1 Q 2
```

Decoded using the source table:

- Interlock: OK
- Flashlamp: Start, external synchronization
- Simmer: On
- Q-switch: Start, internal synchronization

---

## 7. Observed firmware behavior

The following details were recorded against the real controller in repository
history and take precedence over spacing inferred from the extracted text:

1. `R` reports `shutter opened` and `shutter closed`.
2. `QSW` responses on the tested controller contain three spaces after the colon,
   producing `QS°wait°:°°°---`; the manual prints two.
3. `IF`, `IF2`, and `IQ` use a one-deep snapshot-on-read buffer. The first read can
   return the previous sample; read twice and use the second response. `WOR` is
   live and does not require the extra read.
4. `VI` is the instantaneous-capacitor-voltage command. The formerly attempted
   `VT` command was invalid and returned no usable response.
5. Fixed decimal echoes can contain trailing zeroes, such as `28.00`; compare
   numeric values rather than reconstructing the response string.
6. Every reply captured on the tested controller (SN 062) was exactly 17 bytes
   (`CRLF` + 15 data characters), including the Section 1.5 templates flagged as
   printed anomalies (`R`, `QSW`, `IF`, `IF2`, `IQ`, and the `A`/`S`/`PQ`/`SQ`
   activation replies). The 17-byte fixed-frame read is correct for the commands
   the library uses.
7. Addressed commands use `$xxx` (three-digit zero-padded serial number); the
   unprefixed decimal form returns no reply. See Section 1.2.
8. The `WOR` middle labels are `F`/`S` on this firmware; the fresh flashlamp
   interlock-1 prefix is `IF.`. See Sections 2.3 and 5.2.
9. With the Q-switch in external mode (`QSM2`), `PQ` does not drive the `WOR`
   Q-switch field to a continuous `Start` code; it stays at the external `Stop`
   code (`Q 4`) while awaiting external triggers. Flashlamp `A` does report
   `Start` (`F 6`). The library's `arm()` verification accounts for this: it
   requires the Q-switch `Start` only under internal synchronization.
10. Captured reply templates for the previously unexposed commands (now exposed
    by the API), all exactly 17 bytes:

    | Command | Captured reply | Notes |
    |---|---|---|
    | `X` | `SPECTRA-SY 3.68` | model + revision (manual printed `SPECTRA-SC`) |
    | `DAT` | `20/12/02` | `dd/mm/yy` |
    | `CGF` | `temp. CG 091 F ` | Fahrenheit cooling-group temperature |
    | `T` | `ct time 7040:23` | `hhhh:mm` |
    | `ROF` | `shutt. at run 0` | shutter-at-run flag |
    | `ECH` | `echo on        ` | reply/echo mode |
    | `VMO` | `Voltage m0950 V` | average lamp voltage (capital `V`) |
    | `D` | `dis charg 00.0S` | idle-fire interval, seconds |
    | `E` | `ena charg 00.0S` | enable-fire interval, seconds |
    | `WMN` | `dly QS m 100 uS` | lower Q-switch delay limit |
    | `WMX` | `dly QS M 500 uS` | upper Q-switch delay limit |
    | `QSW<n>` | `QS wait :   000` | echo confirmed by a non-destructive set |
    | `IHG` | `IHG           0` | final digit `0` = temperature OK |

## 8. Implementation cautions

1. The manual specifies a 15-character answer field after an initial `CRLF`, but several printed templates conflict with that rule. Preserve the raw reply and validate actual firmware behavior before enforcing a fixed width.
2. `ECH0` suppresses responses but does not prevent command execution.
3. Avoid broadcast queries while replies are enabled on multiple devices.
4. Preserve leading zeroes in 9-digit counters and three-digit fields.
5. Several source examples contain apparent typographical inconsistencies, including the `D10`/`E25` timing replies and the reply-length anomalies listed in Section 1.5. This reference preserves and flags them rather than silently correcting them.
6. The serial electrical and port settings are outside PDF pages 79-88 and are therefore not included here.


---

## Transcription record

Checked against PDF pages 79-88 on 2026-08-07. This records verification of the manual transcription, not hardware verification of every wire-format detail. Definite corrections from the earlier draft include the `X` software-revision template, the printed `PQ`/`OQ` reply spacing, the `QSW` field spacing, and removal of padding that was not printed for several interlock messages. The `ROF` read and programming templates are preserved as the 14-character strings printed in the manual.
