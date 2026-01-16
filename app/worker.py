import asyncio

# This is a dedicated entrypoint for the worker and scheduler.
# In production, run:
#   python -m app.worker
# Or via CLI:
#   taskiq worker app.core.tkq:broker app.main:app
#   taskiq scheduler app.core.tkq:scheduler app.main:app


async def main():
    """Main entrypoint for starting the worker and scheduler combined if needed,
    or just as a placeholder for CLI usage documentation.
    """
    print("TaskIQ Worker/Scheduler entrypoint initialized.")
    # Usually you use the CLI, but we can provide a programmatic way if desired.
    # For now, this file serves as the discovery point for TaskIQ tasks.


if __name__ == "__main__":
    asyncio.run(main())
