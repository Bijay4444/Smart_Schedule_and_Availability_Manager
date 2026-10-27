# Smart Schedule Development Instructions

## Project Goal

Build a scheduling and availability management system for users
balancing classes, multiple jobs, and personal commitments.

The application should:

- manage recurring and one-time commitments
- identify scheduling conflicts
- calculate free time
- generate weekly work availability
- eventually integrate with Google Calendar

## Technology

- Python 3.13
- Django 6.1.2 (latest stable release verified on 2026-10-25)
- Django REST Framework
- PostgreSQL
- Django Templates
- Bootstrap
- pytest
- Git

When planning scheduling behavior or frontend changes, read
`docs/project_spec.md` for agreed scope and open decisions. Use `GLOSSARY.md`
for scheduling terminology.

## Architecture Rules

Business logic must not be placed directly in Django views.

Scheduling calculations belong in service modules.

External integrations must remain separate from core scheduling logic.

API endpoints should use Django REST Framework.

Database models should remain simple and normalized.

Do not add dependencies without explaining why they are necessary.

## Development Rules

For each task:

1. Explain the proposed change.
2. Identify files that will change.
3. Implement only the requested feature.
4. Add or update tests.
5. Run the relevant tests.
6. Explain what was implemented.

Do not implement unrelated features.

Do not rewrite working code unless necessary.

## Learning Requirement

This is a university project.

When implementing non-trivial logic, explain the reasoning
and architecture so the developer can understand and present it.

Do not hide important implementation decisions from the developer.
