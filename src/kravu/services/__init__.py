"""Services layer: the use cases where all business logic lives.

Each service is one business operation (SourceJobs, ScoreJobFit, TailorResume,
...). Services orchestrate domain ports and depend only on the domain layer —
never on concrete infrastructure.
"""
