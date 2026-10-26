# Big Sky YAG Repository Improvement Plan

## Purpose

This plan combines the repository-wide code, typing, testing, documentation,
packaging, and CI audit with the comparison against
`big_sky_bss_rs485_command_reference.md`.

The repository is small and its configured checks currently pass, but the checks
do not cover the whole typed package and several protocol parsers can interpret
malformed controller responses as valid states. Because this library controls
laser hardware, positive validation of operational and safe states takes priority
over API expansion and packaging polish.

No command-reference spacing or symbol should be treated as authoritative merely
because it was extracted from the PDF. Evidence should be ranked as follows:

1. Raw responses captured from the real controller.
2. Repository history explicitly recorded as hardware-verified.
3. Page-image content from the service manual.
4. Extracted Markdown text and test simulators.

## Current baseline

- `uv run pytest`: 81 tests pass with 95%+ statement coverage.
- `uv run ruff check .`: passes.
- Configured strict `uv run mypy`: passes across `big_sky_yag` and `tests`.
- `uv build` passes, and the wheel contains `py.typed`. The publishing action
  validates distribution metadata before uploading.
- The working command names, scaling rules, and ranges largely agree with the
  command reference.

## Implementation status (2026-08-07)

The device-independent work in this plan has been implemented:

- Unknown and malformed state responses raise explicit protocol errors.
- `WOR` numeric domains are validated without choosing the unresolved middle
  labels.
- Arm/disarm timing is validated before commands are sent, and rollback failures
  preserve the original error.
- Descriptors and the full package pass strict typing without production ignores.
- Serial cleanup, context-manager support, encoding handling, and incomplete-read
  errors are implemented.
- `port` is the canonical connection parameter, `resource_name` remains a
  compatibility alias, and injected instruments no longer require a dummy port.
- Device-independent parser, descriptor, transport, bit-field, interlock, and
  transition tests are in place.
- README, package metadata, CI, publishing, and the manual-versus-firmware notes
  have been updated.

Most of this has since been resolved by hardware verification and a firing test
(see the sections below). The only remaining device-gated item is the
water-temperature `IQ` bit, which needs a real thermal-interlock fault to assert.

### Hardware verification (2026-08-07, controller SN 062, COM10)

A live verification pass against the real controller resolved most of the
pending captures and surfaced two protocol defects that were then fixed:

- **Numbered addressing** is `$xxx` (three-digit zero-padded serial number).
  `$062SN` is answered; `062SN`/`62SN`/`>062SN` are not. The library previously
  emitted the unprefixed decimal form and got no reply — **fixed** to `$xxx`.
- **Flashlamp interlock (`IF`)** returns the fresh sample with prefix `IF.`
  (the stale one-deep sample is `IF1`). The parser accepted only `IF`/`IF1`, so
  `flashlamp.interlock` raised on every real read — **fixed** by accepting `IF.`.
- **`WOR` labels** are `I/F/S/Q` on this firmware (not the simulator's
  `I/L/M/Q`); the parser stays label-permissive for portability.
- **`SN`** is lowercase `s/number`, three-digit zero-padded.
- **Reply framing:** every command used by the library replied with exactly 17
  bytes (`CRLF` + 15 data chars), including the templates flagged as printed
  anomalies. The fixed 17-byte read is correct.
- **`disarm()`** was verified end-to-end on hardware (shutter closed, Q-switch
  and flashlamp stopped, safe state positively confirmed).
- **`arm()` in external mode — fixed.** With the Q-switch in external mode
  (`QSM2`, this system's operating mode), `PQ` never drives `WOR` to a
  continuous Q-switch `Start`. `arm()`'s verification is now mode-aware: it
  requires the Q-switch `Start` only under internal synchronization; under
  external synchronization it verifies the flashlamp `Start` and open shutter
  (the positively confirmable signals) and does not demand the unreachable
  Q-switch `Start`. Hardware operation requires the arming sequence to start the
  flashlamp, open the shutter, and only then start the Q-switch. Disarm still
  confirms the stopped state in both modes.

A follow-up firing test (2026-08-07, isolator-gated) resolved the last two items:

- **`IQ` bit mapping — fixed** to `0/1/6`. Emission inhibited was captured live
  (`IQS 10 00 00 00` during the inhibit window → bit `0`); shutter closed sits at
  bit `6`. The previous `1/2/6` never reported emission inhibited. Water
  temperature (bit `1`) follows the same validated order (not directly asserted).
- **Active `PQ`/`OQ` reply length — resolved to 15 chars** (`fire ext   qse `),
  confirming the fixed 17-byte read; the manual's 16-char note was a print
  artifact. Verified by passing a single Q-switch trigger through the isolator.

Remaining device work is limited to the water-temperature `IQ` bit (needs a real
thermal-interlock fault) and the optional `UCQ0`/`SUC` echoes; neither blocks
current behavior.

## Consolidated findings

Status labels used below:

- **FIXED**: implemented and covered by local checks.
- **PARTIAL**: the device-independent portion is implemented, with a clearly
  identified remainder.
- **PENDING DEVICE**: intentionally unchanged until a real-device capture exists.
- **DEFERRED**: optional API expansion rather than a defect in current behavior.

### P0: Safety and protocol correctness

#### 1. Malformed shutter responses can be treated as safely closed — **FIXED**

`BigSkyYag.shutter` currently returns `False` for every response other than the
exact open response. An empty, truncated, error, or unknown response can therefore
be interpreted as a closed shutter during `disarm()` verification.

Planned correction:

- Accept only the real controller's known open and closed replies.
- Raise a dedicated protocol-response exception for every other value.
- Test empty, truncated, mislabeled, and unknown replies.

#### 2. `WOR` status parsing accepts unsupported values and ignores labels — **FIXED (labels captured)**

The parser checks token count and numeric conversion but does not validate literal
labels or the complete numeric domains. Modulo decoding can accept some negative
or unsupported values. Interlock and simmer values are not restricted to `0` and
`1`.

The manual extraction shows `I/F/S/Q`, while the test simulator emits `I/L/M/Q`.
The implementation currently ignores these labels, so the discrepancy is hidden.

Completed: numeric fields, outer labels, structure, and documented value domains
are validated. Remaining: choose the two middle literal labels after a raw device
capture.

Planned correction:

- Restrict interlock and simmer to `0` or `1`.
- Restrict flashlamp and Q-switch states to `0, 1, 2, 4, 5, 6`.
- Decode synchronization explicitly instead of using permissive modulo logic.
- Validate the literal labels after capturing a real `WOR` response.
- Ensure invalid responses can never satisfy `arm()` or `disarm()`.

#### 3. Other boolean and enum parsers are too permissive — **FIXED**

Pump state, Q-switch-at-run state, trigger mode, and Q-switch mode should validate
the complete response rather than extracting any value that happens to convert.
Several parsers misuse `str.strip("prefix")`; `strip()` removes a set of characters
from both ends and does not remove a literal prefix.

Planned correction:

- Introduce shared exact-response parsing helpers.
- Accept only the documented numeric domains.
- Replace character-set stripping with literal prefix and fixed-field parsing.
- Include the raw response in every protocol error.

#### 4. Q-switch interlock bit mapping was off by one — **FIXED**

After the eight printed bits are reversed, manual positions `a`, `b`, and `g`
correspond to bit indices `0`, `1`, and `6`. The implementation previously used
`1`, `2`, and `6`, so `EMISSION_INHIBITED` was read from the wrong bit and never
reported correctly.

Resolved by live firing (2026-08-07): during the Q-switch inhibit window
(flashlamp pumping, shutter open) the reply was `IQS 10 00 00 00`, decoding to the
emission-inhibited bit at index `0`; shutter-closed was confirmed at index `6`
(`IQS 00 00 00 10`). The code now uses `0`, `1`, `6`. Water temperature (index
`1`) follows the same validated reversed order but was not directly asserted (it
needs a real thermal fault, which was not forced).

#### 5. Serial-number addressing may omit the required prefix and padding — **FIXED**

The reference specifies addressed commands such as `$042P1`. The implementation
and fake test currently produce `42P1`. Broadcast commands using `>` agree with
the manual and have stronger real-device evidence; numbered addressing does not.

The addressed form must be tested on hardware before changing the public behavior.
If confirmed, serial numbers should be validated as `0..999` and formatted as
`$xxx` with three digits.

### P1: Transition and transport reliability

#### 6. Transition timing arguments are not validated — **FIXED**

Negative timeout values are silently converted to zero, zero polling intervals
can create a busy loop, and non-finite values have undefined behavior.

Planned correction:

- Require finite numeric values.
- Require `timeout_s >= 0`.
- Require `poll_s > 0`, with an explicit rule for the zero-timeout test case.
- Fail before sending commands when arguments are invalid.

#### 7. Arm rollback can lose the original failure — **FIXED**

If arming fails and rollback also fails, the raised exception preserves the
rollback failure but not the original cause in a structured form.

Planned correction:

- Preserve the original arm failure, rollback command failures, and rollback
  verification failure, using an `ExceptionGroup` where appropriate.
- Keep the high-level `BigSkyYagTransitionError` message concise while retaining all
  underlying causes.

#### 8. Serial framing assumptions need explicit handling — **FIXED (framing confirmed)**

The transport reads 17 bytes based on `CRLF` plus a 15-character answer. The
manual prints several anomalous response lengths, while repository history records
real-device fixed-width behavior and stale-response desynchronization.

Planned correction:

- Do not change framing until raw captures exist for anomalous commands used by
  the library.
- Detect and report incomplete reads rather than passing them to property parsers.
- Keep raw responses available in errors.
- Apply the configured encoding consistently to writes and reads, or document
  ASCII as the only supported encoding.
- Replace the stale comment claiming `VT` is an example command that returns
  nothing; `VI` is the valid instantaneous-voltage command and `VT` was invalid.
- Document that instances are not thread-safe unless transaction locking is added.

Completed: incomplete reads and decoding failures have explicit transport errors,
encoding is applied consistently, the stale `VT` comment is corrected, and
thread-safety limitations are documented. Remaining: confirm anomalous complete
response lengths on hardware before changing the 17-byte framing rule.

#### 9. The main device API does not expose cleanup — **FIXED**

`SerialInstrument` has `close()`, but `BigSkyYag` does not provide a documented
cleanup or context-manager path.

Planned correction:

- Add `BigSkyYag.close()`.
- Add `__enter__` and `__exit__`.
- Track whether the device owns an internally created instrument.
- Do not close an injected instrument unless ownership is explicitly transferred.
- Extend the transport protocol to express optional or required lifecycle support.

### P1: Typing and public API correctness

#### 10. Strict mypy excludes most of the shipped package — **FIXED**

The current mypy file list excludes `attributes.py`, `bit_handling.py`, and
`interlock.py`. Running strict mypy over the package reports 26 errors.

Planned correction:

- Change mypy scope to `big_sky_yag` and `tests`.
- Type every public and internal method argument and return.
- Replace incomplete legacy generics such as bare `List`.
- Rename the protocol called `BigSkyYag` in `attributes.py` to avoid confusion
  with the concrete device class.
- Remove the production `type: ignore` after typing `QSwitch` correctly.

#### 11. Descriptor typing and class access are incorrect — **FIXED**

The property descriptors have untyped instance and owner parameters, untyped
variadic constructors, incompatible override ignores, and setters annotated as
returning strings even though assignment discards descriptor return values. Class
access attempts to query through `None` instead of returning the descriptor.

Planned correction:

- Make the descriptors generic over their value type.
- Add overloaded `__get__` signatures for class and instance access.
- Make `__set__` return `None`.
- Move write-and-verify behavior into an internal method that can return the raw
  controller response.
- Use explicit typed constructor parameters instead of untyped `*args` and
  `**kwargs`.
- Add downstream type-check examples for integer and floating-point assignments.

#### 12. `Bits` has incomplete types and weak input validation — **FIXED**

Planned correction:

- Return `list[int]` from `get_set_bits()`.
- Type enum arguments precisely.
- Prefer boolean bit values or validate integer inputs as `0` or `1`.
- Reject negative bit indices.

### P2: Tests and CI

#### 13. Protocol behavior is sparsely tested — **FIXED**

Tests do not cover interlock decoding, most descriptor reads and writes, trigger
and mode parsing, property echo validation, temperature and counters, resource
cleanup, incomplete serial reads, or most transition error paths.

Planned correction:

- Split tests into focused modules for device transitions, descriptors, transport,
  and interlocks.
- Share fake transports and controller state fixtures through `conftest.py` when
  useful.
- Add valid and malformed-response tables for every parser.
- Test snapshot-on-read behavior for `IF`, `IF2`, and `IQ`.
- Add delayed transition success, transient read failure, rollback failure, and
  timing-validation tests.
- Add coverage measurement after the known gaps are filled; use a practical
  threshold rather than selecting one before the baseline is known.

#### 14. CI's green type check gives incomplete assurance — **FIXED**

Planned correction:

- Run full-package strict mypy in CI.
- Keep Ruff formatting and lint checks.
- Run the expanded protocol and transition test suite on all supported Python
  versions.
- Build both wheel and source distribution.
- Validate distribution metadata through the PyPI publishing action.
- Confirm that `py.typed` is included in the wheel.

#### 15. Publishing can attempt the same release twice — **FIXED**

The publish workflow triggers on both a `v*` tag and a published GitHub release.
A normal tag-plus-release flow can therefore attempt to upload one version twice.
Tag pushes also do not run the main CI workflow unless they point at `main` through
another triggering event.

Planned correction:

- Choose one release trigger, preferably `release: published`.
- Ensure the exact commit or artifact being published passed tests, lint, full
  mypy, build, and metadata validation.
- Prefer promoting a previously tested artifact over rebuilding an unverified one.
- Retain minimal trusted-publishing permissions and the protected PyPI environment.

### P2: Documentation and command-reference alignment

#### 16. README usage is incomplete and contains a unit error — **FIXED**

The README calls Q-switch delay nanoseconds, while both code and reference specify
microseconds. It also omits installation, cleanup, transition methods, exception
behavior, connection options, and a complete safe shutdown sequence.

Planned correction:

- Correct Q-switch delay to microseconds.
- Add installation and supported-Python instructions.
- Demonstrate connection through a context manager.
- Document pump startup, coolant-flow settling, interlock inspection, arming,
  disarming, pump shutdown, and connection cleanup.
- Document what `arm()` and `disarm()` verify and what they do not manage.
- Include a laser-safety warning that software checks do not replace physical
  interlocks and approved operating procedures.
- Correct docstring mistakes such as `state (str)` for boolean setters and
  `Raises: Type` instead of `TypeError`.

#### 17. The command reference mixes manual transcription and firmware facts — **FIXED**

The reference should preserve printed manual layouts while clearly distinguishing
them from observed controller behavior.

Planned correction:

- Rename or qualify "Verified reference" so it does not imply every printed
  space and symbol was verified on hardware.
- Add explicit evidence labels: "printed in manual", "observed on tested
  firmware", and "unresolved".
- Record the hardware-verified three spaces in the `QSW` response while preserving
  the manual's printed two-space form.
- Record the hardware-verified one-deep snapshot behavior of `IF`, `IF2`, and
  `IQ`; the second read is current while the first can be stale.
- Record the verified shutter words `opened` and `closed`.
- Mark exact `WOR` labels, numbered addressing, serial-number capitalization, and
  Q-switch interlock bit positions as unresolved pending captures.
- Preserve warnings about reply-length anomalies rather than normalizing strings
  to 15 characters without evidence.

#### 18. Several documented commands are not exposed by the API — **FIXED**

All of the previously unsupported reference commands are now exposed, with parsers
based on responses captured from the real controller (2026-08-07, SN 062):

- Reads: `X` (`software_revision`), `DAT` (`software_revision_date`), `CGF`
  (`temperature_cooling_group_fahrenheit`), `T` (`operating_time`), `ROF`
  (`shutter_at_run`), `ECH` (`echo`), `VMO` (`flashlamp.voltage_average`), `D`
  (`flashlamp.idle_fire_interval`), `E` (`flashlamp.enable_fire_interval`), `WMN`
  (`qswitch.delay_min`), `WMX` (`qswitch.delay_max`), `IHG` (`hg_temperature_ok`).
- Writes: `ROF<n>`, `D<n>`, `E<n>`, `WMN<delay>`, `WMX<delay>`, writable
  `QSW<n>` (`qswitch.pulses_wait`), `UCQ0` (`qswitch.user_counter_reset`), `SUC`
  (`flashlamp.save_user_counter`), and `ECH1/ECH0` via `set_echo`.

Safety handling applied:

- `ECH0` is written through `set_echo(False)` without waiting for a reply (it
  produces none), and its docstring warns that the controller stops answering
  until `ECH1`. It is not exercised on real hardware.
- `WMN`/`WMX` factory-limit setters are range-validated (`100..999`) and carry
  README safety notes; they were implemented and unit-tested but not written to
  the real device.
- `QSW<n>` echo was captured non-destructively (set to its current value);
  `UCQ0`/`SUC` echoes follow the documented templates and were not actuated on
  hardware.

### P3: Package and API polish

#### 19. Public exports and naming are inconsistent — **FIXED**

Planned correction:

- Decide whether `LaserStatus`, `Status`, `Trigger`, `QSwitchMode`, interlock state
  dataclasses, and `SerialInstrument` are supported public objects.
- Export supported objects consistently through `big_sky_yag.__init__`.
- Reconcile names such as `q_switch` versus `qswitch` and `counter_user` versus
  `user_counter`, preserving compatibility aliases or using a deprecation cycle.
- Consider frozen status dataclasses because they represent snapshots.
- Use the PySerial term `port`, retain `resource_name` as a compatibility alias,
  reject ambiguous use of both, and allow instrument injection without a dummy
  port.

Completed: supported enums, status models, interlock models, errors, and the serial
transport are exported consistently; snapshot dataclasses are immutable; `port`
is canonical while `resource_name` remains compatible; and injected instruments
need no dummy port. Naming is now reconciled: `LaserStatus` exposes `qswitch` /
`qswitch_synchronization` aliases matching the `yag.qswitch` device name (the
`q_switch*` fields remain), and the Q-switch user counter was renamed to
`user_counter` / `user_counter_reset()` to match the flashlamp (the old
`counter_user` / `counter_user_reset()` names were removed, no alias).

#### 20. Packaging metadata is minimal — **FIXED**

Planned correction:

- Add license metadata and appropriate classifiers.
- Add documentation and issue-tracker URLs.
- Verify README rendering and wheel contents.
- Keep declared Python support aligned with the CI matrix.

## Work that can be completed without new device verification

The tasks below either do not depend on wire-level details or are backed by an
existing hardware-verification record.

### Protocol safety and internal behavior

- [x] Introduce a consistent `BigSkyYagError`, `BigSkyYagProtocolError`,
  `BigSkyYagTransportError`, and `BigSkyYagTransitionError` hierarchy, with no
  legacy aliases.
- [x] Make unknown shutter, pump, mode, trigger, and boolean responses fail closed
  instead of silently producing a state. Exact accepted layouts should initially
  include only already observed responses.
- [x] Restrict documented numeric domains for `WOR` while postponing literal-label
  validation until a raw response is captured.
- [x] Validate transition timing arguments.
- [x] Preserve original and rollback failures together.
- [x] Keep and test the hardware-recorded double-read behavior for `IF`, `IF2`, and
  `IQ`.
- [x] Keep the hardware-recorded three-space `QSW` template and document the manual
  difference.
- [x] Correct the stale `VT` comment because `VI` is the verified command.

### Typing, testing, lifecycle, and tooling

- [x] Extend strict mypy to the full package.
- [x] Redesign and type descriptors.
- [x] Complete annotations in `attributes.py` and `bit_handling.py`.
- [x] Add class-level descriptor behavior.
- [x] Add cleanup and context-manager support with explicit instrument ownership.
- [x] Add malformed-response, range-validation, transition, descriptor, and bit-helper
  tests that do not depend on unresolved response labels.
- [x] Add coverage measurement, distribution validation, and wheel-content checks.
- [x] Fix the duplicate publish trigger and require verified artifacts.

### Documentation and packaging

- [x] Correct the Q-switch delay unit from ns to us/microseconds.
- [x] Expand installation, lifecycle, transition, exception, and safety documentation.
- [x] Correct existing type and exception names in docstrings.
- [x] Separate manual transcription from firmware-observed facts in the command
  reference.
- [x] Add package metadata and clarify public exports.

## Work that requires new device verification

Each item should be verified by recording the exact transmitted bytes and raw
response bytes, including `CRLF`, capitalization, padding, and total length.

### Required captures

1. [x] **Numbered addressing** — captured 2026-08-07 (SN 062). Addressed form is
   `$xxx` (three-digit zero-padded); `$062SN` answered, unprefixed/`>`-prefixed
   numeric forms did not. Library updated to `$xxx` with 0..999 range validation.

2. [x] **`WOR` response** — captured 2026-08-07. Labels are `I/F/S/Q`; observed
   codes include flashlamp `4`/`6` and Q-switch `4` under external sync. Parser
   left label-permissive; command reference updated.

3. [x] **Q-switch `IQ` bit mapping** — resolved to `0/1/6` by live firing
   (2026-08-07). Emission inhibited captured directly (`IQS 10 00 00 00` → bit 0)
   and shutter closed at bit 6 (`IQS 00 00 00 10`); code updated from `1/2/6`.
   Water temperature (bit 1) follows the same validated order but needs a real
   thermal fault to assert (not forced).

4. [x] **Serial-number response** — captured 2026-08-07: `s/number    062`
   (lowercase, three-digit zero-padded).

5. [x] **Anomalous reply lengths used by the library** — captured 2026-08-07.
   Every command the library uses (`R`, `QSW`, `IF`, `IF2`, `IQ`, `A`, `S`,
   `PQ`, `SQ`, plus all reads) replied with exactly 17 bytes (`CRLF` + 15). The
   fixed 17-byte read is correct; the printed anomalies were manual artifacts.

6. [ ] **Potential API additions**
   - Capture `UCQ0` and `QSW<n>` echoed responses before exposing setters.
   - Capture other commands only when there is a concrete API requirement.
   - Design `ECH0` separately because no response is expected by definition.

### Capture format

Store each observation in a small, reviewable record containing:

```text
Controller model/firmware:
Connection settings:
Precondition/state:
TX bytes (escaped):
RX bytes (escaped):
RX byte count:
Repeated result:
Operator notes:
```

Do not trigger fault conditions solely to complete documentation. Interlock
captures should only be taken under an approved and safe hardware procedure.

## Implementation sequence

### Phase 1: Device-independent safety regression tests — **COMPLETED**

1. Add shared fake-transport fixtures.
2. Add malformed shutter, pump, Q-switch status, trigger, and mode tests.
3. Add domain tests for all documented `WOR` numeric values.
4. Add tests proving malformed responses cannot verify arm or disarm.
5. Add transition timing and rollback-cause tests.

Exit criteria:

- Current unsafe behavior is represented by failing tests before production fixes.
- Tests require no physical controller.

### Phase 2: Protocol exception and parser hardening — **COMPLETED**

1. Add a protocol exception hierarchy.
2. Add reusable exact-field parsing helpers.
3. Harden all parsers whose accepted real responses are already known.
4. Restrict `WOR` numeric domains without yet enforcing unresolved labels.
5. Improve transition failure aggregation.

Exit criteria:

- Unknown responses cannot silently become operational or safe states.
- Errors include the command and raw response.

### Phase 3: Full typing and descriptor repair — **COMPLETED**

1. Expand mypy scope.
2. Type the transport/controller protocol and subcomponents.
3. Redesign descriptors with generics and overloads.
4. Complete bit-helper types and validation.
5. Remove production ignores.

Exit criteria:

- `uv run mypy --strict big_sky_yag tests` passes.
- Downstream assignment examples reveal the expected types.

### Phase 4: Lifecycle, transport, and test-suite expansion — **COMPLETED**

1. Add `close()` and context-manager support.
2. Apply encoding consistently.
3. Detect incomplete reads without changing unresolved full-response framing.
4. Add interlock, descriptor, echo-validation, and cleanup tests.
5. Establish coverage reporting and then choose a justified threshold.

Exit criteria:

- Owned serial resources close deterministically.
- Transport failures are distinct from protocol-content failures.

### Phase 5: Hardware verification checkpoint — **COMPLETED (one bit device-gated)**

Completed 2026-08-07 against the real controller (SN 062) plus an isolator-gated
firing test. Addressing (`$xxx`), `WOR` labels (`I/F/S/Q`), `SN` capitalization,
reply framing (17 bytes, including active `PQ`/`OQ`), the `IF.` interlock prefix,
and the `IQ` bit mapping (`0/1/6`) are all resolved and annotated in the command
reference. The only item still device-gated is the water-temperature `IQ` bit,
which needs a real thermal-interlock fault to assert and was not forced.

1. Collect the required raw captures.
2. Add sanitized capture fixtures to tests where appropriate.
3. Resolve addressing, `WOR` labels, `IQ` indices, `SN` capitalization, and reply
   lengths.
4. Update the command reference with observed-firmware annotations.

Exit criteria:

- Every strict parser is based on captured controller output or explicitly permits
  documented firmware variants.
- No unresolved wire-format assumption is presented as verified fact.

### Phase 6: Documentation and selected API coverage — **COMPLETED**

1. Rewrite the primary README example around lifecycle and verified transitions.
2. Document units, ranges, interlocks, exceptions, and operational limitations.
3. Add `UCQ0` and writable `QSW` only if their captures are complete.
4. Defer other protocol commands until demanded by a concrete use case.

Documentation is complete. `UCQ0` and writable `QSW` are now exposed (their echoes
were captured), and the remaining reference commands were also added; see finding
#18.

Exit criteria:

- A new user can install, connect, configure, operate, disarm, and close the device
  from the documentation.
- Manual text and observed firmware behavior are clearly distinguished.

### Phase 7: CI, publishing, and package polish — **COMPLETED**

1. Enforce full-package typing and expanded tests in CI.
2. Validate built distributions and `py.typed` inclusion.
3. Use a single publication trigger and publish only verified artifacts.
4. Finalize public exports, compatibility aliases, and package metadata.

Exit criteria:

- One release produces one publication attempt.
- The published artifact is the artifact that passed all quality gates.

## Verification commands

Run after each implementation phase:

```powershell
uv lock --check
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv build
```

During the typing phase, also run the explicit full-package command until the
configuration itself is updated:

```powershell
uv run mypy --strict big_sky_yag tests
```

## Definition of done

The improvement effort is complete when:

- No malformed or unknown response can be interpreted as a verified armed or safe
  state.
- Strict mypy covers the entire shipped package and passes.
- Public descriptors expose correct downstream types.
- Serial resources have deterministic cleanup.
- Protocol parsers have valid and malformed-response coverage.
- Unresolved device behavior has been captured or is explicitly documented as
  unsupported rather than guessed.
- README units and examples agree with verified controller behavior.
- Manual transcription and observed firmware facts are clearly separated.
- CI validates the exact artifact published through a single release path.
