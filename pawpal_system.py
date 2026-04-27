"""Core implementation for the PawPal pet-care planning system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional


@dataclass
class Task:
	"""A single care activity for a pet."""

	task_id: str
	pet_id: str
	description: str
	duration_minutes: int
	priority: str
	frequency: str = "daily"
	due_time: Optional[time] = None
	completed: bool = False
	task_type: str = "general"
	reason: str = ""
	scheduled_for: Optional[date] = None

	VALID_PRIORITIES = {"low", "medium", "high"}
	VALID_FREQUENCIES = {"once", "daily", "weekly"}

	def __post_init__(self) -> None:
		"""Normalize and validate task fields after initialization."""
		self.priority = self.priority.lower().strip()
		self.frequency = self.frequency.lower().strip()
		if self.priority not in self.VALID_PRIORITIES:
			raise ValueError(f"Invalid priority: {self.priority}")
		if self.frequency not in self.VALID_FREQUENCIES:
			raise ValueError(f"Invalid frequency: {self.frequency}")
		if self.duration_minutes <= 0:
			raise ValueError("duration_minutes must be positive")

	def is_due_on(self, day: date) -> bool:
		"""Return True if task should appear in plan for this date."""
		if self.completed and self.frequency == "once":
			return False
		if self.frequency == "daily":
			if self.scheduled_for is None:
				return True
			return day >= self.scheduled_for
		if self.frequency == "weekly":
			if self.scheduled_for is None:
				return False
			return day >= self.scheduled_for and day.weekday() == self.scheduled_for.weekday()
		# once
		if self.scheduled_for is None:
			return True
		return self.scheduled_for == day

	def mark_completed(self) -> None:
		"""Mark this task as completed."""
		self.completed = True

	def mark_complete(self) -> None:
		"""Compatibility alias for mark_completed."""
		self.mark_completed()

	def mark_incomplete(self) -> None:
		"""Mark this task as not completed."""
		self.completed = False

	def calculate_urgency(self, current_time: time) -> int:
		"""Higher number means more urgent."""
		urgency = 0
		if self.priority == "high":
			urgency += 60
		elif self.priority == "medium":
			urgency += 35
		else:
			urgency += 15

		if self.due_time is not None:
			now_minutes = current_time.hour * 60 + current_time.minute
			due_minutes = self.due_time.hour * 60 + self.due_time.minute
			if now_minutes >= due_minutes:
				urgency += 50
			else:
				mins_left = due_minutes - now_minutes
				urgency += max(0, 40 - mins_left // 10)

		if not self.completed:
			urgency += 10

		return urgency

	def explain_why(self, pet_name: Optional[str] = None) -> str:
		"""Return a short explanation for why the task was selected.

		Args:
			pet_name: Optional display name to use instead of ``pet_id``.
		"""
		due_text = self.due_time.strftime("%H:%M") if self.due_time else "any time"
		pet_label = pet_name if pet_name else self.pet_id
		return (
			f"{self.description} for pet {pet_label} was selected because "
			f"it is {self.priority} priority, {self.frequency}, and due around {due_text}."
		)


@dataclass
class Pet:
	"""Stores pet profile and its care tasks."""

	pet_id: str
	name: str
	species: str
	breed: str
	weight_kg: float
	diet_plan: str = ""
	medications: List[str] = field(default_factory=list)
	care_notes: Dict[str, Any] = field(default_factory=dict)
	tasks: List[Task] = field(default_factory=list)

	def add_task(self, task: Task) -> None:
		"""Add a task to this pet after validating ownership."""
		if task.pet_id != self.pet_id:
			raise ValueError("task.pet_id must match pet.pet_id")
		self.tasks.append(task)

	def remove_task(self, task_id: str) -> bool:
		"""Remove a task by id and return True if removed."""
		for i, task in enumerate(self.tasks):
			if task.task_id == task_id:
				del self.tasks[i]
				return True
		return False

	def get_tasks_for_day(self, day: date) -> List[Task]:
		"""Return tasks that are due on the provided day."""
		return [task for task in self.tasks if task.is_due_on(day)]

	def get_pending_tasks_for_day(self, day: date) -> List[Task]:
		"""Return due tasks for the day that are not completed."""
		return [task for task in self.get_tasks_for_day(day) if not task.completed]

	def update_health(self, weight_kg: float, notes: Optional[Dict[str, Any]] = None) -> None:
		"""Update this pet's weight and optionally merge care notes."""
		self.weight_kg = weight_kg
		if notes:
			self.care_notes.update(notes)


class Owner:
	"""Manages pets and provides task access for scheduling."""

	def __init__(
		self,
		owner_id: str,
		name: str,
		time_available_min_per_day: int,
		preferences: Optional[Dict[str, Any]] = None,
		notification_method: str = "app",
		pets: Optional[List[Pet]] = None,
	) -> None:
		"""Initialize an owner with profile, preferences, and pets."""
		self.owner_id = owner_id
		self.name = name
		self.time_available_min_per_day = time_available_min_per_day
		self.preferences = preferences if preferences is not None else {}
		self.notification_method = notification_method
		self.pets: List[Pet] = pets if pets is not None else []

	def add_pet(self, pet: Pet) -> None:
		"""Add a pet to the owner's managed pet list."""
		self.pets.append(pet)

	def remove_pet(self, pet_id: str) -> bool:
		"""Remove a pet by id and return True if removed."""
		for i, pet in enumerate(self.pets):
			if pet.pet_id == pet_id:
				del self.pets[i]
				return True
		return False

	def set_preferences(self, preferences: Dict[str, Any]) -> None:
		"""Replace owner preferences with the provided mapping."""
		self.preferences = preferences

	def get_available_time(self, day: date) -> int:
		"""Allow per-day overrides in preferences via 'time_overrides'."""
		overrides = self.preferences.get("time_overrides", {})
		return int(overrides.get(day.isoformat(), self.time_available_min_per_day))

	def get_all_tasks(self, day: Optional[date] = None) -> List[Task]:
		"""Return all pet tasks, optionally filtered to a specific day."""
		all_tasks: List[Task] = []
		for pet in self.pets:
			if day is None:
				all_tasks.extend(pet.tasks)
			else:
				all_tasks.extend(pet.get_tasks_for_day(day))
		return all_tasks

	def complete_task(self, task_id: str) -> bool:
		"""Mark a task completed by id and return success status."""
		for task in self.get_all_tasks():
			if task.task_id == task_id:
				task.mark_completed()
				return True
		return False


class Scheduler:
	"""The planning brain that builds a feasible daily plan."""

	def __init__(self, constraints: Optional[Dict[str, Any]] = None) -> None:
		"""Initialize scheduler state and optional planning constraints."""
		self.constraints = constraints if constraints is not None else {}
		self.daily_plan: List[Task] = []
		self._task_index: Dict[str, Task] = {}
		self._last_explanations: List[str] = []

	def collect_tasks(self, pets: List[Pet], day: date) -> List[Task]:
		"""Collect pending tasks due on the given day from all pets."""
		collected: List[Task] = []
		for pet in pets:
			collected.extend(pet.get_pending_tasks_for_day(day))
		return collected

	def sort_by_time(self, tasks: List[Task]) -> List[Task]:
		"""Return tasks in chronological order by due time.

		Tasks without a due time are placed at the end. Description is used as a
		stable tie-breaker when two tasks have the same due time.

		Args:
			tasks: Tasks to sort.

		Returns:
			A new list of tasks sorted by time, earliest first.
		"""
		return sorted(
			tasks,
			key=lambda task: (
				task.due_time is None,
				task.due_time if task.due_time is not None else time.max,
				task.description.lower(),
			),
		)

	def filter_tasks(
		self,
		tasks: List[Task],
		pets: List[Pet],
		completed: Optional[bool] = None,
		pet_name: Optional[str] = None,
	) -> List[Task]:
		"""Filter tasks by completion status and/or pet name.

		Filtering is optional and composable:
		- If ``completed`` is provided, only tasks with that status are kept.
		- If ``pet_name`` is provided, matching is case-insensitive.

		Args:
			tasks: Tasks to filter.
			pets: Pets used to map ``pet_id`` values to pet names.
			completed: Optional completion filter (True or False).
			pet_name: Optional pet name filter.

		Returns:
			A list containing only tasks that satisfy all provided filters.
		"""
		pet_name_by_id = {pet.pet_id: pet.name for pet in pets}
		target_pet_name = pet_name.lower().strip() if pet_name is not None else None

		filtered: List[Task] = []
		for task in tasks:
			if completed is not None and task.completed != completed:
				continue
			if target_pet_name is not None:
				name_for_task = pet_name_by_id.get(task.pet_id, "")
				if name_for_task.lower().strip() != target_pet_name:
					continue
			filtered.append(task)

		return filtered

	def rank_tasks(self, tasks: List[Task], current_time: Optional[time] = None) -> List[Task]:
		"""Rank tasks by urgency score, then by shorter duration, then name.

		Urgency is computed by ``Task.calculate_urgency`` using current time.
		Higher urgency tasks appear first.

		Args:
			tasks: Tasks to rank.
			current_time: Optional time reference for urgency scoring.

		Returns:
			A ranked task list, highest urgency first.
		"""
		if current_time is None:
			current_time = datetime.now().time()

		def rank_key(task: Task) -> tuple[int, int, str]:
			# Negative urgency gives descending urgency without reverse=True.
			return (
				-task.calculate_urgency(current_time),
				task.duration_minutes,
				task.description.lower(),
			)

		return sorted(tasks, key=rank_key)

	def apply_owner_constraints(self, owner: Owner, tasks: List[Task], day: date) -> List[Task]:
		"""Filter ranked tasks to fit owner limits and preferences."""
		available_minutes = owner.get_available_time(day)
		blocked_types = set(owner.preferences.get("blocked_task_types", []))
		preferred_species = owner.preferences.get("preferred_species")

		selected: List[Task] = []
		used_minutes = 0

		pet_by_id = {pet.pet_id: pet for pet in owner.pets}

		for task in tasks:
			if task.task_type in blocked_types:
				continue
			pet = pet_by_id.get(task.pet_id)
			if preferred_species and pet and pet.species != preferred_species:
				continue
			if used_minutes + task.duration_minutes > available_minutes:
				continue
			selected.append(task)
			used_minutes += task.duration_minutes

		return selected

	def build_daily_plan(self, owner: Owner, day: date, current_time: Optional[time] = None) -> List[Task]:
		"""Build and store the selected daily plan for the owner."""
		candidate_tasks = self.collect_tasks(owner.pets, day)
		ranked_tasks = self.rank_tasks(candidate_tasks, current_time=current_time)
		selected_tasks = self.apply_owner_constraints(owner, ranked_tasks, day)
		self.daily_plan = self.sort_by_time(selected_tasks)
		pet_name_by_id = {pet.pet_id: pet.name for pet in owner.pets}

		self._task_index = {task.task_id: task for task in self.daily_plan}
		self._last_explanations = [
			f"Included: {task.explain_why(pet_name=pet_name_by_id.get(task.pet_id))}"
			for task in self.daily_plan
		]

		for task in self.daily_plan:
			task.scheduled_for = day

		return self.daily_plan

	def mark_task_complete(self, owner: Owner, task_id: str, completed_on: Optional[date] = None) -> bool:
		"""Mark a task complete and create the next recurring task instance.

		For recurring tasks:
		- ``daily`` creates a new task scheduled for ``completed_on + 1 day``.
		- ``weekly`` creates a new task scheduled for ``completed_on + 7 days``.

		Args:
			owner: Owner containing pets and tasks.
			task_id: Identifier of the task to mark complete.
			completed_on: Date used to calculate the next recurring date.

		Returns:
			True if a task was completed; False if not found or already completed.
		"""
		if completed_on is None:
			completed_on = date.today()

		for pet in owner.pets:
			for task in pet.tasks:
				if task.task_id != task_id:
					continue
				if task.completed:
					return False

				task.mark_completed()

				if task.frequency in {"daily", "weekly"}:
					next_due_date = completed_on + timedelta(days=1 if task.frequency == "daily" else 7)
					next_task = Task(
						task_id=f"{task.task_id}-next-{next_due_date.isoformat()}",
						pet_id=task.pet_id,
						description=task.description,
						duration_minutes=task.duration_minutes,
						priority=task.priority,
						frequency=task.frequency,
						due_time=task.due_time,
						task_type=task.task_type,
						reason=task.reason,
						scheduled_for=next_due_date,
					)
					pet.add_task(next_task)

				return True

		return False

	def detect_time_conflicts(self, tasks: List[Task]) -> List[Dict[str, Any]]:
		"""Detect same-time scheduling conflicts in a task list.

		A conflict is any due time shared by two or more tasks. Tasks without due
		time are ignored.

		Args:
			tasks: Tasks to evaluate.

		Returns:
			A list of conflict dictionaries with due time, involved task IDs,
			involved pet IDs, and a ``same_pet`` flag.
		"""
		tasks_by_due_time: Dict[time, List[Task]] = {}
		for task in tasks:
			if task.due_time is None:
				continue
			tasks_by_due_time.setdefault(task.due_time, []).append(task)

		conflicts: List[Dict[str, Any]] = []
		for due_time_value in sorted(tasks_by_due_time.keys()):
			group = tasks_by_due_time[due_time_value]
			if len(group) < 2:
				continue

			pet_ids = {task.pet_id for task in group}
			conflicts.append(
				{
					"due_time": due_time_value,
					"task_ids": [task.task_id for task in group],
					"task_descriptions": [task.description for task in group],
					"pet_ids": sorted(pet_ids),
					"same_pet": len(pet_ids) == 1,
				}
			)

		return conflicts

	def get_conflict_warnings(
		self,
		tasks: List[Task],
		pet_name_by_id: Optional[Dict[str, str]] = None,
	) -> List[str]:
		"""Build lightweight warning messages from detected time conflicts.

		This method never raises for conflicts; it returns human-readable warning
		strings so callers can display non-blocking alerts in CLI or UI.

		Args:
			tasks: Tasks to inspect for overlaps.
			pet_name_by_id: Optional mapping to render pet names in warnings.

		Returns:
			A list of warning strings. Empty list means no conflicts.
		"""
		if pet_name_by_id is None:
			pet_name_by_id = {}

		warnings: List[str] = []
		for conflict in self.detect_time_conflicts(tasks):
			due_time_text = conflict["due_time"].strftime("%H:%M")
			pet_names = [pet_name_by_id.get(pet_id, pet_id) for pet_id in conflict["pet_ids"]]
			task_names = conflict.get("task_descriptions", [])
			task_names_text = ", ".join(task_names) if task_names else "multiple tasks"
			if conflict["same_pet"]:
				warnings.append(
					f"Warning: overlapping tasks at {due_time_text} for {pet_names[0]} ({task_names_text})."
				)
			else:
				pets_text = ", ".join(pet_names)
				warnings.append(
					f"Warning: overlapping tasks at {due_time_text} across pets ({pets_text}) [{task_names_text}]."
				)

		return warnings

	def reschedule_unfinished_tasks(self, owner: Owner, source_day: date, target_day: Optional[date] = None) -> int:
		"""Move unfinished once/weekly tasks to a target day."""
		if target_day is None:
			target_day = source_day + timedelta(days=1)

		rescheduled_count = 0
		for task in owner.get_all_tasks(source_day):
			if not task.completed and task.frequency in {"once", "weekly"}:
				task.scheduled_for = target_day
				rescheduled_count += 1

		return rescheduled_count

	def get_task_by_id(self, task_id: str) -> Optional[Task]:
		"""Return a task from the current plan index by id."""
		return self._task_index.get(task_id)

	def _to_minutes(self, value: time) -> int:
		"""Convert a time value to minutes from midnight."""
		return value.hour * 60 + value.minute

	def _from_minutes(self, minutes: int) -> time:
		"""Convert minutes from midnight back to a time value."""
		minutes = minutes % (24 * 60)
		return time(minutes // 60, minutes % 60)

	def _window_for_task(self, task: Task) -> tuple[int, int, str]:
		"""Return healthy scheduling window and a short rationale for task type."""
		text = f"{task.task_type} {task.description}".lower()

		if any(token in text for token in ["medication", "medicine", "med", "pill", "antibiotic"]):
			return (5 * 60, 23 * 60, "Medication is allowed in a broad window but should stay consistent.")
		if any(token in text for token in ["shower", "bath", "groom", "grooming"]):
			return (8 * 60, 20 * 60, "Bathing/grooming is best during daytime to reduce stress.")
		if any(token in text for token in ["walk", "exercise", "play"]):
			return (6 * 60, 21 * 60 + 30, "Exercise is safer during daytime/evening windows.")
		if any(token in text for token in ["feed", "meal", "breakfast", "dinner", "food"]):
			return (6 * 60, 21 * 60, "Feeding should be in regular waking-hour windows.")
		return (6 * 60, 22 * 60, "General care task placed within normal waking hours.")

	def _duration_profile(self, task: Task) -> tuple[int, str]:
		"""Return a recommended maximum duration and short rationale for a task."""
		text = f"{task.task_type} {task.description}".lower()

		if any(token in text for token in ["shower", "bath", "groom", "grooming"]):
			return (20, "Bathing/grooming should stay short to avoid stress or chilling.")
		if any(token in text for token in ["walk", "exercise", "play", "run"]):
			return (30, "Exercise blocks should stay moderate so pets do not overexert.")
		if any(token in text for token in ["feed", "meal", "breakfast", "dinner", "food"]):
			return (15, "Feeding blocks should be efficient and consistent.")
		if any(token in text for token in ["medication", "medicine", "med", "pill", "antibiotic"]):
			return (5, "Medication tasks should be quick and precise.")
		return (task.duration_minutes, "No duration change needed for this task type.")

	def _priority_weight(self, priority: str) -> int:
		"""Return numeric weight for priorities, higher means more important."""
		mapping = {"high": 3, "medium": 2, "low": 1}
		return mapping.get(priority.lower().strip(), 1)

	def optimize_schedule(
		self,
		owner: Owner,
		day: date,
		current_time: Optional[time] = None,
		slot_minutes: int = 15,
	) -> Dict[str, Any]:
		"""Build an optimized schedule that keeps all due tasks and resolves timing issues.

		Optimization goals:
		- keep due tasks in plan instead of dropping on conflicts
		- avoid unhealthy timing windows (for example, midnight showers)
		- avoid overlapping tasks across one or many pets
		- keep higher-priority tasks earlier when conflicts happen

		Returns:
			Dictionary with optimized tasks and human-readable adjustments.
		"""
		if slot_minutes <= 0:
			slot_minutes = 15

		if current_time is None:
			current_time = datetime.now().time()

		candidate_tasks = self.collect_tasks(owner.pets, day)
		if not candidate_tasks:
			return {
				"tasks": [],
				"adjustments": ["No pending tasks available to optimize."],
				"conflicts_resolved": 0,
				"window_adjustments": 0,
			}

		# Copy tasks so optimization does not mutate canonical task definitions.
		working_tasks: List[Task] = []
		for task in candidate_tasks:
			working_tasks.append(
				Task(
					task_id=task.task_id,
					pet_id=task.pet_id,
					description=task.description,
					duration_minutes=task.duration_minutes,
					priority=task.priority,
					frequency=task.frequency,
					due_time=task.due_time,
					completed=task.completed,
					task_type=task.task_type,
					reason=task.reason,
					scheduled_for=task.scheduled_for,
				)
			)

		# Resolve simultaneous due-time collisions by importance first.
		ranked_tasks = self.rank_tasks(working_tasks, current_time=current_time)
		pet_name_by_id = {pet.pet_id: pet.name for pet in owner.pets}

		# Track ranges as [start_min, end_min) for owner-level non-overlap.
		occupied: List[tuple[int, int, str]] = []
		optimized: List[Task] = []
		adjustments: List[str] = []
		conflicts_resolved = 0
		window_adjustments = 0

		for task in ranked_tasks:
			pet_name = pet_name_by_id.get(task.pet_id, task.pet_id)
			window_start, window_end, window_note = self._window_for_task(task)
			recommended_duration, duration_note = self._duration_profile(task)
			if task.duration_minutes > recommended_duration:
				original_duration = task.duration_minutes
				task.duration_minutes = recommended_duration
				adjustments.append(
					f"Shortened {task.description} for {pet_name} from {original_duration} to {task.duration_minutes} minutes. {duration_note}"
				)

			if task.due_time is None:
				preferred = window_start
			else:
				preferred = self._to_minutes(task.due_time)

			if preferred < window_start or preferred > window_end:
				old_text = self._from_minutes(preferred).strftime("%H:%M")
				preferred = max(window_start, min(preferred, window_end))
				new_text = self._from_minutes(preferred).strftime("%H:%M")
				window_adjustments += 1
				adjustments.append(
					f"Moved {task.description} for {pet_name} from {old_text} to {new_text}. {window_note}"
				)

			start_min = preferred
			end_min = start_min + task.duration_minutes

			# Move forward in discrete slots until non-overlapping.
			while True:
				overlap = False
				for existing_start, existing_end, existing_task_id in occupied:
					if start_min < existing_end and end_min > existing_start:
						overlap = True
						break
				if not overlap:
					break

				start_min += slot_minutes
				end_min = start_min + task.duration_minutes
				conflicts_resolved += 1

			# If we drifted beyond preferred healthy window, clamp to the earliest possible
			# slot in that window that still avoids overlap.
			if end_min > window_end + task.duration_minutes:
				start_min = window_start
				end_min = start_min + task.duration_minutes
				while True:
					overlap = False
					for existing_start, existing_end, existing_task_id in occupied:
						if start_min < existing_end and end_min > existing_start:
							overlap = True
							break
					if not overlap:
						break
					start_min += slot_minutes
					end_min = start_min + task.duration_minutes

			new_due = self._from_minutes(start_min)
			if task.due_time is None:
				adjustments.append(
					f"Scheduled {task.description} for {pet_name} at {new_due.strftime('%H:%M')} to avoid overlap and fill open time."
				)
			elif self._to_minutes(task.due_time) != start_min:
				adjustments.append(
					f"Shifted {task.description} for {pet_name} from {task.due_time.strftime('%H:%M')} to {new_due.strftime('%H:%M')} to resolve conflicts."
				)

			task.due_time = new_due
			occupied.append((start_min, end_min, task.task_id))
			optimized.append(task)

		optimized = self.sort_by_time(optimized)

		# Rebuild explanation lines for the optimized plan.
		self.daily_plan = optimized
		self._task_index = {task.task_id: task for task in optimized}
		self._last_explanations = [
			f"Included: {task.explain_why(pet_name=pet_name_by_id.get(task.pet_id))}"
			for task in optimized
		]

		# Prefer medication/high-priority first if tasks still share a due minute.
		for conflict in self.detect_time_conflicts(optimized):
			if not conflict.get("task_descriptions"):
				continue
			pet_names = [pet_name_by_id.get(pid, pid) for pid in conflict["pet_ids"]]
			adjustments.append(
				"Conflict remained at "
				+ conflict["due_time"].strftime("%H:%M")
				+ " across "
				+ ", ".join(pet_names)
				+ "; consider larger slot spacing."
			)

		available_minutes = owner.get_available_time(day)
		total_minutes = sum(task.duration_minutes for task in optimized)
		if total_minutes > available_minutes:
			overflow = total_minutes - available_minutes
			adjustments.append(
				f"Optimized plan exceeds owner available time by {overflow} minutes; consider splitting into next day."
			)

		if not adjustments:
			adjustments.append("Current plan already looks well-optimized for timing and conflicts.")

		return {
			"tasks": optimized,
			"adjustments": adjustments,
			"conflicts_resolved": conflicts_resolved,
			"window_adjustments": window_adjustments,
		}

	def explain_plan(self) -> str:
		"""Return human-readable explanations for the current daily plan."""
		if not self.daily_plan:
			return "No tasks were selected for today."
		return "\n".join(self._last_explanations)


# Backward-compatible alias for earlier class naming.
Pets = Pet
