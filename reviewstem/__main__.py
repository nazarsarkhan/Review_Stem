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
from .logger import logger
from .motor_cortex import MotorCortex
from .mutation_engine import MutationEngine
from .openspace_integration import (
    ReviewStemSkillEngine,
    ReviewStemExecutionAnalyzer,
    ReviewStemEvolutionEngine,
)
from .schemas import EvaluationScore, GenomeCluster, IterationTrace, ReviewOutput, SelectedSkill, SpecializationState
from .state import (
    compare_genomes,
    extract_changed_files,
    infer_reviewer_skill_map,
    new_run_id,
    summarize_diff,
    summarize_repo_map,
    summarize_review,
    utc_timestamp,
    write_specialization_state,
)
from .stem_cell import StemCell
from .utils import log_review_scores
from .visualizer import ReviewVisualizer

logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)
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


def load_review_guidance(diff: str, root: Path, repo_signals: str = "", case_id: str | None = None, llm: Optional[LLMClient] = None) -> list[SelectedSkill]:
    """Load reusable review guidance for the current diff using OpenSpace."""
    # Try OpenSpace first
    openspace_skills_dir = root / "skills" / "openspace"
    if openspace_skills_dir.exists() and llm:
        try:
            skill_engine = ReviewStemSkillEngine(
                skill_dirs=[openspace_skills_dir],
                llm=llm
            )
            relevant = skill_engine.retrieve_skills(diff, repo_signals, case_id)
            if relevant:
                logger.info("OpenSpace: Retrieved %d skills with quality metrics", len(relevant))
                return relevant
        except Exception as e:
            logger.warning("OpenSpace skill retrieval failed, falling back to Epigenetics: %s", e)

    # Fallback to old Epigenetics
    skill_memory = Epigenetics(str(root / "skills" / "skills.json"))
    relevant = skill_memory.retrieve_selected_skills(diff, repo_signals=repo_signals, case_id=case_id)
    if relevant:
        return relevant
    return [
        SelectedSkill(
            skill_name="Generic Evidence-Grounded PR Review",
            trigger_context="No specific skill matched the diff or repository signals.",
            trait_instruction="Ground every finding in changed code, inspect files when context is missing, avoid speculation, and require concrete fixes for high-risk findings.",
            total_score=0.0,
            reason="Fallback selected because no deterministic skill score was positive.",
            fallback=True,
        )
    ]


async def run_review_pipeline(
    diff: str,
    repo_path: Path,
    config: ReviewStemConfig,
    case_name: str,
    mode: str = "review",
    fallback_diff: bool = False,
    persist_outputs: bool = True,
) -> tuple[ReviewOutput, EvaluationScore, list[float], SpecializationState]:
    """Run the full ReviewStem specialization and review pipeline."""
    llm = LLMClient(config)
    stem = StemCell(llm)
    motor = MotorCortex(llm, repo_path=str(repo_path), config=config)
    immune = ImmuneSystem(llm)
    mutation = MutationEngine(llm)
    pruner = NeuralPruner(llm)
    stress_tester = StressTester(llm)

    repo_map = Hippocampus.generate_repo_map(str(repo_path), max_files=config.repo_map_max_files)
    changed_files = extract_changed_files(diff)
    fitness = FitnessFunction(llm, repo_path=str(repo_path), changed_files=changed_files)
    skills = load_review_guidance(diff, Path.cwd(), repo_signals=repo_map, case_id=case_name, llm=llm)

    # Initialize skill evolution engine for persistent learning
    from .skill_evolution import SkillEvolutionEngine
    skill_evolution = SkillEvolutionEngine(Path(".reviewstem/learned_skills.json"))

    # Initialize OpenSpace components for skill learning
    openspace_skills_dir = Path.cwd() / "skills" / "openspace"
    skill_engine = None
    execution_analyzer = None
    evolution_engine = None

    if openspace_skills_dir.exists():
        try:
            skill_engine = ReviewStemSkillEngine(
                skill_dirs=[openspace_skills_dir],
                llm=llm
            )
            await skill_engine.sync_skills()
            execution_analyzer = ReviewStemExecutionAnalyzer(skill_engine.store)
            evolution_engine = ReviewStemEvolutionEngine(
                store=skill_engine.store,
                registry=skill_engine.registry,
                llm=llm
            )
            logger.info("OpenSpace skill learning enabled")
        except Exception as e:
            logger.warning("OpenSpace initialization failed: %s", e)

    state = SpecializationState(
        run_id=new_run_id(case_name),
        mode="benchmark" if mode == "benchmark" else "review",
        case_id=case_name if mode == "benchmark" else None,
        timestamp=utc_timestamp(),
        target_score=config.target_score,
        max_iterations=config.max_iterations,
        model=config.model,
        environment={
            "changed_files": changed_files,
            "diff_summary": summarize_diff(diff),
            "repo_map_summary": summarize_repo_map(repo_map),
            "selected_benchmark_case": case_name if fallback_diff or mode == "benchmark" else None,
            "diff_was_real": not fallback_diff,
            "repo_path": str(repo_path),
        },
        selected_skills=skills,
    )
    if not config.quiet:
        console.print("[yellow]Loaded review guidance.[/yellow]")

    cluster = await stem.differentiate(repo_map, diff, skills)
    current_genomes = cluster.genomes
    state.initial_reviewer_genomes = current_genomes
    state.reviewer_skill_map = infer_reviewer_skill_map(current_genomes, skills)
    all_generations = [current_genomes[0]] if current_genomes else []
    final_review: ReviewOutput | None = None
    evaluation: EvaluationScore | None = None
    scores: list[float] = []
    evolved_skills_list = []

    for iteration in range(1, config.max_iterations + 1):
        if not config.quiet:
            console.print(f"\n[bold yellow]Pass {iteration}: {len(current_genomes)} specialized reviewers active[/bold yellow]")

        architecture_before = list(current_genomes)
        pruned_cluster = await pruner.prune(GenomeCluster(genomes=current_genomes))
        current_genomes = pruned_cluster.genomes
        stress_profiles = await asyncio.gather(
            *[stress_tester.generate_profile(genome, diff) for genome in current_genomes]
        )
        draft_reviews = await asyncio.gather(
            *[
                motor.execute_draft_review(genome, diff, profile, iteration=iteration)
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

        # OpenSpace: Analyze execution for skill learning
        execution_analysis = None
        if execution_analyzer and skill_engine:
            try:
                execution_analysis = execution_analyzer.analyze_review_execution(
                    run_id=state.run_id,
                    selected_skills=skills,
                    review_output=final_review,
                    fitness_score=evaluation.score,
                    deterministic_penalties=fitness.last_penalties,
                    target_score=config.target_score
                )
                logger.info("Execution analysis: success=%s, candidate_for_evolution=%s",
                           execution_analysis.overall_success,
                           execution_analysis.candidate_for_evolution)
            except Exception as e:
                logger.warning("Execution analysis failed: %s", e)

        iteration_trace = IterationTrace(
            iteration=iteration,
            reviewer_architecture_before=architecture_before,
            pruned_reviewer_architecture=current_genomes,
            stress_profiles={
                genome.persona_name: profile for genome, profile in zip(current_genomes, stress_profiles)
            },
            draft_review_summaries={
                genome.persona_name: summarize_review(review)
                for genome, review in zip(current_genomes, draft_reviews)
            },
            peer_finalized_review_summaries={
                genome.persona_name: summarize_review(review)
                for genome, review in zip(current_genomes, finalized_reviews)
            },
            final_synthesized_review_summary=summarize_review(final_review),
            fitness_score=evaluation.score,
            deterministic_penalties=fitness.last_penalties,
            evaluator_comments=evaluation.feedback,
        )

        if not config.quiet:
            console.print(f"  [bold cyan]Fitness Score: {evaluation.score:.2f}[/bold cyan]")

        if evaluation.score >= config.target_score:
            state.stop_reason = f"target_score_met: {evaluation.score:.2f} >= {config.target_score:.2f}"
            state.iterations.append(iteration_trace)

            # Learn from successful review
            for genome in current_genomes:
                learned = skill_evolution.learn_from_success(
                    genome=genome,
                    case_id=case_name,
                    fitness_score=evaluation.score,
                    min_score_threshold=0.85
                )
                if learned:
                    logger.info(f"Learned new skill from successful review: {learned.skill_name}")

            if not config.quiet:
                console.print("  [green]Quality threshold met.[/green]")
            break

        if iteration < config.max_iterations:
            old_genomes = list(current_genomes)
            cluster = await mutation.evolve(current_genomes, final_review, evaluation)
            current_genomes = cluster.genomes
            iteration_trace.mutation_applied = True
            iteration_trace.mutation_reason = (
                f"Fitness {evaluation.score:.2f} below target {config.target_score:.2f}. "
                f"Evaluator feedback: {evaluation.feedback}"
            )
            iteration_trace.mutation_delta = compare_genomes(old_genomes, current_genomes)

            # OpenSpace: Evolve skills if needed
            if execution_analysis and execution_analysis.candidate_for_evolution and evolution_engine:
                try:
                    evolved_skills = await evolution_engine.evolve_skills(
                        analysis=execution_analysis,
                        review_output=final_review,
                        deterministic_penalties=fitness.last_penalties
                    )
                    if evolved_skills:
                        evolved_skills_list.extend(evolved_skills)
                        logger.info("Evolved %d skills in iteration %d", len(evolved_skills), iteration)
                        if not config.quiet:
                            console.print(f"  [magenta]Evolved {len(evolved_skills)} skills[/magenta]")
                except Exception as e:
                    logger.warning("Skill evolution failed: %s", e)

            state.iterations.append(iteration_trace)
            if current_genomes:
                all_generations.append(current_genomes[0])
        else:
            state.stop_reason = f"max_iterations_reached: {config.max_iterations}"
            state.iterations.append(iteration_trace)
            if not config.quiet:
                console.print("  [red]Maximum iterations reached.[/red]")

    if not final_review or not evaluation:
        raise RuntimeError("ReviewStem did not produce a final review.")

    if persist_outputs:
        ReviewVisualizer.generate_evolution_diagram(case_name, all_generations)
        log_review_scores(case_name, scores[0], scores[-1], len(scores))

    state.tool_use = motor.tool_events
    state.outputs = {
        "llm_call_count": llm.call_count,
        "llm_calls": llm.call_log,
        "score_history": scores,
        "final_comment_count": len(final_review.comments),
    }

    # Add evolved skills to state
    if evolved_skills_list:
        state.outputs["evolved_skills"] = evolved_skills_list

    # Add skill evolution statistics to state
    skill_stats = skill_evolution.get_skill_statistics()
    state.outputs["skill_evolution_stats"] = skill_stats
    if skill_stats["total_learned_skills"] > 0:
        logger.info(f"Skill evolution stats: {skill_stats['total_learned_skills']} learned skills, "
                   f"{skill_stats['average_success_rate']:.2%} avg success rate")

    write_specialization_state(
        state,
        Path("outputs"),
        case_id=case_name if mode == "benchmark" else None,
    )

    return final_review, evaluation, scores, state


async def run_baseline_review(diff: str, repo_path: Path, config: ReviewStemConfig) -> tuple[ReviewOutput, int]:
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
    review = await llm.parse(prompt, schema=ReviewOutput, stage="generic_baseline")
    return review, llm.call_count


async def run_skilled_baseline_review(
    diff: str,
    repo_path: Path,
    config: ReviewStemConfig,
    case_id: str | None = None,
) -> tuple[ReviewOutput, int]:
    """Run a single generic reviewer with selected skill text but no specialization loop."""
    llm = LLMClient(config)
    repo_map = Hippocampus.generate_repo_map(str(repo_path), max_files=config.repo_map_max_files)
    skills = load_review_guidance(diff, Path.cwd(), repo_signals=repo_map, case_id=case_id)
    skill_text = "\n".join(skill.model_dump_json() for skill in skills)
    prompt = f"""
You are a general-purpose code reviewer. Use the selected review skills below, but do not create
specialized reviewers, peer review, mutation, or iterative fitness loops.

Selected Skills:
{skill_text}

Repository Map:
{repo_map}

Diff:
{diff}

Return specific file paths, exact 1-based line numbers, severity, issue descriptions, and complete suggested fixes.
"""
    review = await llm.parse(prompt, schema=ReviewOutput, stage="skilled_baseline")
    return review, llm.call_count


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
    case_name = "sql_injection" if using_benchmark else "live_review"

    if using_benchmark and not config.quiet:
        console.print("[yellow]No local changes detected. Using benchmark scenario.[/yellow]")

    final_review, evaluation, _, _ = await run_review_pipeline(
        diff,
        repo_path,
        config,
        case_name,
        mode="review",
        fallback_diff=using_benchmark,
    )

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

        baseline_review, baseline_calls = await run_baseline_review(case.diff, repo_path, config)
        baseline_score = score_review(case, baseline_review, repo_path)
        skilled_baseline_review, skilled_baseline_calls = await run_skilled_baseline_review(
            case.diff,
            repo_path,
            config,
            case.case_id,
        )
        skilled_baseline_score = score_review(case, skilled_baseline_review, repo_path)
        reviewstem_review, evaluation, scores, state = await run_review_pipeline(
            case.diff,
            repo_path,
            config,
            case.case_id,
            mode="benchmark",
            persist_outputs=False,
        )
        reviewstem_score = score_review(case, reviewstem_review, repo_path)
        results.append(
            {
                "case_id": case.case_id,
                "title": case.title,
                "baseline_score": baseline_score.score,
                "skilled_baseline_score": skilled_baseline_score.score,
                "reviewstem_score": reviewstem_score.score,
                "fitness_score": round(evaluation.score, 2),
                "passes": len(scores),
                "baseline_calls": baseline_calls,
                "skilled_baseline_calls": skilled_baseline_calls,
                "reviewstem_calls": state.outputs.get("llm_call_count", 0),
                "requires_context": case.requires_context,
                "notes": reviewstem_score.notes,
                "issue_detected": reviewstem_score.issue_detected,
                "grounding_score": reviewstem_score.grounding_score,
                "concept_score": reviewstem_score.concept_score,
                "severity_score": reviewstem_score.severity_score,
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


@app.command("skills")
def skills_command(
    action: str = typer.Argument("list", help="Action: list, stats, export, prune"),
    output: str = typer.Option(None, help="Output file for export action"),
):
    """Manage learned skills from successful reviews."""
    from .skill_evolution import SkillEvolutionEngine

    evolution = SkillEvolutionEngine(Path(".reviewstem/learned_skills.json"))

    if action == "list":
        learned = evolution.get_learned_skills()
        if not learned:
            console.print("[yellow]No learned skills yet. Run successful reviews to learn new skills.[/yellow]")
            return

        table = Table(title="Learned Skills")
        table.add_column("Skill Name")
        table.add_column("Source Case")
        table.add_column("Success Score")
        table.add_column("Usage")
        table.add_column("Success Rate")
        table.add_column("Learned At")

        for skill in learned:
            success_rate = skill.success_count / skill.usage_count if skill.usage_count > 0 else 0.0
            table.add_row(
                skill.skill_name,
                skill.source_case,
                f"{skill.success_score:.2f}",
                f"{skill.success_count}/{skill.usage_count}",
                f"{success_rate:.1%}",
                skill.learned_at[:10]
            )

        console.print(table)
        console.print(f"\n[cyan]Total learned skills: {len(learned)}[/cyan]")

    elif action == "stats":
        stats = evolution.get_skill_statistics()
        console.print("\n[bold]Skill Evolution Statistics[/bold]")
        console.print(f"Total learned skills: {stats['total_learned_skills']}")
        console.print(f"Total usage: {stats['total_usage']}")
        console.print(f"Total success: {stats['total_success']}")
        console.print(f"Average success rate: {stats['average_success_rate']:.1%}")
        console.print(f"Last updated: {stats['last_updated']}")

    elif action == "export":
        if not output:
            console.print("[red]Error: --output required for export action[/red]")
            raise typer.Exit(code=1)

        evolution.export_to_skill_catalog(Path(output))
        console.print(f"[green]Exported learned skills to {output}[/green]")

    elif action == "prune":
        evolution.prune_underperforming_skills(min_success_rate=0.5, min_usage=3)
        console.print("[green]Pruned underperforming skills[/green]")

    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        console.print("Valid actions: list, stats, export, prune")
        raise typer.Exit(code=1)


def _print_benchmark_table(results: list[dict]):
    table = Table(title="ReviewStem Benchmark")
    table.add_column("Case")
    table.add_column("Generic", justify="right")
    table.add_column("Generic+Skills", justify="right")
    table.add_column("ReviewStem", justify="right")
    table.add_column("Delta", justify="right")
    table.add_column("Detected?", justify="center")
    table.add_column("Calls", justify="right")
    table.add_column("Passes", justify="right")
    for result in results:
        delta = result["reviewstem_score"] - result["baseline_score"]
        detected = "Y" if result.get("issue_detected", False) else "N"
        table.add_row(
            result["case_id"],
            f"{result['baseline_score']:.2f}",
            f"{result['skilled_baseline_score']:.2f}",
            f"{result['reviewstem_score']:.2f}",
            f"{delta:+.2f}",
            detected,
            f"{result['baseline_calls']}/{result['skilled_baseline_calls']}/{result['reviewstem_calls']}",
            str(result["passes"]),
        )
    console.print(table)


def cli():
    app()


if __name__ == "__main__":
    cli()
