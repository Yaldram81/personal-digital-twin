"""Command-line interface for the Personal Digital Twin.

Commands:
    init      Create a new encrypted vault (set passphrase).
    doctor    Check environment, config, and store health.
    serve     Run the API server (unlocks the vault first).

Usage: ``pdt <command> [options]``
"""

from __future__ import annotations

import getpass
import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from pdt.core.config import get_settings
from pdt.core.crypto import KDFParams, Vault

app = typer.Typer(
    name="pdt",
    help="Personal Digital Twin — a computational model of how you think.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def init(
    data_dir: Path = typer.Option(  # noqa: B008
        None,
        help="Override the data directory (default: .data).",
    ),
) -> None:
    """Create a new encrypted vault. Prompts for a passphrase."""
    settings = get_settings()
    if data_dir is not None:
        settings.data_dir = data_dir.resolve()

    if Vault.exists(settings.data_dir):
        console.print(
            f"[yellow]A vault already exists at {settings.data_dir}.[/yellow]\n"
            "Use a different --data-dir, or delete it first."
        )
        raise typer.Exit(code=1)

    passphrase = getpass.getpass("Choose a passphrase (>= 8 chars): ")
    confirm = getpass.getpass("Confirm passphrase: ")
    if passphrase != confirm:
        console.print("[red]Passphrases do not match.[/red]")
        raise typer.Exit(code=1)

    params = KDFParams(
        memory_kib=settings.kdf_memory_kib,
        time_cost=settings.kdf_time_cost,
        parallelism=settings.kdf_parallelism,
    )
    try:
        vault = Vault.init(settings.data_dir, passphrase, params)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    # Initialize the DuckDB schema right away so the store is ready.
    from pdt.memory.structured import DuckDBStructuredStore

    store = DuckDBStructuredStore(settings.duckdb_path, vault.key)
    store.init_schema()
    store.close()

    console.print(
        f"[green]Vault created at {settings.data_dir}.[/green]\n"
        f"Encrypted DuckDB store initialized: {settings.duckdb_path}\n"
        f"Vector store will live at: {settings.lancedb_path}\n"
        "\n[dim]Remember your passphrase — it cannot be recovered.[/dim]"
    )


@app.command()
def doctor() -> None:
    """Check environment, config, dependencies, and store health."""
    settings = get_settings()

    table = Table(title="pdt doctor", show_header=True, header_style="bold cyan")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")

    all_ok = True

    # Python version
    py_ok = sys.version_info >= (3, 11)
    all_ok &= py_ok
    table.add_row(
        "Python >= 3.11",
        "[green]ok[/green]" if py_ok else "[red]FAIL[/red]",
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    )

    # Data dir
    all_ok &= settings.data_dir.exists()
    table.add_row(
        "Data directory",
        "[green]ok[/green]" if settings.data_dir.exists() else "[yellow]missing[/yellow]",
        str(settings.data_dir),
    )

    # Vault
    vault_ok = Vault.exists(settings.data_dir)
    table.add_row(
        "Vault (passphrase salt)",
        "[green]ok[/green]" if vault_ok else "[yellow]not initialized[/yellow]",
        "run `pdt init` to create" if not vault_ok else "present",
    )

    # DuckDB store
    duckdb_ok = settings.duckdb_path.exists()
    table.add_row(
        "DuckDB store",
        "[green]ok[/green]" if duckdb_ok else "[yellow]not initialized[/yellow]",
        str(settings.duckdb_path),
    )

    # LanceDB store
    lance_ok = settings.lancedb_path.exists()
    table.add_row(
        "LanceDB vectors",
        "[green]ok[/green]" if lance_ok else "[yellow]not initialized[/yellow]",
        str(settings.lancedb_path),
    )

    # LLM provider / API key
    needs_key = settings.requires_api_key
    key_ok = bool(settings.llm_api_key) if needs_key else True
    all_ok &= key_ok
    table.add_row(
        f"LLM provider ({settings.llm_provider})",
        "[green]ok[/green]" if key_ok else "[red]missing key[/red]",
        settings.llm_model,
    )

    # KDF params sanity
    kdf_ok = settings.kdf_memory_kib >= 8192
    all_ok &= kdf_ok
    table.add_row(
        "Argon2id params",
        "[green]ok[/green]" if kdf_ok else "[red]too weak[/red]",
        f"mem={settings.kdf_memory_kib}KiB t={settings.kdf_time_cost} p={settings.kdf_parallelism}",
    )

    console.print(table)
    if not all_ok:
        console.print("\n[yellow]Some checks need attention.[/yellow]")
        raise typer.Exit(code=1)
    console.print("\n[green]All checks passed.[/green]")


@app.command()
def serve(
    host: str = typer.Option(None, help="Bind address."),  # noqa: B008
    port: int = typer.Option(None, help="Bind port."),  # noqa: B008
) -> None:
    """Run the API server. Unlocks the vault with a passphrase prompt."""
    import uvicorn

    settings = get_settings()
    if not Vault.exists(settings.data_dir):
        console.print("[red]No vault found. Run `pdt init` first.[/red]")
        raise typer.Exit(code=1)

    passphrase = getpass.getpass("Vault passphrase: ")
    params = KDFParams(
        memory_kib=settings.kdf_memory_kib,
        time_cost=settings.kdf_time_cost,
        parallelism=settings.kdf_parallelism,
    )
    try:
        vault = Vault.unlock(settings.data_dir, passphrase, params)
    except (ValueError, FileNotFoundError) as exc:
        console.print(f"[red]Unlock failed: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    # Attach an unlocked store to the app state.
    from pdt.api.app import get_state
    from pdt.memory.structured import DuckDBStructuredStore

    store = DuckDBStructuredStore(settings.duckdb_path, vault.key)
    store.init_schema()
    get_state().attach_store(store)

    bind_host = host or settings.api_host
    bind_port = port or settings.api_port
    console.print(f"[green]Serving PDT on http://{bind_host}:{bind_port}[/green]")
    uvicorn.run(
        "pdt.api.app:app",
        host=bind_host,
        port=bind_port,
        reload=False,
    )


@app.command()
def narrate(
    data_dir: Path = typer.Option(  # noqa: B008
        None,
        help="Override the data directory (default: .data).",
    ),
) -> None:
    """Interactively narrate a real decision (Phase 1 flow, CLI-native).

    Walks through the same structured-reflection prompts as the API's
    ``/narration/*`` endpoints, then extracts and stores a `ReasoningTrace`
    directly against the encrypted local store -- no running server required.
    """
    settings = get_settings()
    if data_dir is not None:
        settings.data_dir = data_dir.resolve()

    if not Vault.exists(settings.data_dir):
        console.print("[red]No vault found. Run `pdt init` first.[/red]")
        raise typer.Exit(code=1)

    passphrase = getpass.getpass("Vault passphrase: ")
    params = KDFParams(
        memory_kib=settings.kdf_memory_kib,
        time_cost=settings.kdf_time_cost,
        parallelism=settings.kdf_parallelism,
    )
    try:
        vault = Vault.unlock(settings.data_dir, passphrase, params)
    except (ValueError, FileNotFoundError) as exc:
        console.print(f"[red]Unlock failed: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    from pdt.core.llm.base import create_client
    from pdt.extraction.trace_extractor import build_extraction_event, extract_trace
    from pdt.inference.irl import fit as fit_irl
    from pdt.inference.irl import update as update_irl
    from pdt.memory.structured import DuckDBStructuredStore
    from pdt.ui.cli.narrate import NarrationSession

    store = DuckDBStructuredStore(settings.duckdb_path, vault.key)
    store.init_schema()
    llm = create_client(
        provider=settings.llm_provider,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        default_model=settings.llm_model,
        embedding_model=settings.embedding_model,
    )

    session = NarrationSession(session_id="cli-session")
    prompts: dict[str, str] = {
        "intake": "What decision were you facing?",
        "options": "What options did you seriously consider?",
        "factors": "What factors mattered most, and how did you weigh them?",
        "weighting": "How did those factors trade off against each other?",
        "counterfactual": "What almost changed your mind? (optional, Enter to skip)",
        "review": "Anything else worth adding? (optional, Enter to skip)",
    }
    console.print("[bold cyan]Let's narrate a real decision.[/bold cyan]\n")
    try:
        for field_name in ["intake", "options", "factors", "weighting", "counterfactual", "review"]:
            value = typer.prompt(prompts[field_name], default="", show_default=False)
            if value.strip():
                session.advance(field_name, value.strip())

        narration_text = session.to_narration_text()
        if not narration_text:
            console.print("[red]No narration content was provided.[/red]")
            raise typer.Exit(code=1)

        try:
            result = extract_trace(narration_text, llm)
        except ValueError as exc:
            console.print(f"[red]Extraction failed: {exc}[/red]")
            raise typer.Exit(code=1) from exc

        trace_json = result.trace.model_dump_json()
        row_id = store.insert_trace(trace_json)
        store.insert_extraction_event(
            row_id,
            json.dumps(build_extraction_event(result, narration_text)),
        )

        trace_history = store.list_traces(limit=10_000)
        current_fit = fit_irl(trace_history)
        updated_fit = update_irl(
            trace_history,
            current_theta=current_fit.theta,
            current_confidence=current_fit.confidence,
        )
        for dim, value in updated_fit.theta.items():
            store.insert_param(
                dim,
                value,
                updated_fit.confidence[dim],
                updated_fit.n_traces,
                "inferred",
                domain=result.trace.domain.value,
            )
    finally:
        store.close()

    console.print(f"\n[green]Trace stored:[/green] {row_id}")
    console.print(f"Domain: {result.trace.domain.value}")
    console.print(f"Chosen: {result.trace.chosen_option}")
    if result.support_flags:
        console.print(f"[yellow]Support flags: {', '.join(result.support_flags)}[/yellow]")


if __name__ == "__main__":
    app()
