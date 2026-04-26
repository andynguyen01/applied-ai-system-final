import uuid
from datetime import date, time

import streamlit as st

from pawpal_system import Owner, Pet, Scheduler, Task
from rag_validator import load_knowledge_base, validate_schedule


st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

# Create persistent objects in session state
if "owner" not in st.session_state:
    st.session_state.owner = Owner(
        owner_id="owner-1",
        name="Jordan",
        time_available_min_per_day=90,
        preferences={},
    )

if "scheduler" not in st.session_state:
    st.session_state.scheduler = Scheduler()

owner = st.session_state.owner
scheduler = st.session_state.scheduler

st.title("🐾 PawPal+")

st.markdown(
    """
Welcome to the PawPal+ app.

Now the UI is connected to your backend classes, so adding pets and tasks
actually updates the Owner, Pet, Task, and Scheduler objects.
"""
)

st.divider()

st.subheader("Owner Info")
owner.name = st.text_input("Owner name", value=owner.name)
owner.time_available_min_per_day = st.number_input(
    "Time available per day (minutes)",
    min_value=1,
    max_value=600,
    value=owner.time_available_min_per_day,
)

st.divider()

st.subheader("Add a Pet")
pet_name = st.text_input("Pet name", value="Mochi")
species = st.selectbox("Species", ["dog", "cat", "other"])
breed = st.text_input("Breed", value="Unknown")
weight_kg = st.number_input("Weight (kg)", min_value=0.1, max_value=100.0, value=5.0)
diet_plan = st.text_input("Diet plan", value="Normal diet")

if st.button("Add pet"):
    new_pet = Pet(
        pet_id=str(uuid.uuid4()),
        name=pet_name,
        species=species,
        breed=breed,
        weight_kg=float(weight_kg),
        diet_plan=diet_plan,
    )
    owner.add_pet(new_pet)
    st.success(f"{pet_name} was added successfully.")

if owner.pets:
    st.write("Current pets:")
    pet_table = [
        {
            "Name": pet.name,
            "Species": pet.species,
            "Breed": pet.breed,
            "Weight (kg)": pet.weight_kg,
        }
        for pet in owner.pets
    ]
    st.table(pet_table)
else:
    st.info("No pets added yet.")

st.divider()

st.subheader("Add a Task")

if owner.pets:
    pet_options = {pet.name: pet for pet in owner.pets}
    selected_pet_name = st.selectbox("Choose pet", list(pet_options.keys()))
    selected_pet = pet_options[selected_pet_name]

    col1, col2, col3 = st.columns(3)
    with col1:
        task_title = st.text_input("Task title", value="Morning walk")
    with col2:
        duration = st.number_input("Duration (minutes)", min_value=1, max_value=240, value=20)
    with col3:
        priority = st.selectbox("Priority", ["low", "medium", "high"], index=2)

    frequency = st.selectbox("Frequency", ["once", "daily", "weekly"], index=1)
    due_time_input = st.time_input("Due time", value=time(8, 0))
    task_type = st.text_input("Task type", value="general")

    if st.button("Add task"):
        new_task = Task(
            task_id=str(uuid.uuid4()),
            pet_id=selected_pet.pet_id,
            description=task_title,
            duration_minutes=int(duration),
            priority=priority,
            frequency=frequency,
            due_time=due_time_input,
            task_type=task_type,
        )
        selected_pet.add_task(new_task)
        st.success(f'Task "{task_title}" was added to {selected_pet.name}.')
else:
    st.info("Add a pet first before adding tasks.")

# Show all tasks
all_task_objects = []
for pet in owner.pets:
    for task in pet.tasks:
        all_task_objects.append(task)

if all_task_objects:
    pet_name_by_id = {pet.pet_id: pet.name for pet in owner.pets}
    sorted_tasks = scheduler.sort_by_time(all_task_objects)

    st.subheader("Task Dashboard")
    st.success(f"Loaded {len(sorted_tasks)} tasks sorted by due time.")

    completion_filter = st.selectbox(
        "Completion status",
        ["All", "Pending", "Completed"],
    )
    pet_filter = st.selectbox(
        "Pet filter",
        ["All pets"] + [pet.name for pet in owner.pets],
    )

    completed_arg = None
    if completion_filter == "Pending":
        completed_arg = False
    elif completion_filter == "Completed":
        completed_arg = True

    pet_name_arg = None if pet_filter == "All pets" else pet_filter

    filtered_tasks = scheduler.filter_tasks(
        tasks=sorted_tasks,
        pets=owner.pets,
        completed=completed_arg,
        pet_name=pet_name_arg,
    )

    filtered_task_table = [
        {
            "Pet": pet_name_by_id.get(task.pet_id, task.pet_id),
            "Task": task.description,
            "Duration": task.duration_minutes,
            "Priority": task.priority,
            "Frequency": task.frequency,
            "Due Time": task.due_time.strftime("%H:%M") if task.due_time else "--:--",
            "Completed": task.completed,
        }
        for task in filtered_tasks
    ]

    if filtered_task_table:
        st.table(filtered_task_table)
        st.success(f"Showing {len(filtered_tasks)} matching tasks.")
    else:
        st.warning("No tasks match the selected filters.")

    conflict_warnings = scheduler.get_conflict_warnings(filtered_tasks, pet_name_by_id)
    if conflict_warnings:
        for warning in conflict_warnings:
            st.warning(warning)
    else:
        st.success("No time conflicts detected for the current view.")
else:
    st.info("No tasks added yet.")

st.divider()

st.subheader("Build Schedule")

if st.button("Generate schedule"):
    today = date.today()
    plan = scheduler.build_daily_plan(owner, today)

    if plan:
        pet_name_by_id = {pet.pet_id: pet.name for pet in owner.pets}
        schedule_table = []
        for task in plan:
            schedule_table.append(
                {
                    "Time": task.due_time.strftime("%H:%M") if task.due_time else "--:--",
                    "Pet": pet_name_by_id.get(task.pet_id, task.pet_id),
                    "Task": task.description,
                    "Priority": task.priority,
                    "Duration": task.duration_minutes,
                }
            )

        st.success("Schedule generated successfully.")
        st.table(schedule_table)

        # RAG Validation: Check schedule against pet health knowledge
        st.divider()
        st.subheader("🔍 Health & Safety Validation")
        try:
            kb = load_knowledge_base()
            validation = validate_schedule(plan, owner.pets, kb)
            rag_info = validation.get("rag", {})
            workflow_steps = validation.get("workflow", [])
            
            if not validation["valid"]:
                st.error("⚠️ Schedule has potential health concerns:")
                warnings = validation.get("warnings", [])
                if not warnings:
                    warnings = [
                        "The validator flagged concerns but did not provide a structured warning list."
                    ]
                for warning in warnings:
                    st.error(f"  • {warning}")
            else:
                st.success("✅ Schedule validated - No health concerns detected.")
            
            if validation["optimizations"]:
                st.info("💡 Suggested improvements:")
                for opt in validation["optimizations"]:
                    st.write(f"  • {opt}")
            
            if validation["explanation"]:
                st.write(f"**Validation Summary:** {validation['explanation']}")

            if workflow_steps:
                with st.expander("Agentic Workflow (observable steps)"):
                    for step in workflow_steps:
                        st.write(f"**{step.get('step', 'Step')}** - {step.get('status', 'unknown')}")
                        st.caption(step.get("detail", ""))

            with st.expander("RAG Debug (How to verify it is running)"):
                st.write(f"Knowledge base characters loaded: {rag_info.get('kb_chars', len(kb))}")
                st.write(f"Gemini call executed: {rag_info.get('used', False)}")
                st.write(f"Model used: {rag_info.get('model_used', 'unknown')}")
                sources_used = rag_info.get("retrieved_sources", [])
                if sources_used:
                    st.write("Retrieved sources: " + ", ".join(sources_used))
                if rag_info.get("error"):
                    st.write(f"Gemini error: {rag_info.get('error')}")
                raw = rag_info.get("raw_response", "")
                if raw:
                    st.text_area(
                        "Raw Gemini response",
                        value=raw,
                        height=180,
                        disabled=True,
                    )
                kb_preview = kb[:400] + ("..." if len(kb) > 400 else "")
                st.text_area(
                    "Knowledge base preview used for retrieval",
                    value=kb_preview,
                    height=120,
                    disabled=True,
                )
        except Exception as e:
            st.warning(f"Could not run health validation: {str(e)}")

        st.divider()
        plan_conflict_warnings = scheduler.get_conflict_warnings(plan, pet_name_by_id)
        if plan_conflict_warnings:
            for warning in plan_conflict_warnings:
                st.warning(warning)
        else:
            st.success("No schedule conflicts detected.")

        st.markdown("### Why this plan")
        for line in scheduler.explain_plan().splitlines():
            st.write(f"- {line.replace('Included: ', '')}")

        st.divider()
        st.markdown("### Optimize schedule")
        optimized = scheduler.optimize_schedule(owner, today)
        optimized_tasks = optimized.get("tasks", [])

        if optimized_tasks:
            optimized_table = []
            for task in optimized_tasks:
                optimized_table.append(
                    {
                        "Optimized Time": task.due_time.strftime("%H:%M") if task.due_time else "--:--",
                        "Pet": pet_name_by_id.get(task.pet_id, task.pet_id),
                        "Task": task.description,
                        "Priority": task.priority,
                        "Duration": task.duration_minutes,
                    }
                )

            st.success("Optimized schedule generated with conflict-aware time adjustments.")
            st.table(optimized_table)

            optimized_conflicts = scheduler.get_conflict_warnings(optimized_tasks, pet_name_by_id)
            if optimized_conflicts:
                st.warning("Some overlaps still remain after optimization:")
                for warning in optimized_conflicts:
                    st.warning(warning)
            else:
                st.success("No schedule conflicts detected in optimized plan.")

            st.caption(
                "Resolved conflicts: "
                + str(optimized.get("conflicts_resolved", 0))
                + " | Healthy-window adjustments: "
                + str(optimized.get("window_adjustments", 0))
            )

            st.info("Optimization notes")
            for note in optimized.get("adjustments", []):
                st.write(f"  • {note}")
        else:
            st.warning("No tasks available for optimization.")
    else:
        st.warning("No tasks were selected for today.")