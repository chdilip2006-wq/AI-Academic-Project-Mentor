# Project health calculation

Health is recalculated when a milestone is updated or a weekly progress report or risk assessment is saved. The API stores the resulting `health` and `overallProgress` on the project.

- **Overall progress** is the rounded arithmetic mean of milestone percentages, clamped to 0–100. With no milestones, the previously stored project percentage is retained.
- **Completed** applies when every existing milestone is marked completed or overall progress reaches 100%.
- **At Risk** applies when an unfinished milestone is past its due date, any milestone is marked delayed, or a stored risk assessment contains a high-severity/high-probability risk.
- **Needs Attention** applies when a progress report describes a challenge and no higher-priority condition applies.
- **On Track** is the default when none of the above conditions applies.

These are transparent rules-based indicators, not predictions. Faculty dashboards use the same stored health label and also display delayed milestones and AI summaries.
