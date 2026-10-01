"""Antigravity SDK backend: a read-only, sandboxed, budget-capped reviewer.

API names verified against the installed ``google-antigravity`` (0.1.20):
``LocalAgentConfig(response_schema=, policies=, workspaces=, skills_paths=,
capabilities=, budget_config=, model=, vertex=, project=, location=, api_key=)``,
``types.BudgetConfig``, ``types.CapabilitiesConfig(disabled_tools=, enable_subagents=,
run_command_config=RunCommandConfig(enable_sandbox=True))``,
``hooks.policy.{deny, allow}``, ``ModelTarget`` + ``VertexEndpoint`` /
``GeminiAPIEndpoint`` + ``GeminiModelOptions(thinking_level=)``,
``ChatResponse.structured_output()`` / ``.usage_metadata`` / ``.stop_reason``.

The SDK exposes no temperature/seed knob. Determinism is obtained around the
model instead: pinned model id + thinking level, fixed prompt template, fixed
skills (SHA), JSON ``response_schema``, no side-effect tools, and the verdict
cache / ``--replay`` check in ``gate.py`` (ADR-009).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from ..gitdiff import DiffInfo
from ..inputs import Skill
from ..models import FindingList, ReviewResult, sort_findings
from . import BackendError

SYSTEM_INSTRUCTIONS = (
    "You are CI-GATE, the GEAP read-only code review gate. You never modify files or run commands. "
    "You answer only with JSON that matches the provided schema."
)

# Tools that could cause side effects are both disabled (capabilities) and denied (policy): defence in depth.
DENIED_TOOLS = ("run_command", "create_file", "edit_file", "generate_image", "search_web", "read_url_content",
                "start_subagent", "schedule", "ask_question")


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "y")


def build_config(repo_dir: Path, skills: list[Skill], model: str | None):
    try:
        from google.antigravity import LocalAgentConfig, types
        from google.antigravity.hooks import policy
        from google.antigravity.models import GeminiAPIEndpoint, GeminiModelOptions, ModelTarget, ModelType, \
            ThinkingLevel, VertexEndpoint
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise BackendError("backend 'sdk' needs the optional extra: pip install 'geap-harness[sdk]'") from exc

    use_vertex = _truthy(os.environ.get("GOOGLE_GENAI_USE_VERTEXAI")) and bool(os.environ.get("GOOGLE_CLOUD_PROJECT"))
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GEAP_HARNESS_LOCATION", "global")
    api_key = None if use_vertex else os.environ.get("GEMINI_API_KEY")
    if not use_vertex and not api_key:
        raise BackendError("sdk backend: set GOOGLE_GENAI_USE_VERTEXAI=TRUE + GOOGLE_CLOUD_PROJECT (ADC/WIF) "
                           "or GEMINI_API_KEY")

    level = getattr(ThinkingLevel, os.environ.get("GEAP_HARNESS_THINKING_LEVEL", "LOW").upper(), ThinkingLevel.LOW)
    # thinking_level is Gemini 3+ only; Vertex returns 400 "thinking_level is not supported" for 2.x.
    supports_level = bool(model) and model.startswith("gemini-3")
    options = GeminiModelOptions(thinking_level=level) if supports_level else GeminiModelOptions()
    model_kwargs: dict = {}
    if model and not model.endswith("-default"):
        endpoint = (VertexEndpoint(project=project, location=location, options=options) if use_vertex
                    else GeminiAPIEndpoint(api_key=api_key, options=options))
        model_kwargs["model"] = ModelTarget(name=model, types=[ModelType.TEXT], endpoint=endpoint)
    else:
        model_kwargs.update(vertex=use_vertex or None, project=project if use_vertex else None,
                            location=location if use_vertex else None, api_key=api_key)

    policies = [policy.deny(t, name=f"ci_gate_deny_{t}", reason="CI gate is read-only") for t in DENIED_TOOLS]
    policies.append(policy.allow("view_file", name="ci_gate_allow_view"))

    return LocalAgentConfig(
        system_instructions=SYSTEM_INSTRUCTIONS,
        workspaces=[str(repo_dir)],  # auto-prepends policy.workspace_only
        skills_paths=[str(s.path) for s in skills],
        response_schema=FindingList,
        policies=policies,
        capabilities=types.CapabilitiesConfig(
            enable_subagents=False,
            disabled_tools=[
                types.BuiltinTools.RUN_COMMAND, types.BuiltinTools.CREATE_FILE, types.BuiltinTools.EDIT_FILE,
                types.BuiltinTools.GENERATE_IMAGE, types.BuiltinTools.SEARCH_WEB,
                types.BuiltinTools.READ_URL_CONTENT, types.BuiltinTools.SCHEDULE,
                types.BuiltinTools.ASK_QUESTION, types.BuiltinTools.START_SUBAGENT,
            ],
            run_command_config=types.RunCommandConfig(enable_sandbox=True),
        ),
        budget_config=types.BudgetConfig(
            max_model_calls=int(os.environ.get("GEAP_GATE_MAX_MODEL_CALLS", "12")),
            max_tool_calls=int(os.environ.get("GEAP_GATE_MAX_TOOL_CALLS", "40")),
            max_total_tokens=int(os.environ.get("GEAP_GATE_MAX_TOTAL_TOKENS", "400000")),
        ),
        **model_kwargs,
    )


async def _run(cfg, prompt: str) -> tuple[dict | None, dict, str | None, str]:
    from google.antigravity import Agent

    async with Agent(cfg) as agent:
        resp = await agent.chat(prompt)
        data = await resp.structured_output()
        text = "" if data is not None else (await resp.text())
        um = resp.usage_metadata
        usage = {
            "prompt_tokens": getattr(um, "prompt_token_count", None),
            "output_tokens": getattr(um, "candidates_token_count", None),
            "thoughts_tokens": getattr(um, "thoughts_token_count", None),
            "total_tokens": getattr(um, "total_token_count", None),
        } if um is not None else {}
        stop = getattr(resp.stop_reason, "name", None) if resp.stop_reason is not None else None
        return data, usage, stop, text


def review(repo_dir: Path, diff: DiffInfo, *, prompt: str, skills: list[Skill], model: str,
           timeout_s: int = 600) -> ReviewResult:
    cfg = build_config(repo_dir, skills, model)
    try:
        data, usage, stop, text = asyncio.run(asyncio.wait_for(_run(cfg, prompt), timeout=timeout_s))
    except TimeoutError as exc:
        raise BackendError(f"sdk reviewer timed out after {timeout_s}s") from exc
    if data is None:
        raise BackendError(f"sdk reviewer returned no structured output (stop_reason={stop}): {text[:300]}")
    fl = FindingList.model_validate(data)
    usage = {**usage, "stop_reason": stop, "model": model}
    return ReviewResult(backend="sdk", model=model, summary=fl.summary,
                        findings=sort_findings(fl.findings), usage=usage)
