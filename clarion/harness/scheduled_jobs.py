"""LLM-scheduled jobs — recurring tasks the LLM can create and manage.

Jobs are stored in the brain at `_jobs/`. Each job has:
- A schedule (cron-like: daily, weekly, hourly, or specific intervals)
- A description of what the job does
- Either a custom tool name to call, or a prompt for the LLM to execute

Jobs are checked by a background worker and executed when due.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta

from clarion.brain.manager import BrainManager
from clarion.providers.base import ToolDef

logger = logging.getLogger(__name__)

JOBS_FILE = "_jobs/scheduled.json"


def _load_jobs(brain: BrainManager) -> list[dict]:
    content = brain.read_file(JOBS_FILE)
    if not content:
        return []
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return []


def _save_jobs(brain: BrainManager, jobs: list[dict]) -> None:
    brain.write_file(JOBS_FILE, json.dumps(jobs, indent=2))


def create_job(
    brain: BrainManager,
    name: str,
    description: str,
    schedule: str,
    action_type: str,
    action: str,
) -> dict:
    """Create a new scheduled job.

    Args:
        name: unique job name
        description: what the job does
        schedule: "daily", "weekly", "hourly", or "every_N_hours"
        action_type: "tool" (call a tool) or "prompt" (run an LLM prompt)
        action: tool name or prompt text
    """
    jobs = _load_jobs(brain)

    # Check for duplicate
    existing = [j for j in jobs if j.get("name") == name]
    if existing:
        # Update existing job
        for j in jobs:
            if j["name"] == name:
                j["description"] = description
                j["schedule"] = schedule
                j["action_type"] = action_type
                j["action"] = action
                j["updated_at"] = datetime.now(timezone.utc).isoformat()
        _save_jobs(brain, jobs)
        logger.info("Scheduled job updated: %s (%s)", name, schedule)
        return {"status": "updated", "name": name, "schedule": schedule}

    job = {
        "name": name,
        "description": description,
        "schedule": schedule,
        "action_type": action_type,
        "action": action,
        "enabled": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_run": None,
        "next_run": _calculate_next_run(schedule),
        "run_count": 0,
    }

    jobs.append(job)
    _save_jobs(brain, jobs)
    logger.info("Scheduled job created: %s (%s)", name, schedule)
    return {"status": "created", "name": name, "schedule": schedule}


def get_due_jobs(brain: BrainManager) -> list[dict]:
    """Get jobs that are due to run."""
    now = datetime.now(timezone.utc)
    jobs = _load_jobs(brain)
    due = []

    for job in jobs:
        if not job.get("enabled", True):
            continue
        next_run = job.get("next_run")
        if next_run:
            try:
                next_dt = datetime.fromisoformat(next_run)
                if next_dt <= now:
                    due.append(job)
            except ValueError:
                continue

    return due


def mark_job_run(brain: BrainManager, name: str) -> None:
    """Mark a job as just run and calculate the next run time."""
    jobs = _load_jobs(brain)
    for job in jobs:
        if job["name"] == name:
            job["last_run"] = datetime.now(timezone.utc).isoformat()
            job["run_count"] = job.get("run_count", 0) + 1
            job["next_run"] = _calculate_next_run(job["schedule"])
            break
    _save_jobs(brain, jobs)


def list_jobs(brain: BrainManager) -> list[dict]:
    """List all scheduled jobs."""
    return _load_jobs(brain)


def _calculate_next_run(schedule: str) -> str:
    """Calculate the next run time based on schedule expression.

    Supported expressions:
    - "hourly" → every hour
    - "daily" → every day at 9am
    - "daily_at_HH:MM" → every day at specific time (e.g., "daily_at_14:30")
    - "weekly" → every Monday at 9am
    - "weekly_DAY" → every specific day at 9am (e.g., "weekly_friday")
    - "monthly_N" → Nth day of month at 9am (e.g., "monthly_1", "monthly_15")
    - "first_DAY_of_month" → first specific weekday of month (e.g., "first_monday_of_month")
    - "last_DAY_of_month" → last specific weekday of month
    - "every_N_hours" → every N hours (e.g., "every_4_hours")
    - "every_N_minutes" → every N minutes (e.g., "every_30_minutes")
    """
    now = datetime.now(timezone.utc)
    DAY_NAMES = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                 "friday": 4, "saturday": 5, "sunday": 6}

    try:
        if schedule == "hourly":
            return (now + timedelta(hours=1)).isoformat()

        elif schedule == "daily":
            return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0).isoformat()

        elif schedule.startswith("daily_at_"):
            time_str = schedule.replace("daily_at_", "")
            hour, minute = int(time_str.split(":")[0]), int(time_str.split(":")[1])
            next_run = now.replace(hour=hour, minute=minute, second=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            return next_run.isoformat()

        elif schedule.startswith("weekly_"):
            day_name = schedule.replace("weekly_", "").lower()
            target_day = DAY_NAMES.get(day_name, 0)
            days_ahead = (target_day - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return (now + timedelta(days=days_ahead)).replace(
                hour=9, minute=0, second=0
            ).isoformat()

        elif schedule == "weekly":
            days_ahead = (0 - now.weekday()) % 7  # next Monday
            if days_ahead == 0:
                days_ahead = 7
            return (now + timedelta(days=days_ahead)).replace(
                hour=9, minute=0, second=0
            ).isoformat()

        elif schedule.startswith("monthly_"):
            day_num = int(schedule.replace("monthly_", ""))
            next_month = now.month + 1 if now.day >= day_num else now.month
            next_year = now.year + (1 if next_month > 12 else 0)
            next_month = next_month if next_month <= 12 else 1
            return datetime(next_year, next_month, min(day_num, 28),
                           9, 0, 0, tzinfo=timezone.utc).isoformat()

        elif schedule.startswith("first_") and schedule.endswith("_of_month"):
            day_name = schedule.replace("first_", "").replace("_of_month", "").lower()
            target_day = DAY_NAMES.get(day_name, 0)
            # Find first occurrence of target weekday in next month
            if now.month == 12:
                first_of_next = datetime(now.year + 1, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
            else:
                first_of_next = datetime(now.year, now.month + 1, 1, 9, 0, 0, tzinfo=timezone.utc)
            days_ahead = (target_day - first_of_next.weekday()) % 7
            return (first_of_next + timedelta(days=days_ahead)).isoformat()

        elif schedule.startswith("last_") and schedule.endswith("_of_month"):
            day_name = schedule.replace("last_", "").replace("_of_month", "").lower()
            target_day = DAY_NAMES.get(day_name, 0)
            # Find last occurrence of target weekday in current/next month
            if now.month == 12:
                last_of_month = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
            else:
                last_of_month = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
            days_back = (last_of_month.weekday() - target_day) % 7
            result = last_of_month - timedelta(days=days_back)
            result = result.replace(hour=9, minute=0, second=0)
            if result <= now:
                # Move to next month
                if now.month >= 11:
                    last_of_month = datetime(now.year + 1, (now.month % 12) + 2, 1, tzinfo=timezone.utc) - timedelta(days=1)
                else:
                    last_of_month = datetime(now.year, now.month + 2, 1, tzinfo=timezone.utc) - timedelta(days=1)
                days_back = (last_of_month.weekday() - target_day) % 7
                result = last_of_month - timedelta(days=days_back)
                result = result.replace(hour=9, minute=0, second=0)
            return result.isoformat()

        elif schedule.startswith("every_") and schedule.endswith("_hours"):
            hours = int(schedule.replace("every_", "").replace("_hours", ""))
            return (now + timedelta(hours=hours)).isoformat()

        elif schedule.startswith("every_") and schedule.endswith("_minutes"):
            minutes = int(schedule.replace("every_", "").replace("_minutes", ""))
            return (now + timedelta(minutes=minutes)).isoformat()

    except (ValueError, IndexError):
        pass

    # Default: tomorrow at 9am
    return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0).isoformat()


# -- Built-in tool for LLM to create jobs --

class ScheduleJobTool:
    """Tool that lets the LLM schedule recurring jobs."""

    def __init__(self, brain: BrainManager):
        self._brain = brain

    @property
    def name(self) -> str:
        return "schedule_job"

    @property
    def definition(self) -> ToolDef:
        return ToolDef(
            name="schedule_job",
            description=(
                "Schedule a recurring job. The job runs on a schedule and either "
                "calls a tool or executes an LLM prompt. "
                "Schedules: 'hourly', 'daily', 'weekly', 'every_N_hours'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Unique job name"},
                    "description": {"type": "string", "description": "What the job does"},
                    "schedule": {
                        "type": "string",
                        "description": "Schedule: 'hourly', 'daily', 'weekly', 'every_4_hours'",
                    },
                    "action_type": {
                        "type": "string",
                        "enum": ["tool", "prompt"],
                        "description": "'tool' to call a tool, 'prompt' to run an LLM prompt",
                    },
                    "action": {
                        "type": "string",
                        "description": "Tool name (for action_type=tool) or prompt text (for action_type=prompt)",
                    },
                },
                "required": ["name", "description", "schedule", "action_type", "action"],
            },
        )

    async def execute(self, arguments: dict) -> str:
        result = create_job(
            self._brain,
            name=arguments.get("name", ""),
            description=arguments.get("description", ""),
            schedule=arguments.get("schedule", "daily"),
            action_type=arguments.get("action_type", "prompt"),
            action=arguments.get("action", ""),
        )
        return json.dumps(result)
