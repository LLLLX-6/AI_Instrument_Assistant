from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from ai_instrument_assistant.application.services.engineering_evidence import (
    DeterministicEngineeringComparator,
    EngineeringEvidenceAssembler,
)
from ai_instrument_assistant.application.services.engineering_evidence_workflow import (
    EngineeringEvidenceWorkflow,
)
from ai_instrument_assistant.domain.engineering_evidence import (
    DesignEvidenceItem,
    DesignEvidenceKind,
    DesignEvidenceOrigin,
    EvidenceQuality,
    TargetProvenance,
    TeachingDiagnosisContext,
    VerificationState,
)
from tests.support.engineering_evidence_workflow import NOW, workflow_request


def reasoning_context(scenario: str = "pwm_no_tolerance") -> TeachingDiagnosisContext:
    request = workflow_request(scenario)
    result = EngineeringEvidenceWorkflow(
        assembler=EngineeringEvidenceAssembler(),
        comparator=DeterministicEngineeringComparator(),
    ).execute(request)
    design_fact = DesignEvidenceItem(
        evidence_id=UUID("dededede-dede-4ded-8ded-dededededede"),
        kind=DesignEvidenceKind.CONNECTIVITY_FACT,
        label="PWM_OUT selected network",
        value="PWM_OUT",
        unit=None,
        document=request.design_context.document,
        design_object=request.probe_target.design_object,
        verification_state=VerificationState.SNAPSHOT_BOUNDED,
        observed_at=NOW,
        origin=DesignEvidenceOrigin.DESIGN_DERIVED,
    )
    user_targets = tuple(
        replace(target, provenance=TargetProvenance.USER_PROVIDED)
        for target in result.teaching_context.design_targets
    )
    return replace(
        result.teaching_context,
        design_facts=(design_fact,),
        design_targets=user_targets,
        limitations=result.teaching_context.limitations
        + ("The JLCEDA snapshot is observation identity only.",),
    )


def degraded_reasoning_context() -> TeachingDiagnosisContext:
    context = reasoning_context()
    located = context.physical_observations[0]
    warning = "Recorded waveform quality is degraded."
    degraded = replace(
        located,
        item=replace(
            located.item,
            quality=EvidenceQuality.DEGRADED,
            warnings=(warning,),
        ),
    )
    return replace(
        context,
        physical_observations=(degraded,) + context.physical_observations[1:],
        quality="degraded",
        warnings=context.warnings + (warning,),
    )
