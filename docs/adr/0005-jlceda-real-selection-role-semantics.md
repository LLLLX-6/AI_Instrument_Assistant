# ADR 0005: JLCEDA Real Selection Role Semantics

Status: PROPOSED — Phase 8B.2 remains blocked pending architecture review.

Date: 2026-09-10

## Context

A bounded real JLCEDA diagnostic observed two provider-selected schematic
objects after the user selected a PWM_OUT wire segment: one `Wire` and one
`Component`. The approved adapter also derived exactly one `Net` from the
Wire's observed network name. The Phase 8B.2 projection failed at selection
cardinality with `multiple_selected_objects`.

This observation proves the returned shape for one run. It does not establish
that the Component is primary, auxiliary, owned by the Wire, UI-attached, or
otherwise safe to ignore.

## Sources Reviewed

Repository sources:

- frozen `@jlceda/pro-api-types` 0.4.14;
- SDK compatibility declaration 1.6.17;
- extension engine compatibility `^3.2.0`;
- Phase 5 selection and highlight findings;
- current adapter, dispatcher, AIA-JLCEDA v1 schemas, Domain models, and tests.

Official JLCEDA documentation inspected on 2026-09-10:

- `SCH_SelectControl`:
  https://prodocs.lceda.cn/cn/api/reference/pro-api.sch_selectcontrol.html
- `getAllSelectedPrimitives_PrimitiveId`:
  https://prodocs.lceda.cn/cn/api/reference/pro-api.sch_selectcontrol.getallselectedprimitives_primitiveid.html
- `getAllSelectedPrimitives`:
  https://prodocs.lceda.cn/cn/api/reference/pro-api.sch_selectcontrol.getallselectedprimitives.html
- `ISCH_PrimitiveWire`:
  https://prodocs.lceda.cn/cn/api/reference/pro-api.isch_primitivewire.html
- `ISCH_PrimitiveWire.getState_Net`:
  https://prodocs.lceda.cn/cn/api/reference/pro-api.isch_primitivewire.getstate_net.html
- `SCH_Net.getNet`:
  https://prodocs.lceda.cn/cn/api/reference/pro-api.sch_net.getnet.html
- API stability policy:
  https://prodocs.lceda.cn/cn/api/guide/stability.html

The live official documentation is not a versioned contract for the pinned
0.4.14 types. Newer `SCH_Net.getNet` is BETA and documented as added in EDA
4.2, so it cannot be assumed available to the extension's current `^3.2.0`
compatibility boundary.

## Findings

The documented schematic selection APIs return arrays containing all selected
primitive IDs or all selected primitive objects. They expose no documented:

- primary selected object;
- selection role;
- semantic ordering guarantee;
- auxiliary or UI-attached marker;
- Wire-to-Component owner or parent relationship;
- exact last-clicked primitive.

`SCH_Event.addMouseEventListener` reports only an event type and therefore does
not provide an exact primitive identity. `getCurrentMousePosition` plus geometry
or hit-testing would be heuristic and is outside the approved selection
contract. `doSelectPrimitives` changes selection; it cannot discover what the
user originally selected.

A selected Wire can be retrieved by its ID and can expose an observed network
name through `getState_Net`. This is already the approved bounded path. The
official documentation warns that the Wire network name can be stale while
global multi-page network state refreshes. The API does not return a selected
Net object directly. Newer `SCH_Net.getNet(name)` still requires a name and
does not supply selection-role evidence.

No official documentation reviewed here describes an extra Component as a
stable consequence of selecting a Wire. One real observation must not be
promoted to provider semantics.

## Decision

Recommend **Option D — provider cannot currently expose sufficient documented
role evidence** within the frozen boundary.

The following invariant remains frozen:

```text
Wire
+ Component
+ no documented primary/role/relationship evidence
-> ambiguous_selection
```

This remains true even when exactly one derived Net exists. The display name
`PWM_OUT`, selection array order, and uniqueness of the derived Net cannot
resolve the selection-role ambiguity.

Phase 5's approved `selected Wire -> separately derived Net` behavior remains
valid for a single provider-selected Wire. Wire-to-Net expansion is not the
cause of the real failure and is not weakened or removed.

## Schema and Domain Consequences

No schema or Domain change is authorized by this proposal.

The existing `DesignSelection.primary_object` field could carry a
provider-observed primary object without a new wire field, but JLCEDA currently
provides no documented value for it, so the adapter must continue sending
`null`. A relationship-aware solution would require provider evidence first;
only then should a provider-neutral relationship model and versioned schema
change be proposed. No ad-hoc JSON extension is allowed.

`ProbeTarget` continues to require one exact Net `DesignObjectRef`. A single
selected Wire plus one derived Net may produce it. Wire plus an unexplained
Component may not discard the Component and may not produce an authoritative
ProbeTarget.

## Proposed Tests for a Future Change

The recorded synthetic fixture freezes the current result:

```text
Wire + Component + one derived Net + no roles -> ambiguous_selection
```

If a future documented provider contract supplies role evidence, begin with
Red tests proving:

1. explicit provider-observed primary Wire plus verified related auxiliary
   Component preserves both references and resolves the derived Net;
2. the same objects without role/relationship evidence remain ambiguous;
3. order reversal cannot change the outcome;
4. name equality cannot create role evidence;
5. old readers reject or safely ignore only according to an approved versioned
   compatibility policy.

## Risks and Follow-up

The selection methods are BETA, and official stability guidance allows them to
change. Encoding observed array order or incidental UI behavior would be
fragile and unsafe. Phase 8B.2 therefore remains:

```text
IMPLEMENTATION/AUTOMATED TESTS PASS
REAL JLCEDA VALIDATION BLOCKED
```

A bounded UX workaround may ask the user to explicitly choose among the
provider-returned objects, but that would be a new trusted user decision and a
separate architecture proposal—not an inferred primary selection.
