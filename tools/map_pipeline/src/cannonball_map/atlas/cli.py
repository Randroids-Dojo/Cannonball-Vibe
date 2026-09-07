from pathlib import Path

import typer

from cannonball_map.atlas.acquire import acquire_snapshot
from cannonball_map.atlas.audit import audit, verify_outputs
from cannonball_map.atlas.io import canonical, versioned
from cannonball_map.manifest import compute_sha256

app = typer.Typer(no_args_is_help=True, help="Acquire approved atlas sources and audit coverage.")


@app.command("lock")
def lock_command(job: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    """Explicitly pin edited job inputs; does not approve sources or change corridor scope."""
    try:
        document = versioned(job)
        for key in ("catalog", "profiles", "route_selection", "scope"):
            ref = document[key]
            ref["sha256"] = compute_sha256((job.parent / ref["path"]).resolve())
        scope = versioned((job.parent / document["scope"]["path"]).resolve())
        if scope["route_selection_sha256"] != document["route_selection"]["sha256"]:
            raise ValueError("Review/update scope against the changed route policy before locking")
        for ref in document.get("artifact_manifests", []):
            ref["sha256"] = compute_sha256((job.parent / ref["path"]).resolve())
        temporary = job.with_suffix(job.suffix + ".tmp")
        temporary.write_bytes(canonical(document))
        temporary.replace(job)
    except (ValueError, TypeError, KeyError, OSError) as error:
        failure(job.parent, error)
    typer.echo("atlas-job-inputs-locked; source admission and coverage still require audit")


def failure(output: Path, error: Exception) -> None:
    payload = {
        "schema_version": 1,
        "status": "failed",
        "code": getattr(error, "code", "invalid_input"),
        "message": str(error),
    }
    # Print structured errors even when an invalid output path cannot be written safely.
    typer.echo(canonical(payload).decode().strip())
    raise typer.Exit(1) from error


@app.command("audit")
def audit_command(
    job: Path = typer.Argument(..., exists=True, dir_okay=False),
    output: Path = typer.Option(Path("reports/atlas/audit")),
) -> None:
    """Normalize locked inputs and emit explicit gaps; exit 2 means incomplete coverage."""
    try:
        report = audit(job, output)
        verify_outputs(output)
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as error:
        failure(output, error)
    typer.echo(
        canonical(
            {
                "status": report["status"],
                "counts": report["counts"],
                "report": str(output / "report.md"),
            }
        )
        .decode()
        .strip()
    )
    if report["status"] != "complete":
        raise typer.Exit(2)


@app.command("acquire")
def acquire_command(
    profile_id: str,
    output: Path = typer.Option(...),
    profiles: Path = typer.Option(Path("data/atlas/datasets.v1.json"), exists=True),
    catalog: Path = typer.Option(Path("data/sources/catalog.json"), exists=True),
    where: str | None = None,
    observed_on: str | None = None,
) -> None:
    """Acquire a bounded, approved source into a checksummed artifact bundle."""
    try:
        matches = [p for p in versioned(profiles)["datasets"] if p["id"] == profile_id]
        if len(matches) != 1:
            raise ValueError("Profile ID must identify exactly one dataset")
        result = acquire_snapshot(matches[0], catalog, output, where=where, observed_on=observed_on)
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as error:
        failure(output, error)
    typer.echo(canonical(result).decode().strip())


@app.command("verify")
def verify_command(output: Path) -> None:
    """Check all audit output bytes against their manifest."""
    try:
        verify_outputs(output)
    except (ValueError, TypeError, KeyError, OSError) as error:
        failure(output, error)
    typer.echo("atlas-output-hashes-ok")
