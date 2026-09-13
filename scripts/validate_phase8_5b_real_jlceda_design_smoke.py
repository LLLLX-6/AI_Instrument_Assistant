from __future__ import annotations

import asyncio
import json
from pathlib import Path

from ai_instrument_assistant.application.interactive import WorkflowState
from ai_instrument_assistant.bootstrap.interactive import (
    compose_jlceda_interactive_host,
)
from ai_instrument_assistant.integrations.interactive import InteractiveEndpointConfig


ROOT = Path(__file__).resolve().parents[1]
INTERACTIVE_SECRET = ROOT / ".aia-secrets" / "phase8_5b0-interactive-psk.txt"
PROVIDER_SECRET = ROOT / ".aia-secrets" / "jlceda-psk.txt"


async def main() -> None:
    if not INTERACTIVE_SECRET.is_file() or not PROVIDER_SECRET.is_file():
        raise SystemExit("required local credential reference is unavailable")

    runtime = compose_jlceda_interactive_host(
        repository_root=ROOT,
        interactive_config=InteractiveEndpointConfig(
            port=49626,
            credential_reference=INTERACTIVE_SECRET,
        ),
        provider_credential_reference=PROVIDER_SECRET,
    )
    workflow = runtime.host.start_workflow(
        "Phase 8.5B JLCEDA design smoke",
        "phase8_5b-real-jlceda-design-smoke",
    )
    workflow = runtime.host.transition(
        workflow.workflow_id,
        workflow.revision,
        WorkflowState.OBSERVING_DESIGN,
    )

    observations = 0
    prior_observation: tuple[str | None, str | None] = (None, None)
    prior_state: tuple[int, str] | None = None
    await runtime.start()
    print(json.dumps({
        "status": "READY",
        "provider_listener": 49624,
        "interactive_listener": 49626,
        "hardware_listener": "INACTIVE",
        "production_design_selection_issuer": True,
    }, sort_keys=True), flush=True)
    try:
        while True:
            current = runtime.host.get_workflow(workflow.workflow_id)
            binding_time = (
                None
                if current.design_selection_binding is None
                else current.design_selection_binding.selection_observed_at.isoformat()
            )
            observation_key = (current.design_observation_ref, binding_time)
            if current.design_observation_ref is not None and observation_key != prior_observation:
                observations += 1
                prior_observation = observation_key
            state_key = (current.revision, current.state.value)
            if state_key != prior_state:
                prior_state = state_key
                print(json.dumps({
                    "event": "WORKFLOW_STATE",
                    "revision": current.revision,
                    "state": current.state.value,
                    "host_fresh_observations": observations,
                    "typed_candidate_binding": current.design_selection_binding is not None,
                    "candidate_count": (
                        0
                        if current.design_selection_binding is None
                        else len(current.design_selection_binding.presented_candidates)
                    ),
                    "trusted_design_decision": current.trusted_design_selection is not None,
                    "probe_target": (
                        None
                        if current.probe_target is None
                        else current.probe_target.design_object.display_name
                    ),
                    "operation_scope": current.operation_scope_ref is not None,
                    "physical_confirmation": current.physical_confirmation_ref is not None,
                }, sort_keys=True), flush=True)
            await asyncio.sleep(0.2)
    finally:
        audit_actions = tuple(item.action for item in runtime.host.audit_records)
        interactive_counters = runtime.interactive_server.counters
        await runtime.stop()
        print(json.dumps({
            "status": "STOPPED",
            "interactive_connections": sum(
                action == "frontend_connected:jlceda" for action in audit_actions
            ),
            "interactive_disconnects": sum(
                action == "frontend_disconnected:jlceda" for action in audit_actions
            ),
            "design_selection_challenges": sum(
                action == "challenge_issued:DESIGN_SELECTION" for action in audit_actions
            ),
            "valid_design_selection_answers": sum(
                action == "challenge_answer_validated:design_selection"
                for action in audit_actions
            ),
            "trusted_design_decisions": sum(
                action == "trusted_design_decision_issued" for action in audit_actions
            ),
            "cancellations": sum(
                action == "workflow_cancelled" for action in audit_actions
            ),
            "host_fresh_observations": observations,
            "interactive_initial_snapshots_sent": interactive_counters.initial_snapshots_sent,
            "interactive_snapshot_requests_received": interactive_counters.snapshot_requests_received,
            "interactive_snapshot_replies_sent": interactive_counters.snapshot_replies_sent,
            "interactive_commands_received": interactive_counters.commands_received,
            "interactive_command_dispatches": interactive_counters.command_dispatches,
            "interactive_command_failures": interactive_counters.command_failures,
            "hardware": 0,
            "visa": 0,
            "scpi": 0,
            "deepseek": 0,
        }, sort_keys=True), flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        print(json.dumps({
            "status": "NOT_PASS",
            "reason": "production_composition_start_failed",
            "external_execution_started": False,
        }, sort_keys=True), flush=True)
        raise SystemExit(1) from None
