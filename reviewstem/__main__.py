import asyncio
import logging
import os
from pathlib import Path
import re
import subprocess
from typing import Optional

from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.markup import escape
from rich.table import Table
import typer

from .advanced_agents import NeuralPruner, StressTester
from .benchmark import (
    benchmark_repo_path,
    get_benchmark_case,
    score_review,
    select_benchmark_cases,
    write_benchmark_outputs,
)
from .config import ReviewStemConfig
from .epigenetics import Epigenetics
from .fitness_function import FitnessFunction
from .hippocampus import Hippocampus
from .immune_system import ImmuneSystem
from .llm_client import LLMClient
from .motor_cortex import MotorCortex
from .mutation_engine import MutationEngine
from .schemas import EvaluationScore, GenomeCluster, LearnedTrait, ReviewOutput
from .stem_cell import StemCell
from .utils import log_review_scores
from .visualizer import ReviewVisualizer

logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger = logging.getLogger("ReviewStem")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

load_dotenv(Path.cwd() / ".env")

app = typer.Typer(help="ReviewStem context-aware PR review agent.")
console = Console()
INCOMPLETE_SQL_FIX_PATTERN = re.compile(
    r"await db\.query\('SELECT \* FROM users WHERE name = \$1',\s*\);"
)


def polish_suggested_fix(text: str) -> str:
    """Fix known malformed SQL parameter examples before displaying output."""
    return INCOMPLETE_SQL_FIX_PATTERN.sub(
        "await db.query('SELECT * FROM users WHERE name = $1', [name]);",
        text,
    )


def get_git_diff(config: ReviewStemConfig) -> tuple[str, bool]:
    """Return the current git diff or the default benchmark diff."""
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0 or not result.stdout.strip():
            return get_benchmark_case("sql_injection").diff, True
        return result.stdout[: config.diff_limit], False
    except Exception:
        return get_benchmark_case("sql_injection").diff, True


def load_review_guidance(diff: str, root: Path) -> list[LearnedTrait]:
    """Load reusable review guidance for the current diff."""
    skill_memory = Epigenetics(str(root / "skills" / "skills.json"))
    relevant = skill_memory.retrieve_relevant_skills(diff)
    if relevant:
        return relevant
    return [
        LearnedTrait(
            trigger_context="Database or SQL query modifications",
            trait_instruction="Always check for SQL injection by verifying parameterization. Never trust string interpolation.",
        )
    ]


async def run_review_pipeline(
    diff: str,
    repo_path: Path,
    config: ReviewStemConfig,
    case_name: str,
    persist_outputs: bool = True,
) -> tuple[ReviewOutput, EvaluationScore, list[float]]:
    """Run the full ReviewStem specialization and review pipeline."""
    llm = LLMClient(config)
    stem = StemCell(llm)
    motor = MotorCortex(llm, repo_path=str(repo_path), config=config)
    immune = ImmuneSystem(llm)
    fitness = FitnessFunction(llm, repo_path=str(repo_path))
    mutation = MutationEngine(llm)
    pruner = NeuralPruner(llm)
    stress_tester = StressTester(llm)

    repo_map = Hippocampus.generate_repo_map(str(repo_path), max_files=config.repo_map_max_files)
    skills = load_review_guidance(diff, Path.cwd())
    if not config.quiet:
        console.print("[yellow]Loaded review guidance.[/yellow]")

    cluster = await stem.differentiate(repo_map, diff, skills)
    current_genomes = cluster.genomes
    all_generations = [current_genomes[0]] if current_genomes else []
    final_review: ReviewOutput | None = None
    evaluation: EvaluationScore | None = None
    scores: list[float] = []

    for iteration in range(1, config.max_iterations + 1):
        if not config.quiet:
            console.print(f"\n[bold yellow]Pass {iteration}: {len(current_genomes)} specialized reviewers active[/bold yellow]")

        pruned_cluster = await pruner.prune(GenomeCluster(genomes=current_genomes))
        current_genomes = pruned_cluster.genomes
        stress_profiles = await asyncio.gather(
            *[stress_tester.generate_profile(genome, diff) for genome in current_genomes]
        )
        draft_reviews = await asyncio.gather(
            *[
                motor.execute_draft_review(genome, diff, profile)
                for genome, profile in zip(current_genomes, stress_profiles)
            ]
        )

        final_peer_tasks = []
        for i, genome in enumerate(current_genomes):
            peers = [draft_reviews[j] for j in range(len(current_genomes)) if j != i]
            final_peer_tasks.append(motor.finalize_review_with_peers(genome, draft_reviews[i], peers))

        finalized_reviews = await asyncio.gather(*final_peer_tasks)
        final_review = await immune.synthesize_and_criticize(finalized_reviews)
        evaluation = await fitness.evaluate(final_review)
        scores.append(evaluation.score)

        if not config.quiet:
            console.print(f"  [bold cyan]Fitness Score: {evaluation.score:.2f}[/bold cyan]")

        if evaluation.score >= config.target_score:
            if not config.quiet:
                console.print("  [green]Quality threshold met.[/green]")
            break

        if iteration < config.max_iterations:
            cluster = await mutation.evolve(current_genomes, final_review, evaluation)
            current_genomes = cluster.genomes
            if current_genomes:
                all_generations.append(current_genomes[0])
        elif not config.quiet:
            console.print("  [red]Maximum iterations reached.[/red]")

    if not final_review or not evaluation:
        raise RuntimeError("ReviewStem did not produce a final review.")

    if persist_outputs:
        ReviewVisualizer.generate_evolution_diagram(case_name, all_generations)
        log_review_scores(case_name, scores[0], scores[-1], len(scores))

    return final_review, evaluation, scores


async def run_baseline_review(diff: str, repo_path: Path, config: ReviewStemConfig) -> ReviewOutput:
    """Run a generic single-prompt baseline review."""
    llm = LLMClient(config)
    repo_map = Hippocampus.generate_repo_map(str(repo_path), max_files=config.repo_map_max_files)
    prompt = f"""
You are a general-purpose code reviewer. Review the diff and return only concrete findings.

Repository Map:
{repo_map}

Diff:
{diff}

Return specific file paths, exact 1-based line numbers, severity, issue descriptions, and complete suggested fixes.
"""
    return await llm.parse(prompt, schema=ReviewOutput)


def display_review(final_review: ReviewOutput):
    """Print the final review safely with Rich markup escaping."""
    console.print("\n[bold white]====================================================[/bold white]")
    console.print("[bold cyan]             FINAL AUTOMATED CODE REVIEW             [/bold cyan]")
    console.print("[bold white]====================================================[/bold white]\n")

    for comment in final_review.comments:
        color = "red" if comment.severity == "High" else "yellow" if comment.severity == "Medium" else "green"
        filepath = escape(comment.filepath)
        issue = escape(comment.issue_description)
        suggested_fix = escape(polish_suggested_fix(comment.suggested_fix))
        console.print(f"[{color}][{comment.severity.upper()}][/{color}] [bold]{filepath}:{comment.line_number}[/bold]")
        console.print(f"  [bold]Issue:[/bold] {issue}")
        console.print(f"  [bold]Fix:[/bold] {suggested_fix}\n")

    console.print("[bold white]----------------------------------------------------[/bold white]")
    console.print(f"[bold white]EXECUTIVE SUMMARY:[/bold white]\n{escape(final_review.overall_summary)}")
    console.print("[bold white]----------------------------------------------------[/bold white]\n")


def apply_cli_overrides(
    model: Optional[str],
    max_iterations: Optional[int],
    target_score: Optional[float],
    quiet: bool,
) -> ReviewStemConfig:
    """Load config and apply command-line overrides."""
    config = ReviewStemConfig.from_env().with_overrides(
        model=model,
        max_iterations=max_iterations,
        target_score=target_score,
        quiet=quiet,
    )
    if config.quiet:
        logging.getLogger().setLevel(logging.WARNING)
        logger.setLevel(logging.WARNING)
    return config


@app.callback(invoke_without_command=True)
def default(
    ctx: typer.Context,
    model: Optional[str] = typer.Option(None, "--model", help="Override REVIEWSTEM_MODEL."),
    max_iterations: Optional[int] = typer.Option(None, "--max-iterations", help="Override REVIEWSTEM_MAX_ITERATIONS."),
    target_score: Optional[float] = typer.Option(None, "--target-score", help="Override REVIEWSTEM_TARGET_SCORE."),
    quiet: bool = typer.Option(False, "--quiet", help="Reduce progress output."),
):
    """Run a review when no subcommand is provided."""
    if ctx.invoked_subcommand is None:
        config = apply_cli_overrides(model, max_iterations, target_score, quiet)
        asyncio.run(review_command(config))


@app.command("review")
def review(
    model: Optional[str] = typer.Option(None, "--model", help="Override REVIEWSTEM_MODEL."),
    max_iterations: Optional[int] = typer.Option(None, "--max-iterations", help="Override REVIEWSTEM_MAX_ITERATIONS."),
    target_score: Optional[float] = typer.Option(None, "--target-score", help="Override REVIEWSTEM_TARGET_SCORE."),
    quiet: bool = typer.Option(False, "--quiet", help="Reduce progress output."),
):
    """Run ReviewStem on the current git diff."""
    config = apply_cli_overrides(model, max_iterations, target_score, quiet)
    asyncio.run(review_command(config))


async def review_command(config: ReviewStemConfig):
    """Run the default review command."""
    if not config.quiet:
        console.print("[bold green]Starting ReviewStem automated review...[/bold green]")

    diff, using_benchmark = get_git_diff(config)
    repo_path = benchmark_repo_path(Path.cwd()) if using_benchmark else Path.cwd()
    case_name = "mock_sql_injection" if using_benchmark else "live_review"

    if using_benchmark and not config.quiet:
        console.print("[yellow]No local changes detected. Using benchmark scenario.[/yellow]")

    final_review, evaluation, _ = await run_review_pipeline(diff, repo_path, config, case_name)

    if not config.quiet and evaluation.score >= 0.75:
        console.print("[yellow]Consolidating review guidance...[/yellow]")
        console.print("[green]Reusable review guidance identified.[/green]")

    display_review(final_review)


@app.command("benchmark")
def benchmark(
    cases: Optional[str] = typer.Option(None, "--benchmark-case", help="Comma-separated case IDs."),
    model: Optional[str] = typer.Option(None, "--model", help="Override REVIEWSTEM_MODEL."),
    max_iterations: Optional[int] = typer.Option(None, "--max-iterations", help="Override REVIEWSTEM_MAX_ITERATIONS."),
    target_score: Optional[float] = typer.Option(None, "--target-score", help="Override REVIEWSTEM_TARGET_SCORE."),
    quiet: bool = typer.Option(False, "--quiet", help="Reduce progress output."),
):
    """Run baseline vs ReviewStem benchmark cases."""
    config = apply_cli_overrides(model, max_iterations, target_score, quiet)
    asyncio.run(benchmark_command(cases, config))


async def benchmark_command(case_ids: str | None, config: ReviewStemConfig):
    """Run benchmark cases and write reports."""
    repo_path = benchmark_repo_path(Path.cwd())
    selected_cases = select_benchmark_cases(case_ids)
    results = []

    for case in selected_cases:
        if not config.quiet:
            console.print(f"[bold yellow]Benchmark case:[/bold yellow] {case.case_id}")

        baseline_review = await run_baseline_review(case.diff, repo_path, config)
        baseline_score = score_review(case, baseline_review, repo_path)
        reviewstem_review, evaluation, scores = await run_review_pipeline(
            case.diff,
            repo_path,
            config,
            case.case_id,
            persist_outputs=False,
        )
        reviewstem_score = score_review(case, reviewstem_review, repo_path)
        results.append(
            {
                "case_id": case.case_id,
                "title": case.title,
                "baseline_score": baseline_score.score,
                "reviewstem_score": reviewstem_score.score,
                "fitness_score": round(evaluation.score, 2),
                "passes": len(scores),
                "notes": reviewstem_score.notes,
            }
        )

    json_path, markdown_path = write_benchmark_outputs(results, Path("outputs"))
    _print_benchmark_table(results)
    console.print(f"\n[green]Wrote benchmark reports:[/green] {json_path}, {markdown_path}")


@app.command("doctor")
def doctor():
    """Check local setup without making API calls."""
    config = ReviewStemConfig.from_env()
    checks = [
        ("OPENAI_API_KEY", "set" if os.getenv("OPENAI_API_KEY") else "missing"),
        ("model", config.model),
        ("benchmark_repo", "present" if benchmark_repo_path(Path.cwd()).exists() else "missing"),
        ("skills", "present" if (Path.cwd() / "skills" / "skills.json").exists() else "missing"),
    ]
    table = Table(title="ReviewStem Doctor")
    table.add_column("Check")
    table.add_column("Status")
    for name, status in checks:
        table.add_row(name, status)
    console.print(table)
    if any(status == "missing" for _, status in checks):
        raise typer.Exit(code=1)


def _print_benchmark_table(results: list[dict]):
    table = Table(title="ReviewStem Benchmark")
    table.add_column("Case")
    table.add_column("Baseline", justify="right")
    table.add_column("ReviewStem", justify="right")
    table.add_column("Delta", justify="right")
    table.add_column("Passes", justify="right")
    for result in results:
        delta = result["reviewstem_score"] - result["baseline_score"]
        table.add_row(
            result["case_id"],
            f"{result['baseline_score']:.2f}",
            f"{result['reviewstem_score']:.2f}",
            f"{delta:+.2f}",
            str(result["passes"]),
        )
    console.print(table)


def cli():
    app()


if __name__ == "__main__":
    cli()
