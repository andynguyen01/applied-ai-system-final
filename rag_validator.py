"""RAG-based validation and optimization for PawPal+ schedules."""

import os
import re
from pathlib import Path
from typing import List, Optional

import google.generativeai as genai
from dotenv import load_dotenv

from pawpal_system import Pet, Task

# Load environment variables from .env in project root and from environment.
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)
load_dotenv()

SOURCE_DIR = Path(__file__).parent / "rag_sources"
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "your",
    "their",
    "have",
    "will",
    "should",
    "about",
    "task",
    "tasks",
    "pet",
    "pets",
    "care",
    "time",
    "day",
    "days",
    "best",
    "schedule",
    "scheduling",
    "validation",
    "health",
    "safety",
}

FEW_SHOT_EXAMPLES = """Example A:
Input: A dog has medication due at 08:00, breakfast at 08:15, and a long walk at 08:20.
Output:
VALID: no
WARNINGS:
- Medication should be prioritized before breakfast and exercise. [source: knowledge_base.txt]
- A long walk immediately after eating can be uncomfortable for some dogs. [source: dog_science_notes.txt]
OPTIMIZATIONS:
- Give medication first, then breakfast, then a short walk later.
EXPLANATION:
The schedule improves when health-critical care happens before flexible exercise.

Example B:
Input: A cat has interactive play at 12:00 and fresh water available all day.
Output:
VALID: yes
WARNINGS:
- None
OPTIMIZATIONS:
- Keep play short and predictable.
EXPLANATION:
This is a low-risk routine because hydration is always available and play is age-appropriate.
"""


def _gemini_model_candidates() -> List[str]:
    """Return model names to try, ordered by preference."""
    preferred = os.getenv("GEMINI_MODEL", "").strip()
    defaults = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-flash-latest",
        "gemini-pro-latest",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-pro",
    ]
    if preferred:
        return [preferred] + [name for name in defaults if name != preferred]
    return defaults


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-zA-Z]{3,}", text.lower()) if token not in STOPWORDS]


def _split_into_chunks(text: str) -> list[str]:
    chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n+", text) if chunk.strip()]
    return chunks if chunks else [text.strip()]


def load_custom_documents(source_dir: Optional[Path] = None) -> dict[str, str]:
    """Load extra RAG documents from a directory."""
    directory = source_dir or SOURCE_DIR
    documents: dict[str, str] = {}
    if not directory.exists():
        return documents

    for path in sorted(directory.glob("*.txt")):
        try:
            documents[path.name] = path.read_text(encoding="utf-8")
        except OSError:
            continue

    return documents


def build_rag_query(schedule: List[Task], pets_info: List[Pet]) -> str:
    """Build a retrieval query from the current schedule and pet profiles."""
    parts: list[str] = []
    for pet in pets_info:
        parts.append(f"{pet.name} {pet.species} {pet.breed} {pet.diet_plan}")
    for task in schedule:
        due_time_text = task.due_time.strftime("%H:%M") if task.due_time else "flexible"
        parts.append(f"{task.description} {task.priority} {task.frequency} {task.task_type} {due_time_text}")
    parts.append("feeding medication hydration exercise play routine conflict timing")
    return " ".join(parts)


def retrieve_relevant_context(
    query: str,
    knowledge_base: str,
    extra_documents: Optional[dict[str, str]] = None,
    top_k: int = 4,
) -> list[dict[str, str]]:
    """Return the most relevant text chunks across all RAG sources."""
    extra_documents = extra_documents or load_custom_documents()
    all_sources = {"knowledge_base.txt": knowledge_base, **extra_documents}
    query_tokens = _tokenize(query)
    query_text = _normalize_text(query)

    scored_chunks: list[tuple[int, str, str]] = []
    for source_name, source_text in all_sources.items():
        for chunk in _split_into_chunks(source_text):
            normalized_chunk = _normalize_text(chunk)
            token_hits = sum(1 for token in set(query_tokens) if token in normalized_chunk)
            phrase_hits = 2 if any(piece in normalized_chunk for piece in ["medication", "feeding", "hydration", "exercise", "routine"]) else 0
            source_bonus = 1 if any(tag in source_name.lower() for tag in ["dog", "cat", "multi_pet", "knowledge_base"]) else 0
            query_bonus = 1 if any(word in normalized_chunk for word in query_text.split()[:4]) else 0
            score = token_hits + phrase_hits + source_bonus + query_bonus
            if score > 0:
                scored_chunks.append((score, source_name, chunk.strip()))

    if not scored_chunks:
        fallback_chunks = [
            (1, source_name, chunk.strip())
            for source_name, source_text in all_sources.items()
            for chunk in _split_into_chunks(source_text)[:1]
        ]
        scored_chunks = fallback_chunks

    ranked = sorted(scored_chunks, key=lambda item: (-item[0], item[1]))[:top_k]
    return [
        {"source": source_name, "text": chunk, "score": str(score)}
        for score, source_name, chunk in ranked
    ]


def _format_retrieved_context(retrieved_chunks: list[dict[str, str]]) -> str:
    lines = []
    for index, chunk in enumerate(retrieved_chunks, start=1):
        lines.append(f"[{index}] source: {chunk['source']} | {chunk['text']}")
    return "\n".join(lines)


def _build_validation_prompt(
    schedule: List[Task],
    pets_info: List[Pet],
    knowledge_base: str,
    retrieved_chunks: list[dict[str, str]],
) -> str:
    pets_context = "\n".join(
        [
            f"Pet: {pet.name} ({pet.species}, {pet.breed}), Weight: {pet.weight_kg}kg, Diet: {pet.diet_plan}, Medications: {pet.medications if pet.medications else 'None'}"
            for pet in pets_info
        ]
    )
    tasks_context = "\n".join(
        [
            f"- {task.description} ({task.duration_minutes} mins, {task.priority} priority) at {task.due_time.strftime('%H:%M') if task.due_time else 'flexible'}"
            for task in schedule
        ]
    )
    retrieved_context = _format_retrieved_context(retrieved_chunks)

    return f"""You are PawPal+'s pet-care planning analyst. Use the retrieved evidence and answer in a concise, veterinary-style tone.

Return exactly in this format:
VALID: yes/no
WARNINGS:
- ...
OPTIMIZATIONS:
- ...
EXPLANATION: ...

Few-shot examples:
{FEW_SHOT_EXAMPLES}

PET HEALTH KNOWLEDGE BASE:
{knowledge_base}

RETRIEVED EVIDENCE FROM MULTIPLE SOURCES:
{retrieved_context}

PETS IN HOUSEHOLD:
{pets_context}

PROPOSED DAILY SCHEDULE:
{tasks_context}

Instructions:
1. Prefer health-critical tasks such as feeding, medication, and hydration before flexible enrichment.
2. Use the retrieved sources to justify concerns and optimizations.
3. Cite source names in square brackets when you mention a warning or optimization.
4. If no concern exists, write WARNINGS: None.
5. Keep the explanation short and practical."""


def _build_workflow_steps(
    query: str,
    retrieved_chunks: list[dict[str, str]],
    response_text: Optional[str],
    error: Optional[str],
) -> list[dict[str, str]]:
    return [
        {"step": "Load documents", "status": "done", "detail": f"Loaded {len(retrieved_chunks)} retrieved chunks from knowledge_base.txt and custom source files."},
        {"step": "Retrieve evidence", "status": "done", "detail": f"Query terms focused on: {query[:120]}..."},
        {"step": "Generate analysis", "status": "done" if response_text else "failed", "detail": "Gemini generated a structured validation response." if response_text else f"Gemini error: {error}"},
        {"step": "Parse result", "status": "done", "detail": "Parsed warnings, optimizations, and explanation into app-ready fields." if response_text else "Used fallback schedule output."},
    ]


def _generate_with_gemini(prompt: str) -> tuple[Optional[str], Optional[str]]:
    """Generate content with Gemini and graceful fallback across model names."""
    api_key = os.getenv("GOOGLE_API_KEY", "").strip() or os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None, (
            f"GOOGLE_API_KEY or GEMINI_API_KEY not found. Checked .env at {env_path}"
        )

    genai.configure(api_key=api_key)

    last_error: Optional[str] = None
    for model_name in _gemini_model_candidates():
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            text = (getattr(response, "text", "") or "").strip()
            if text:
                return text, None
            last_error = f"Model '{model_name}' returned an empty response."
        except Exception as exc:
            last_error = f"Model '{model_name}' failed: {exc}"

    return None, last_error or "Unknown Gemini error"


def load_knowledge_base(filepath: str = "knowledge_base.txt") -> str:
    """Load pet health knowledge from knowledge base file.
    
    Args:
        filepath: Path to the knowledge base file.
    
    Returns:
        String containing the knowledge base content.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Knowledge base file not found. Please create knowledge_base.txt"


def validate_schedule(
    schedule: List[Task],
    pets_info: List[Pet],
    knowledge_base: str,
) -> dict:
    """Validate and optimize schedule using RAG with Gemini.
    
    Args:
        schedule: List of tasks in the daily plan.
        pets_info: List of Pet objects with health/profile info.
        knowledge_base: Content from knowledge base file.
    
    Returns:
        Dictionary with validation results, warnings, and optimizations.
    """
    if not schedule:
        return {
            "valid": True,
            "warnings": [],
            "optimizations": [],
            "explanation": "",
            "workflow": [],
            "rag": {
                "used": False,
                "kb_chars": len(knowledge_base or ""),
                "retrieved_sources": [],
                "model_candidates": _gemini_model_candidates(),
                "model_used": None,
                "raw_response": "",
                "error": None,
            },
        }

    query = build_rag_query(schedule, pets_info)
    custom_documents = load_custom_documents()
    retrieved_chunks = retrieve_relevant_context(query, knowledge_base, custom_documents)
    prompt = _build_validation_prompt(schedule, pets_info, knowledge_base, retrieved_chunks)
    
    # Build context about pets
    pets_context = "\n".join([
        f"Pet: {pet.name} ({pet.species}, {pet.breed}), Weight: {pet.weight_kg}kg, "
        f"Diet: {pet.diet_plan}, Medications: {pet.medications if pet.medications else 'None'}"
        for pet in pets_info
    ])
    
    # Build context about scheduled tasks
    tasks_context = "\n".join([
        f"- {task.description} ({task.duration_minutes} mins, {task.priority} priority) "
        f"at {task.due_time.strftime('%H:%M') if task.due_time else 'flexible'}"
        for task in schedule
    ])
    
    response_text, error = _generate_with_gemini(prompt)
    if response_text:
        parsed = parse_validation_response(response_text)
        parsed["workflow"] = _build_workflow_steps(query, retrieved_chunks, response_text, None)
        parsed["rag"] = {
            "used": True,
            "kb_chars": len(knowledge_base or ""),
            "retrieved_sources": [chunk["source"] for chunk in retrieved_chunks],
            "model_candidates": _gemini_model_candidates(),
            "model_used": os.getenv("GEMINI_MODEL", "").strip() or "auto-fallback",
            "raw_response": response_text,
            "error": None,
        }
        return parsed

    return {
        "valid": True,
        "warnings": [f"Could not validate with AI: {error}"],
        "optimizations": [],
        "explanation": "Falling back to current schedule",
        "workflow": _build_workflow_steps(query, retrieved_chunks, None, error),
        "rag": {
            "used": False,
            "kb_chars": len(knowledge_base or ""),
            "retrieved_sources": [chunk["source"] for chunk in retrieved_chunks],
            "model_candidates": _gemini_model_candidates(),
            "model_used": None,
            "raw_response": "",
            "error": error,
        },
    }


def parse_validation_response(response_text: str) -> dict:
    """Parse Gemini's validation response into structured format.
    
    Args:
        response_text: Raw text response from Gemini.
    
    Returns:
        Dictionary with parsed validation results.
    """
    result = {
        "valid": True,
        "warnings": [],
        "optimizations": [],
        "explanation": "",
        "sources": [],
    }

    if not response_text:
        return {
            "valid": True,
            "warnings": ["Gemini returned an empty response."],
            "optimizations": [],
            "explanation": "Falling back to current schedule"
        }
    
    lines = response_text.split("\n")
    current_section = None

    def _clean_item(text: str) -> str:
        cleaned = text.strip().strip("-").strip("*").strip("•").strip()
        cleaned = re.sub(r"^\d+[\.)]\s*", "", cleaned)
        return cleaned.strip()

    def _extract_sources(text: str) -> list[str]:
        return re.findall(r"\[source:\s*([^\]]+)\]", text, flags=re.IGNORECASE)

    def _looks_like_section_header(text: str) -> Optional[str]:
        normalized = text.strip().lower().strip("* ")
        if normalized.startswith("valid:"):
            return "valid"
        if normalized.startswith("warnings:"):
            return "warnings"
        if normalized.startswith("optimizations:"):
            return "optimizations"
        if normalized.startswith("explanation:"):
            return "explanation"
        return None
    
    for line in lines:
        line = line.strip()
        
        section = _looks_like_section_header(line)
        if section == "valid":
            result["valid"] = "yes" in line.lower() or "true" in line.lower()
        elif section == "warnings":
            current_section = "warnings"
            inline = line.split(":", 1)[1].strip() if ":" in line else ""
            if inline and inline.lower() not in {"none", "n/a", "no", "[]"}:
                result["warnings"].append(_clean_item(inline))
                result["sources"].extend(_extract_sources(inline))
        elif section == "optimizations":
            current_section = "optimizations"
            inline = line.split(":", 1)[1].strip() if ":" in line else ""
            if inline and inline.lower() not in {"none", "n/a", "no", "[]"}:
                result["optimizations"].append(_clean_item(inline))
                result["sources"].extend(_extract_sources(inline))
        elif section == "explanation":
            current_section = "explanation"
            inline = line.split(":", 1)[1].strip() if ":" in line else ""
            if inline:
                result["explanation"] += (" " + inline)
                result["sources"].extend(_extract_sources(inline))
        elif line and current_section:
            if current_section == "warnings":
                cleaned = _clean_item(line)
                if cleaned and cleaned.lower() not in {"none", "n/a", "no", "[]"}:
                    result["warnings"].append(cleaned)
                    result["sources"].extend(_extract_sources(line))
            elif current_section == "optimizations":
                cleaned = _clean_item(line)
                if cleaned and cleaned.lower() not in {"none", "n/a", "no", "[]"}:
                    result["optimizations"].append(cleaned)
                    result["sources"].extend(_extract_sources(line))
            elif current_section == "explanation":
                result["explanation"] += " " + line
                result["sources"].extend(_extract_sources(line))
    
    result["explanation"] = result["explanation"].strip()
    result["sources"] = sorted({source.strip() for source in result["sources"] if source.strip()})

    # Fallback: if model says invalid but no warning lines parsed, keep a reason.
    if not result["valid"] and not result["warnings"]:
        result["warnings"] = [
            "Gemini marked the schedule as not valid, but did not return a structured warning list."
        ]

    return result


def get_task_recommendations(pet: Pet, knowledge_base: str) -> List[str]:
    """Get AI-recommended tasks for a specific pet based on knowledge base.
    
    Args:
        pet: Pet object to get recommendations for.
        knowledge_base: Content from knowledge base file.
    
    Returns:
        List of recommended task descriptions.
    """
    prompt = f"""Based on this pet care knowledge:

{knowledge_base}

And this pet profile:
Name: {pet.name}
Species: {pet.species}
Breed: {pet.breed}
Weight: {pet.weight_kg}kg
Diet: {pet.diet_plan}
Medications: {pet.medications if pet.medications else 'None'}

What are the 3-5 most important daily care tasks this pet needs? List them briefly."""
    
    response_text, error = _generate_with_gemini(prompt)
    if response_text:
        return response_text.split("\n")
    return [f"Error getting recommendations: {error}"]
