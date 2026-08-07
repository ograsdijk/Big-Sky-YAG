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
- `uv build` and `twine check` pass, and the wheel contains `py.typed`.
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
- Device-independent parser, descriptor, transport, bit-field, interlock, and
  transition tests are in place.
- README, package metadata, CI, publishing, and the manual-versus-firmware notes
  have been updated.

The unresolved work is limited to behavior that needs new device captures:
numbered addressing, literal `WOR` labels, the first two `IQ` bit positions, exact
`SN` capitalization, anomalous reply lengths, and echoed responses for potential
new setters.

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

#### 2. `WOR` status parsing accepts unsupported values and ignores labels — **PARTIAL**

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

#### 4. Q-switch interlock bit mapping may be off by one — **PENDING DEVICE**

After the eight printed bits are reversed, manual positions `a`, `b`, and `g`
correspond to bit indices `0`, `1`, and `6`. The implementation currently uses
`1`, `2`, and `6` for emission inhibited, water temperature, and shutter closed.

The flashlamp `IF1` and `IF2` mappings agree with the reference. The Q-switch
mapping needs a controlled hardware capture before changing behavior.

#### 5. Serial-number addressing may omit the required prefix and padding — **PENDING DEVICE**

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
- Keep the high-level `LaserTransitionError` message concise while retaining all
  underlying causes.

#### 8. Serial framing assumptions need explicit handling — **PARTIAL**

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
- Validate distributions with `twine check`.
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

#### 18. Several documented commands are not exposed by the API — **DEFERRED**

Currently unsupported reference commands include `X`, `DAT`, `CGF`, `T`, `ROF`,
`ECH`, `SUC`, `VMO`, `D`, `E`, `WMN`, `WMX`, and `IHG`.

Two existing read-only areas have obvious documented write operations:

- `UCQ0` resets the Q-switch user counter.
- `QSW<n>` sets the number of flashlamp pulses to wait.

Planned correction:

- Treat these as API enhancements, not defects.
- Add only commands whose response layout and safety implications are understood.
- Start with `UCQ0` and `QSW<n>` after capturing their actual echoed responses.
- Do not expose `ECH0` through a normal request/response method without designing
  for the intentional absence of its response.
- Avoid adding factory-limit setters `WMN` and `WMX` until their configuration
  restrictions and safety implications are documented.

### P3: Package and API polish

#### 19. Public exports and naming are inconsistent — **PARTIAL**

Planned correction:

- Decide whether `LaserStatus`, `Status`, `Trigger`, `QSwitchMode`, interlock state
  dataclasses, and `SerialInstrument` are supported public objects.
- Export supported objects consistently through `big_sky_yag.__init__`.
- Reconcile names such as `q_switch` versus `qswitch` and `counter_user` versus
  `user_counter`, preserving compatibility aliases or using a deprecation cycle.
- Consider frozen status dataclasses because they represent snapshots.
- Consider making `resource_name` optional when an injected instrument is given.

Completed: supported enums, status models, interlock models, errors, and the serial
transport are exported consistently; snapshot dataclasses are immutable. Remaining:
optional naming aliases and optional `resource_name` ergonomics are compatibility
enhancements rather than correctness blockers.

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

- [x] Introduce `BigSkyYagError`, `LaserProtocolError`, and the existing transition
  error under a consistent hierarchy.
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

1. [ ] **Numbered addressing**
   - Try the documented `$xxx` form on a safely readable command.
   - Compare with the current unprefixed numeric form.
   - Determine required zero-padding and valid address range.

2. [ ] **`WOR` response**
   - Capture at least one internal and one external synchronization state.
   - Confirm whether literal labels are `I/F/S/Q`, `I/L/M/Q`, or firmware-specific.
   - Confirm all state codes used by the tested controller.

3. [ ] **Q-switch `IQ` bit mapping**
   - Capture a baseline response and controlled responses for emission inhibited,
     water-temperature interlock, and shutter closed where safely possible.
   - Confirm whether the correct indices are `0/1/6` or `1/2/6` after reversal.

4. [ ] **Serial-number response**
   - Capture `SN` exactly.
   - Confirm `S/Number` versus `s/number`, field width, and zero-padding.

5. [ ] **Anomalous reply lengths used by the library**
   - Capture `R`, `QSW`, `IF`, `IF2`, `IQ`, `A`, `S`, `M`, `PQ`, `SQ`, and `OQ`.
   - Confirm whether every actual response is 15 characters after `CRLF`.
   - Determine whether active `PQ`/`OQ` responses are actually 15 or 16 characters.

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

### Phase 5: Hardware verification checkpoint — **PENDING DEVICE**

1. Collect the required raw captures.
2. Add sanitized capture fixtures to tests where appropriate.
3. Resolve addressing, `WOR` labels, `IQ` indices, `SN` capitalization, and reply
   lengths.
4. Update the command reference with observed-firmware annotations.

Exit criteria:

- Every strict parser is based on captured controller output or explicitly permits
  documented firmware variants.
- No unresolved wire-format assumption is presented as verified fact.

### Phase 6: Documentation and selected API coverage — **PARTIAL**

1. Rewrite the primary README example around lifecycle and verified transitions.
2. Document units, ranges, interlocks, exceptions, and operational limitations.
3. Add `UCQ0` and writable `QSW` only if their captures are complete.
4. Defer other protocol commands until demanded by a concrete use case.

Documentation is complete. The optional `UCQ0` and writable `QSW` API additions
remain deferred until their echoed responses are captured.

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
uv run --with twine twine check dist/*
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
