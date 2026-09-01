import asyncio
import json
import typer
from typing import Optional, List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from spider.core.factory import create_spider_service
from spider.models.enums import ObservableType, ProviderState
from spider.models.budget import ExecutionBudget
from spider.models.classifier import TargetClassifier

app = typer.Typer(
    name="spider",
    help="SPIDER — Evidence-First OSINT Orchestration Engine for Windows",
    no_args_is_help=True
)
case_app = typer.Typer(help="Manage investigation cases")
provider_app = typer.Typer(help="Inspect provider status and health")
app.add_typer(case_app, name="case")
app.add_typer(provider_app, name="provider")

console = Console()

def infer_observable_type(target: str) -> ObservableType:
    result = TargetClassifier.classify(target)
    return result.detected_type

@app.command()
def doctor(json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON")):
    """Run comprehensive system, database, and provider health diagnostics."""
    async def _run():
        service = create_spider_service(mode="production")
        await service.start()
        try:
            diag = await service.doctor()
            if json_output:
                console.print(json.dumps(diag, indent=2))
            else:
                console.print(Panel.fit("[bold green]SPIDER System Health & Reality Report[/bold green]", border_style="green"))
                table = Table(title="Provider Diagnostics & Reality Verification")
                table.add_column("Provider ID", style="cyan")
                table.add_column("Status", style="bold")
                table.add_column("Version", style="magenta")
                table.add_column("Latency (ms)", justify="right")
                table.add_column("Message", style="white")

                for pid, info in diag["providers"].items():
                    state = info.get("state", "UNKNOWN")
                    color = "green" if state == "READY" else ("yellow" if "LIMITED" in state or "DEGRADED" in state or "MISSING_CREDENTIAL" in state else "red")
                    ver = info.get("provider_version") or "N/A"
                    lat = f"{info.get('latency_ms', 0):.1f}" if info.get("latency_ms") else "-"
                    table.add_row(pid, f"[{color}]{state}[/{color}]", ver, lat, info.get("message", "OK"))
                console.print(table)
        finally:
            await service.stop()
    asyncio.run(_run())

@app.command()
def investigate(
    target: str = typer.Argument(..., help="Target value (domain, IP, username, email, etc.)"),
    case_name: Optional[str] = typer.Option(None, "--name", "-n", help="Case name"),
    authorized: bool = typer.Option(False, "--authorized", "-a", help="Explicit authorized scope flag"),
    max_depth: int = typer.Option(2, "--max-depth", "-d", help="Maximum recursion depth"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Policy profile name"),
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON")
):
    """Execute an end-to-end evidence-first OSINT investigation on a target."""
    async def _run():
        service = create_spider_service(mode="production")
        await service.start()
        try:
            name = case_name or f"Investigation: {target}"
            case_res = await service.create_case(name=name, tags=["cli", "investigation"])
            case_id = case_res["id"]

            classification = TargetClassifier.classify(target)
            obs_type = classification.detected_type
            await service.add_target(case_id, target, obs_type, scope_authorized=authorized)

            budget = ExecutionBudget(max_depth=max_depth)
            run_res = await service.investigate(case_id, budget=budget, policy_profile=profile)

            entities = await service.get_case_entities(case_id)
            assertions = await service.get_case_assertions(case_id)

            if json_output:
                res = {
                    "case_id": case_id,
                    "target": target,
                    "type": obs_type.value,
                    "run_result": run_res,
                    "entities": entities,
                    "assertions": assertions
                }
                console.print(json.dumps(res, indent=2))
            else:
                summary_text = (
                    f"Case ID: {case_id}\n"
                    f"Target: {target} ({obs_type.value})\n"
                    f"Status: {run_res['status']}\n"
                    f"Tasks Run: {run_res['tasks_executed']} | Observations: {run_res['observations_collected']}\n"
                    f"Entities Discovered: {len(entities)} | Assertions: {len(assertions)}"
                )
                console.print(Panel(summary_text, title="Investigation Results", border_style="cyan"))
                
                t_ent = Table(title="Top Discovered Entities")
                t_ent.add_column("Type", style="magenta")
                t_ent.add_column("Canonical Name", style="bold green")
                t_ent.add_column("Observations", justify="right")
                t_ent.add_column("First Seen", style="dim")
                for e in entities[:20]:
                    t_ent.add_row(e["type"], e["canonical_name"], str(e["observation_count"]), e["first_seen"][:19])
                console.print(t_ent)

                t_asrt = Table(title="Knowledge Graph Assertions")
                t_asrt.add_column("Assertion ID", style="dim")
                t_asrt.add_column("Relationship Type", style="yellow")
                t_asrt.add_column("Confidence", justify="right")
                t_asrt.add_column("Sources", style="cyan")
                for a in assertions[:20]:
                    t_asrt.add_row(a["id"][:8], a["assertion_type"], f"{a['confidence']:.2f}", ",".join(a["source_families"] or ["-"]))
                console.print(t_asrt)
        finally:
            await service.stop()
    asyncio.run(_run())

@app.command()
def explain(
    assertion_id: str = typer.Argument(..., help="Assertion ID to explain"),
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON")
):
    """Trace an assertion back to its underlying evidence, independent source families, and raw artifacts."""
    async def _run():
        service = create_spider_service(mode="production")
        await service.start()
        try:
            explanation = await service.explain_assertion(assertion_id)
            if not explanation:
                console.print(f"[bold red]Assertion {assertion_id} not found.[/bold red]")
                raise typer.Exit(1)

            if json_output:
                console.print(json.dumps(explanation, indent=2))
            else:
                src_name = explanation["source_entity"]["canonical_name"]
                tgt_name = explanation["target_entity"]["canonical_name"]
                asrt_type = explanation["assertion_type"]
                conf = explanation["confidence"]
                families = ",".join(explanation["source_families"])
                resolver_ver = explanation["resolver_version"]
                inf_rule = explanation["inference_rule"]

                info_text = f"Assertion: {src_name} -> {asrt_type} -> {tgt_name}\nConfidence: {conf:.2f} | Sources: {families}\nResolver Version: {resolver_ver} | Inference Rule: {inf_rule}"
                console.print(Panel.fit(info_text, title=f"Assertion Explanation: {assertion_id}", border_style="yellow"))

                t_ev = Table(title="Evidence Trail")
                t_ev.add_column("Evidence ID", style="dim")
                t_ev.add_column("Provider", style="magenta")
                t_ev.add_column("Source Family", style="cyan")
                t_ev.add_column("Raw Artifact SHA-256", style="dim")
                t_ev.add_column("Timestamp", style="dim")

                for ev in explanation["evidence"]:
                    t_ev.add_row(
                        ev["evidence_id"][:8],
                        ev["provider_id"],
                        ev["upstream_family"],
                        ev["raw_artifact_sha256"] or "N/A",
                        ev["timestamp"][:19] if ev["timestamp"] else "N/A"
                    )
                console.print(t_ev)
        finally:
            await service.stop()
    asyncio.run(_run())

@app.command()
def rebuild(
    case_id: str = typer.Argument(..., help="Case ID to rebuild"),
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON")
):
    """Rebuild the materialized Knowledge Graph from the append-only observation log without network queries."""
    async def _run():
        service = create_spider_service(mode="production")
        await service.start()
        try:
            res = await service.rebuild_case(case_id)
            if json_output:
                console.print(json.dumps(res, indent=2))
            else:
                rebuild_info = f"Status: {res['status']}\nObservations Processed: {res.get('observations_processed', 0)}\nEntities Rebuilt: {res.get('entities_rebuilt', 0)}\nAssertions Rebuilt: {res.get('assertions_rebuilt', 0)}"
                console.print(Panel.fit(rebuild_info, title="Knowledge Graph Rebuilder", border_style="green"))
        finally:
            await service.stop()
    asyncio.run(_run())

@case_app.command("list")
def list_cases(json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON")):
    """List all stored investigation cases."""
    async def _run():
        service = create_spider_service(mode="production")
        await service.start()
        try:
            cases = await service.list_cases()
            if json_output:
                console.print(json.dumps(cases, indent=2))
            else:
                table = Table(title="Investigation Cases")
                table.add_column("Case ID", style="cyan")
                table.add_column("Name", style="bold")
                table.add_column("Status", style="green")
                table.add_column("Created", style="dim")
                for c in cases:
                    table.add_row(c["id"], c["name"], c["status"], c["created_at"][:19])
                console.print(table)
        finally:
            await service.stop()
    asyncio.run(_run())

@provider_app.command("list")
def list_providers(json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON")):
    """List all registered providers and their capabilities."""
    service = create_spider_service(mode="production")
    adapters = service.provider_manager.list_adapters()
    res = []
    for a in adapters:
        res.append({
            "provider_id": a.provider_id(),
            "version": a.version(),
            "adapter_version": a.adapter_version(),
            "capabilities": a.capabilities(),
            "network_class": a.network_class().value,
            "accepts": [t.value for t in a.accepts()],
            "produces": [t.value for t in a.produces()]
        })
    if json_output:
        console.print(json.dumps(res, indent=2))
    else:
        table = Table(title="Registered OSINT Providers (Production)")
        table.add_column("Provider ID", style="cyan")
        table.add_column("Version", style="magenta")
        table.add_column("Capabilities", style="yellow")
        table.add_column("Network Class", style="green")
        for p in res:
            table.add_row(p["provider_id"], p["version"], ",".join(p["capabilities"]), p["network_class"])
        console.print(table)

@provider_app.command("health")
def check_provider_health(json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON")):
    """Check real-time health for all registered providers."""
    async def _run():
        service = create_spider_service(mode="production")
        await service.start()
        try:
            health = await service.check_provider_health()
            if json_output:
                console.print(json.dumps(health, indent=2))
            else:
                table = Table(title="Provider Health Status")
                table.add_column("Provider ID", style="cyan")
                table.add_column("State", style="bold")
                table.add_column("Message", style="white")
                for pid, h in health.items():
                    state = h.get("state", "UNKNOWN")
                    color = "green" if state == "READY" else ("yellow" if "LIMITED" in state or "DEGRADED" in state or "MISSING_CREDENTIAL" in state else "red")
                    table.add_row(pid, f"[{color}]{state}[/{color}]", h.get("message", "OK"))
                console.print(table)
        finally:
            await service.stop()
    asyncio.run(_run())

if __name__ == "__main__":
    app()
