"""Evaluation harness for PawPal+ RAG enhancements.

This script compares a baseline schedule validator against the enhanced
multi-source RAG validator and prints a compact summary with scores.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import Iterable

from pawpal_system import Owner, Pet, Scheduler, Task
from rag_validator import (
    build_rag_query,
    load_knowledge_base,
    load_custom_documents,
    retrieve_relevant_context,
    validate_schedule,
)


@dataclass(frozen=True)
class EvaluationCase:
    name: str
    tasks: list[Task]
    pets: list[Pet]
    expected_keywords: tuple[str, ...]
    expect_valid: bool | None = None


def _make_pet(pet_id: str, name: str, species: str, breed: str, weight_kg: float, diet_plan: str = "") -> Pet:
    return Pet(
        pet_id=pet_id,
        name=name,
        species=species,
        breed=breed,
        weight_kg=weight_kg,
        diet_plan=diet_plan,
    )


def build_cases() -> list[EvaluationCase]:
    mochi = _make_pet("pet-1", "Mochi", "dog", "Shiba Inu", 10.5, "High-protein kibble")
    luna = _make_pet("pet-2", "Luna", "cat", "Domestic Short Hair", 4.2, "Wet food AM/PM")

    case1_tasks = [
        Task(
            task_id="task-dog-meds",
            pet_id=mochi.pet_id,
            description="Medication",
            duration_minutes=5,
            priority="high",
            frequency="daily",
            due_time=time(8, 0),
            task_type="medication",
        ),
        Task(
            task_id="task-dog-breakfast",
            pet_id=mochi.pet_id,
            description="Breakfast feeding",
            duration_minutes=10,
            priority="high",
            frequency="daily",
            due_time=time(8, 10),
            task_type="feeding",
        ),
        Task(
            task_id="task-dog-walk",
            pet_id=mochi.pet_id,
            description="Long walk",
            duration_minutes=30,
            priority="medium",
            frequency="daily",
            due_time=time(8, 15),
            task_type="walk",
        ),
    ]

    case2_tasks = [
        Task(
            task_id="task-cat-play",
            pet_id=luna.pet_id,
            description="Interactive play",
            duration_minutes=15,
            priority="medium",
            frequency="daily",
            due_time=time(12, 0),
            task_type="enrichment",
        ),
        Task(
            task_id="task-cat-water",
            pet_id=luna.pet_id,
            description="Fresh water check",
            duration_minutes=5,
            priority="high",
            frequency="daily",
            due_time=time(9, 0),
            task_type="hydration",
        ),
    ]

    case3_tasks = [
        Task(
            task_id="task-dog-feed",
            pet_id=mochi.pet_id,
            description="Dog feeding",
            duration_minutes=10,
            priority="high",
            frequency="daily",
            due_time=time(18, 0),
            task_type="feeding",
        ),
        Task(
            task_id="task-cat-feed",
            pet_id=luna.pet_id,
            description="Cat feeding",
            duration_minutes=10,
            priority="high",
            frequency="daily",
            due_time=time(18, 0),
            task_type="feeding",
        ),
        Task(
            task_id="task-cat-play-2",
            pet_id=luna.pet_id,
            description="Play session",
            duration_minutes=20,
            priority="low",
            frequency="daily",
            due_time=time(18, 0),
            task_type="enrichment",
        ),
    ]

    return [
        EvaluationCase(
            name="Medication before meal",
            tasks=case1_tasks,
            pets=[mochi],
            expected_keywords=("medication", "priority", "meal", "walk", "exercise"),
            expect_valid=False,
        ),
        EvaluationCase(
            name="Cat hydration and play",
            tasks=case2_tasks,
            pets=[luna],
            expected_keywords=("hydration", "play", "routine", "water"),
            expect_valid=True,
        ),
        EvaluationCase(
            name="Multi-pet overlap",
            tasks=case3_tasks,
            pets=[mochi, luna],
            expected_keywords=("overlap", "feeding", "pets", "priority"),
            expect_valid=False,
        ),
    ]


def _combined_text(validation_result: dict) -> str:
    parts = [
        " ".join(validation_result.get("warnings", [])),
        " ".join(validation_result.get("optimizations", [])),
        validation_result.get("explanation", ""),
    ]
    return " ".join(part for part in parts if part).lower()


def _score_result(validation_result: dict, expected_keywords: Iterable[str], expect_valid: bool | None) -> tuple[int, int, float, bool]:
    combined = _combined_text(validation_result)
    expected_list = [keyword.lower() for keyword in expected_keywords]
    matches = sum(1 for keyword in expected_list if keyword in combined)
    total = max(1, len(expected_list))
    keyword_score = matches / total
    valid_match = True if expect_valid is None else validation_result.get("valid") == expect_valid
    overall_pass = valid_match and keyword_score >= 0.5
    return matches, total, keyword_score, overall_pass


def run_baseline(schedule: list[Task], pets: list[Pet], knowledge_base: str) -> dict:
    """Fast, rule-based baseline for comparison."""
    scheduler = Scheduler()
    pet_name_by_id = {pet.pet_id: pet.name for pet in pets}
    warnings: list[str] = []
    optimizations: list[str] = []

    for conflict in scheduler.detect_time_conflicts(schedule):
        due_time_text = conflict["due_time"].strftime("%H:%M")
        pet_names = [pet_name_by_id.get(pet_id, pet_id) for pet_id in conflict["pet_ids"]]
        warnings.append(f"Overlapping tasks at {due_time_text} for {', '.join(pet_names)}.")

    for task in schedule:
        title = task.description.lower()
        if task.task_type == "medication":
            warnings.append(f"Medication task '{task.description}' should stay on time.")
        if task.task_type == "feeding":
            optimizations.append(f"Keep '{task.description}' on a consistent schedule.")
        if "walk" in title or task.task_type == "walk":
            optimizations.append(f"Schedule '{task.description}' with enough recovery time before or after meals.")

    return {
        "valid": len(warnings) == 0,
        "warnings": warnings,
        "optimizations": optimizations,
        "explanation": "Rule-based baseline without retrieval or model reasoning.",
        "raw_response": "",
        "error": None,
    }


def main() -> None:
    knowledge_base = load_knowledge_base()
    custom_docs = load_custom_documents()
    cases = build_cases()

    print("PawPal+ RAG Evaluation")
    print("=" * 72)
    print(f"Knowledge base characters: {len(knowledge_base)}")
    print(f"Custom documents loaded: {', '.join(custom_docs.keys()) if custom_docs else 'none'}")
    print()

    summary_rows = []
    for case in cases:
        baseline_result = run_baseline(case.tasks, case.pets, knowledge_base)
        enhanced_result = validate_schedule(case.tasks, case.pets, knowledge_base)

        baseline_matches, baseline_total, baseline_score, baseline_pass = _score_result(
            baseline_result,
            case.expected_keywords,
            case.expect_valid,
        )
        enhanced_matches, enhanced_total, enhanced_score, enhanced_pass = _score_result(
            enhanced_result,
            case.expected_keywords,
            case.expect_valid,
        )
        delta = enhanced_score - baseline_score

        print(f"Case: {case.name}")
        print(f"  Baseline score: {baseline_score:.2f} ({baseline_matches}/{baseline_total}) | valid={baseline_result.get('valid')} | pass={baseline_pass}")
        print(f"  Enhanced score: {enhanced_score:.2f} ({enhanced_matches}/{enhanced_total}) | valid={enhanced_result.get('valid')} | pass={enhanced_pass}")
        print(f"  Delta: {delta:+.2f}")
        print(f"  Retrieved sources: {', '.join(enhanced_result.get('rag', {}).get('retrieved_sources', [])) or 'none'}")
        print(f"  Workflow steps: {len(enhanced_result.get('workflow', []))}")
        print()

        summary_rows.append((baseline_score, enhanced_score))

    baseline_avg = sum(item[0] for item in summary_rows) / len(summary_rows)
    enhanced_avg = sum(item[1] for item in summary_rows) / len(summary_rows)
    improvement = enhanced_avg - baseline_avg

    print("Summary")
    print("-" * 72)
    print(f"Average baseline score: {baseline_avg:.2f}")
    print(f"Average enhanced score: {enhanced_avg:.2f}")
    print(f"Average improvement: {improvement:+.2f}")
    print(f"Enhancement pass: {'YES' if improvement >= 0 else 'NO'}")


if __name__ == "__main__":
    main()
