from datetime import date, time

from pawpal_system import Owner, Pet, Scheduler, Task
from rag_validator import load_custom_documents, retrieve_relevant_context


def test_task_completion_marks_task_as_completed() -> None:
	task = Task(
		task_id="task-1",
		pet_id="pet-1",
		description="Morning walk",
		duration_minutes=20,
		priority="high",
	)

	assert task.completed is False

	task.mark_complete()

	assert task.completed is True


def test_task_addition_increases_pet_task_count() -> None:
	pet = Pet(
		pet_id="pet-1",
		name="Mochi",
		species="dog",
		breed="Shiba Inu",
		weight_kg=10.5,
	)

	starting_count = len(pet.tasks)

	task = Task(
		task_id="task-2",
		pet_id=pet.pet_id,
		description="Evening feeding",
		duration_minutes=10,
		priority="medium",
	)
	pet.add_task(task)

	assert len(pet.tasks) == starting_count + 1


def test_scheduler_sort_by_time_orders_due_times_and_puts_none_last() -> None:
	scheduler = Scheduler()
	task_late = Task(
		task_id="task-late",
		pet_id="pet-1",
		description="Late task",
		duration_minutes=15,
		priority="medium",
		due_time=time(10, 0),
	)
	task_early = Task(
		task_id="task-early",
		pet_id="pet-1",
		description="Early task",
		duration_minutes=15,
		priority="medium",
		due_time=time(8, 0),
	)
	task_anytime = Task(
		task_id="task-anytime",
		pet_id="pet-1",
		description="Anytime task",
		duration_minutes=15,
		priority="medium",
		due_time=None,
	)

	sorted_tasks = scheduler.sort_by_time([task_late, task_anytime, task_early])

	assert [task.task_id for task in sorted_tasks] == [
		"task-early",
		"task-late",
		"task-anytime",
	]


def test_build_daily_plan_returns_tasks_in_due_time_order() -> None:
	owner = Owner(
		owner_id="owner-1",
		name="Jordan",
		time_available_min_per_day=120,
	)
	pet = Pet(
		pet_id="pet-1",
		name="Mochi",
		species="dog",
		breed="Shiba Inu",
		weight_kg=10.5,
	)
	pet.add_task(
		Task(
			task_id="task-noon",
			pet_id=pet.pet_id,
			description="Noon walk",
			duration_minutes=20,
			priority="high",
			due_time=time(12, 0),
		)
	)
	pet.add_task(
		Task(
			task_id="task-morning",
			pet_id=pet.pet_id,
			description="Morning feeding",
			duration_minutes=10,
			priority="medium",
			due_time=time(8, 0),
		)
	)
	owner.add_pet(pet)

	scheduler = Scheduler()
	plan = scheduler.build_daily_plan(owner, date(2026, 3, 29), current_time=time(6, 0))

	assert [task.task_id for task in plan] == ["task-morning", "task-noon"]


def test_filter_tasks_by_completion_status() -> None:
	pet = Pet(
		pet_id="pet-1",
		name="Mochi",
		species="dog",
		breed="Shiba Inu",
		weight_kg=10.5,
	)
	task_done = Task(
		task_id="task-done",
		pet_id=pet.pet_id,
		description="Done task",
		duration_minutes=10,
		priority="low",
		completed=True,
	)
	task_pending = Task(
		task_id="task-pending",
		pet_id=pet.pet_id,
		description="Pending task",
		duration_minutes=10,
		priority="low",
	)

	scheduler = Scheduler()
	filtered = scheduler.filter_tasks(
		tasks=[task_done, task_pending],
		pets=[pet],
		completed=True,
	)

	assert [task.task_id for task in filtered] == ["task-done"]


def test_filter_tasks_by_pet_name_and_completion_status() -> None:
	mochi = Pet(
		pet_id="pet-1",
		name="Mochi",
		species="dog",
		breed="Shiba Inu",
		weight_kg=10.5,
	)
	luna = Pet(
		pet_id="pet-2",
		name="Luna",
		species="cat",
		breed="Domestic Short Hair",
		weight_kg=4.2,
	)
	task_mochi_done = Task(
		task_id="task-mochi-done",
		pet_id=mochi.pet_id,
		description="Mochi done",
		duration_minutes=10,
		priority="medium",
		completed=True,
	)
	task_mochi_pending = Task(
		task_id="task-mochi-pending",
		pet_id=mochi.pet_id,
		description="Mochi pending",
		duration_minutes=10,
		priority="medium",
		completed=False,
	)
	task_luna_done = Task(
		task_id="task-luna-done",
		pet_id=luna.pet_id,
		description="Luna done",
		duration_minutes=10,
		priority="medium",
		completed=True,
	)

	scheduler = Scheduler()
	filtered = scheduler.filter_tasks(
		tasks=[task_mochi_done, task_mochi_pending, task_luna_done],
		pets=[mochi, luna],
		completed=True,
		pet_name="mochi",
	)

	assert [task.task_id for task in filtered] == ["task-mochi-done"]


def test_mark_task_complete_creates_next_daily_task() -> None:
	owner = Owner(
		owner_id="owner-1",
		name="Jordan",
		time_available_min_per_day=120,
	)
	pet = Pet(
		pet_id="pet-1",
		name="Mochi",
		species="dog",
		breed="Shiba Inu",
		weight_kg=10.5,
	)
	daily_task = Task(
		task_id="task-daily",
		pet_id=pet.pet_id,
		description="Daily walk",
		duration_minutes=20,
		priority="high",
		frequency="daily",
		due_time=time(8, 0),
	)
	pet.add_task(daily_task)
	owner.add_pet(pet)

	scheduler = Scheduler()
	completed = scheduler.mark_task_complete(owner, "task-daily", completed_on=date(2026, 3, 29))

	assert completed is True
	assert daily_task.completed is True
	assert len(pet.tasks) == 2
	next_task = pet.tasks[1]
	assert next_task.task_id == "task-daily-next-2026-03-30"
	assert next_task.completed is False
	assert next_task.frequency == "daily"
	assert next_task.scheduled_for == date(2026, 3, 30)


def test_mark_task_complete_creates_next_weekly_task() -> None:
	owner = Owner(
		owner_id="owner-1",
		name="Jordan",
		time_available_min_per_day=120,
	)
	pet = Pet(
		pet_id="pet-1",
		name="Mochi",
		species="dog",
		breed="Shiba Inu",
		weight_kg=10.5,
	)
	weekly_task = Task(
		task_id="task-weekly",
		pet_id=pet.pet_id,
		description="Weekly grooming",
		duration_minutes=30,
		priority="medium",
		frequency="weekly",
		due_time=time(15, 0),
		scheduled_for=date(2026, 3, 29),
	)
	pet.add_task(weekly_task)
	owner.add_pet(pet)

	scheduler = Scheduler()
	completed = scheduler.mark_task_complete(owner, "task-weekly", completed_on=date(2026, 3, 29))

	assert completed is True
	assert len(pet.tasks) == 2
	next_task = pet.tasks[1]
	assert next_task.task_id == "task-weekly-next-2026-04-05"
	assert next_task.frequency == "weekly"
	assert next_task.scheduled_for == date(2026, 4, 5)


def test_detect_time_conflicts_for_same_pet() -> None:
	scheduler = Scheduler()
	task_a = Task(
		task_id="task-a",
		pet_id="pet-1",
		description="Walk",
		duration_minutes=20,
		priority="high",
		due_time=time(9, 0),
	)
	task_b = Task(
		task_id="task-b",
		pet_id="pet-1",
		description="Feed",
		duration_minutes=10,
		priority="medium",
		due_time=time(9, 0),
	)
	task_c = Task(
		task_id="task-c",
		pet_id="pet-1",
		description="Play",
		duration_minutes=15,
		priority="low",
		due_time=time(10, 0),
	)

	conflicts = scheduler.detect_time_conflicts([task_a, task_b, task_c])

	assert len(conflicts) == 1
	assert conflicts[0]["due_time"] == time(9, 0)
	assert conflicts[0]["same_pet"] is True
	assert set(conflicts[0]["task_ids"]) == {"task-a", "task-b"}


def test_detect_time_conflicts_for_different_pets() -> None:
	scheduler = Scheduler()
	task_a = Task(
		task_id="task-a",
		pet_id="pet-1",
		description="Dog walk",
		duration_minutes=20,
		priority="high",
		due_time=time(18, 0),
	)
	task_b = Task(
		task_id="task-b",
		pet_id="pet-2",
		description="Cat meds",
		duration_minutes=5,
		priority="high",
		due_time=time(18, 0),
	)

	conflicts = scheduler.detect_time_conflicts([task_a, task_b])

	assert len(conflicts) == 1
	assert conflicts[0]["due_time"] == time(18, 0)
	assert conflicts[0]["same_pet"] is False
	assert set(conflicts[0]["pet_ids"]) == {"pet-1", "pet-2"}


def test_get_conflict_warnings_returns_messages_without_raising() -> None:
	scheduler = Scheduler()
	task_a = Task(
		task_id="task-a",
		pet_id="pet-1",
		description="Dog walk",
		duration_minutes=20,
		priority="high",
		due_time=time(18, 0),
	)
	task_b = Task(
		task_id="task-b",
		pet_id="pet-2",
		description="Cat meds",
		duration_minutes=5,
		priority="high",
		due_time=time(18, 0),
	)

	warnings = scheduler.get_conflict_warnings(
		tasks=[task_a, task_b],
		pet_name_by_id={"pet-1": "Mochi", "pet-2": "Luna"},
	)

	assert len(warnings) == 1
	assert "Warning:" in warnings[0]
	assert "18:00" in warnings[0]
	assert "Mochi" in warnings[0]
	assert "Luna" in warnings[0]


def test_get_conflict_warnings_returns_empty_list_when_no_conflicts() -> None:
	scheduler = Scheduler()
	task_a = Task(
		task_id="task-a",
		pet_id="pet-1",
		description="Dog walk",
		duration_minutes=20,
		priority="high",
		due_time=time(18, 0),
	)
	task_b = Task(
		task_id="task-b",
		pet_id="pet-2",
		description="Cat meds",
		duration_minutes=5,
		priority="high",
		due_time=time(19, 0),
	)

	warnings = scheduler.get_conflict_warnings([task_a, task_b])

	assert warnings == []


def test_load_custom_documents_reads_text_files(tmp_path) -> None:
	first = tmp_path / "dog_notes.txt"
	second = tmp_path / "cat_notes.txt"
	first.write_text("Dog feeding should be consistent.", encoding="utf-8")
	second.write_text("Cats benefit from short play sessions.", encoding="utf-8")

	documents = load_custom_documents(source_dir=tmp_path)

	assert set(documents.keys()) == {"dog_notes.txt", "cat_notes.txt"}
	assert "consistent" in documents["dog_notes.txt"]


def test_retrieve_relevant_context_prefers_matching_source() -> None:
	knowledge_base = "General pet care guidance."
	extra_documents = {
		"dog_science_notes.txt": "Dogs need routine feeding and water before exercise.",
		"cat_science_notes.txt": "Cats often prefer smaller, more frequent meals.",
	}

	retrieved = retrieve_relevant_context(
		query="dog feeding and exercise timing",
		knowledge_base=knowledge_base,
		extra_documents=extra_documents,
		top_k=2,
	)

	assert retrieved
	assert retrieved[0]["source"] == "dog_science_notes.txt"
	assert "feeding" in retrieved[0]["text"].lower() or "exercise" in retrieved[0]["text"].lower()
