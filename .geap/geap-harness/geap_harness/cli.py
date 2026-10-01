"""``geap-harness`` CLI: gate | review | publish (PLATFORM_CONTRACTS.md §6)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import typer

from . import __version__
from .backends import BACKENDS, BackendError
from .cache import canonical_json
from .gate import read_verdict, run_gate, verdict_json, write_verdict
from .gitdiff import GitError
from .inputs import DEFAULT_SKILLS
from .publish import publish as do_publish

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="GEAP deterministic AI gate — Antigravity reviewer proposes, policy decides.")

EXIT_PASS, EXIT_FAIL, EXIT_ERROR, EXIT_NOT_REPRODUCIBLE = 0, 1, 2, 3


def _backend_default() -> str:
    return os.environ.get("GEAP_GATE_BACKEND") or "offline"


def _check_backend(b: str) -> str:
    if b not in BACKENDS:
        raise typer.BadParameter(f"must be one of {', '.join(BACKENDS)}")
    return b


RepoDir = typer.Option(Path("."), "--repo-dir", help="Git repository to review.")
Base = typer.Option(..., "--base", help="Base commit (e.g. PR base sha).")
Head = typer.Option("HEAD", "--head", help="Head commit.")
BackendOpt = typer.Option(None, "--backend", help="sdk | cli | offline (default $GEAP_GATE_BACKEND or offline).")
ModelOpt = typer.Option(None, "--model", envvar="GEAP_HARNESS_REVIEW_MODEL", help="Pinned reviewer model id.")
SkillsDir = typer.Option(None, "--skills-dir", help="Directory containing skill folders (default: vendored).")
SkillOpt = typer.Option(None, "--skill", help="Skill name (repeatable). Default: code-review, secure-coding, unit-test.")
CacheDir = typer.Option(None, "--cache-dir", help="Cache dir (default <repo-dir>/.geap/cache).")
CacheUri = typer.Option(None, "--cache-uri", envvar="GEAP_GATE_CACHE_URI", help="Optional gs:// cache mirror.")
NoCache = typer.Option(False, "--no-cache", help="Bypass the verdict cache.")
Timeout = typer.Option(600, "--timeout", help="Reviewer timeout (s).")


def _err(msg: str) -> None:
    typer.echo(f"geap-harness: error: {msg}", err=True)


@app.command()
def gate(
    repo_dir: Path = RepoDir,
    base: str = Base,
    head: str = Head,
    policy: Optional[Path] = typer.Option(None, "--policy", help="Policy YAML (default <repo-dir>/.geap/policy.yaml if present)."),
    out: Path = typer.Option(Path("gate.json"), "--out", help="Verdict JSON output path."),
    backend: Optional[str] = BackendOpt,
    model: Optional[str] = ModelOpt,
    replay: bool = typer.Option(False, "--replay", help="Recompute and assert the verdict is identical."),
    junit: Optional[Path] = typer.Option(None, "--junit", help="JUnit XML for the tests_passed rule."),
    skills_dir: Optional[Path] = SkillsDir,
    skill: Optional[list[str]] = SkillOpt,
    cache_dir: Optional[Path] = CacheDir,
    cache_uri: Optional[str] = CacheUri,
    no_cache: bool = NoCache,
    timeout: int = Timeout,
    exit_zero: bool = typer.Option(False, "--exit-zero", help="Always exit 0 on a computed verdict (CI publishes later)."),
) -> None:
    """Review base..head and decide pass/fail with the deterministic policy. Exit 0 pass, 1 fail, 2 error, 3 not reproducible."""
    b = _check_backend(backend or _backend_default())
    pol = policy
    if pol is None and (repo_dir / ".geap" / "policy.yaml").is_file():
        pol = repo_dir / ".geap" / "policy.yaml"
    try:
        run = run_gate(repo_dir=repo_dir, base=base, head=head, policy_path=pol, backend=b, model=model,
                       skills_dir=skills_dir, skills=tuple(skill or DEFAULT_SKILLS), cache_dir=cache_dir,
                       cache_uri=cache_uri, use_cache=not no_cache, replay=replay, junit=junit, timeout_s=timeout,
                       now=os.environ.get("GEAP_GATE_NOW"))
    except (BackendError, GitError, FileNotFoundError, ValueError) as exc:
        _err(str(exc))
        raise typer.Exit(EXIT_ERROR)
    write_verdict(run.verdict, out)
    v = run.verdict
    typer.echo(f"GEAP AI Gate: {v.verdict.upper()}  findings={len(v.findings)}  backend={b}  model={v.model}  "
               f"cache={'hit' if run.cache_hit else 'miss'}  reproducible={str(v.reproducible).lower()}  -> {out}")
    for r in v.rules:
        typer.echo(f"  [{'PASS' if r.passed else 'FAIL'}] {r.id}: {r.detail}")
    if replay and not run.replay_ok:
        _err("replay produced a different verdict (not reproducible)")
        raise typer.Exit(EXIT_NOT_REPRODUCIBLE)
    if exit_zero:
        raise typer.Exit(EXIT_PASS)
    raise typer.Exit(EXIT_PASS if v.verdict == "pass" else EXIT_FAIL)


@app.command()
def review(
    repo_dir: Path = RepoDir,
    base: str = Base,
    head: str = Head,
    out: Optional[Path] = typer.Option(None, "--out", help="Write findings JSON here (default stdout)."),
    backend: Optional[str] = BackendOpt,
    model: Optional[str] = ModelOpt,
    skills_dir: Optional[Path] = SkillsDir,
    skill: Optional[list[str]] = SkillOpt,
    cache_dir: Optional[Path] = CacheDir,
    cache_uri: Optional[str] = CacheUri,
    no_cache: bool = NoCache,
    timeout: int = Timeout,
) -> None:
    """Run the reviewer only (no policy) and emit findings JSON."""
    b = _check_backend(backend or _backend_default())
    try:
        run = run_gate(repo_dir=repo_dir, base=base, head=head, use_policy=False, backend=b, model=model,
                       skills_dir=skills_dir, skills=tuple(skill or DEFAULT_SKILLS), cache_dir=cache_dir,
                       cache_uri=cache_uri, use_cache=not no_cache, timeout_s=timeout,
                       now=os.environ.get("GEAP_GATE_NOW"))
    except (BackendError, GitError, FileNotFoundError, ValueError) as exc:
        _err(str(exc))
        raise typer.Exit(EXIT_ERROR)
    payload = {
        "summary": run.review.summary,
        "findings": [f.model_dump() for f in run.verdict.findings],
        "backend": b, "model": run.verdict.model, "cache_key": run.verdict.cache_key,
        "skill_shas": run.verdict.skill_shas, "prompt_hash": run.verdict.prompt_hash,
        "usage": run.review.usage,
    }
    text = canonical_json(payload)
    if out:
        Path(out).write_text(text, encoding="utf-8")
        typer.echo(f"{len(payload['findings'])} finding(s) -> {out}")
    else:
        sys.stdout.write(text)


@app.command()
def publish(
    gate_file: Path = typer.Option(Path("gate.json"), "--gate", help="Verdict JSON from `gate`."),
    sha: Optional[str] = typer.Option(None, "--sha", help="Head sha for the check run (default from event)."),
    pr: Optional[int] = typer.Option(None, "--pr", help="PR number (default from event)."),
) -> None:
    """Publish the verdict as the 'GEAP AI Gate' check run + one upserted PR comment (no-op outside Actions)."""
    try:
        v = read_verdict(gate_file)
    except (OSError, ValueError) as exc:
        _err(f"cannot read {gate_file}: {exc}")
        raise typer.Exit(EXIT_ERROR)
    try:
        res = do_publish(v, sha=sha, pr_number=pr)
    except Exception as exc:  # noqa: BLE001 - surface HTTP errors without a traceback
        _err(f"publish failed: {exc}")
        raise typer.Exit(EXIT_ERROR)
    typer.echo(res.message)


@app.command()
def version() -> None:
    """Print the geap-harness version."""
    typer.echo(__version__)


@app.command("show")
def show(gate_file: Path = typer.Option(Path("gate.json"), "--gate")) -> None:
    """Pretty-print a verdict file (canonical JSON)."""
    sys.stdout.write(verdict_json(read_verdict(gate_file)))


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
