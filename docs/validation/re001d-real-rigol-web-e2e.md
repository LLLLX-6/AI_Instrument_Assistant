# RE-001D Real Rigol Interactive Web E2E Validation

Status: **INTERACTIVE WEB RE-001D REAL RIGOL EXECUTION PATH PROVEN**
(bounded RE-001D path only)

Validation date: 2026-09-19

## Scope

This validation proves one bounded conversational path in the real DeepSeek
Harness Web against the real instrument:

```text
Browser
  -> DeepSeek Harness Web
  -> RE-001D prepare
  -> canonical physical confirmation (normal user chat message)
  -> 2 ProbeSetupConfirmations
  -> 4 one-shot TrustedOperationScopes
  -> authenticated Hardware IPC
  -> REAL Rigol DS1102Z-E
  -> four ordered real measurements
  -> canonical results with source="instrument"
  -> strict canonical mapping
  -> deterministic analysis
  -> Evidence
  -> grounded publication
  -> safe final Egress
```

This milestone proves only the bounded RE-001D path. It does not claim:
all possible REAL hardware behavior, arbitrary experiment support,
autonomous laboratory operation, sweep/waveform/PWM coverage, or
multi-instrument support.

## Code baseline

- RE-001D FAKE Web checkpoint: `4719eff`
  (`checkpoint(re001d): prove interactive web RE-001D FAKE path`,
  tag `re001d-fake-web-path-proven`)
- Semantic fix: `5dd9326`
  (`fix(re001d): remove implicit frequency target`)
- Automated baseline on this code: Python 683/683, Harness
  unit/contract/architecture 210/210, integration/model 39/39,
  FAKE E2E 6/6, strict typecheck and production build PASS.

## Instrument identity (masked)

- Manufacturer: RIGOL TECHNOLOGIES
- Model: DS1102Z-E
- Firmware: 00.06.03.SP2
- Serial: `***9517` (masked; the full serial and the full VISA resource
  string are intentionally not recorded)

## Physical setup

Both oscilloscope channels were connected to the same STM32 signal node
(CH1 = declared Vin, CH2 = declared Vout, both probe grounds on STM32 GND).
The user confirmed a safe low-voltage signal (maximum expected voltage
approximately 3.3 V) and verified the physical probe attenuation switches
against the oscilloscope channel probe-ratio settings before the final run.

## Previous probe-ratio issue and physical correction

An earlier REAL run (before `5dd9326`) measured:

- CH1 Vpp ~= 0.408 V
- CH2 Vpp ~= 4.12 V

— an approximately 10x discrepancy between two channels probing the same
node. The user physically diagnosed this as an inconsistent probe
attenuation/configuration setting and corrected it outside the software.
After correction the oscilloscope manually showed approximately
CH1 Vpp = 416 mV, CH2 Vpp = 404 mV at approximately 10.0 kHz on both
channels. No software compensation was introduced at any point.

## Final REAL run (completely new workflow)

A completely new chat and workflow were used; no previous workflow or
scope was reused.

Request (exact):

> Measure the current STM32 output. Treat CH1 as Vin and CH2 as Vout.
> Measure frequency and Vpp and explain the result.

- prepare(): PASS
- `requested_frequency_hz`: null — the reviewed request declares roles
  but no expected frequency, and no implicit 100 Hz target was assumed
- canonical physical confirmation: supplied verbatim as a normal user
  chat message (not a Tool result)
- authority after confirmation: 2 ProbeSetupConfirmations (CH1, CH2)
  and 4 one-shot TrustedOperationScopes

## Authority and scope budgets

| Operation | Channel | Initial budget | Final budget |
| --- | --- | ---: | ---: |
| `hardware.measure_frequency` | CH1 | 1 | 0 |
| `hardware.measure_vpp` | CH1 | 1 | 0 |
| `hardware.measure_frequency` | CH2 | 1 | 0 |
| `hardware.measure_vpp` | CH2 | 1 | 0 |

No wildcard scope, no budget fallback, no fifth measurement.

## REAL hardware execution

Exact successful order:

1. CH1 frequency
2. CH1 Vpp
3. CH2 frequency
4. CH2 Vpp

Successful REAL measurement count: 4. Retries: 0. No waveform, PWM,
sweep, raw SCPI, or extra measurement occurred. Two pre-confirmation
`hardware_get_status` attempts were correctly rejected at the operation
scope gate (status is outside the four RE-001D scopes; no budget was
consumed and no measurement IPC occurred in those rejections).

Final measured values:

| Quantity | Value |
| --- | ---: |
| CH1 frequency | 10020.04 Hz |
| CH1 Vpp | 0.42 V |
| CH2 frequency | 10020.04 Hz |
| CH2 Vpp | 0.40 V |

The values are consistent with the manual post-correction oscilloscope
observation; the earlier ~10x discrepancy did not recur.

## Real provenance

All four canonical observations carried `source = "instrument"`
(`ObservationSource.INSTRUMENT`), mapped to
`TeachingEvidenceSource.INSTRUMENT`. Instrument evidence items: 4.
Simulated evidence items: 0. The publication used the real-instrument
evidence form ("Instrument measurement: ...").

## Deterministic analysis

- Vin frequency = Vout frequency = 10020.04 Hz
- gain ratio = 0.952380952381
- gain dB = -0.423785981399

`requested_frequency_hz` was null for this current-output request, so no
frequency-relative-deviation metric was computed, published, or implied.
No undeclared 100 Hz target appeared anywhere in the analysis or the
final publication. Explicit-target experiments (the RE-001B 100 Hz point)
retain the deviation metric by contract.

## Publication / grounding / egress

- `:49627 complete()`: PASS
- strict canonical mapper: PASS
- deterministic analyzer: PASS
- evidence construction: PASS
- trusted RE-001D publication: PASS (deterministic safe grounding
  fallback accepted; no model retry)
- final egress: SAFE

## Known non-blocking execution-liveness limitation

After valid confirmation, the model may occasionally select an
out-of-scope status tool and stop before executing the
already-authorized measurement plan. The authority layer correctly fails
closed and preserves the existing one-shot scopes. A later conversational
trigger can continue execution without re-authorizing Hardware.

In this run the duplicated canonical confirmation was an authority
no-op: it created no additional confirmation authority, no new scopes,
and no additional budgets; the existing four one-shot scopes remained
valid and were subsequently consumed by the exact four authorized
measurements.

## Final conclusion

INTERACTIVE WEB RE-001D REAL RIGOL EXECUTION PATH PROVEN
(bounded RE-001D path; single instrument; no broader hardware claims).
