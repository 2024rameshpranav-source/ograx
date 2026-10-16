# AquaSignal Data Directory

This directory stores durable local application data.

## SQLite Database
- Database file: `aquasignal.db`
- Tables:
  - `reports`: Citizen observations and ground-truth validation records.
  - `predictions`: Model prediction logs and inference audit records.

Configurable via `DATABASE_URL` in `.env` (default: `sqlite:///./backend/app/data/aquasignal.db`).
Database files (`*.db`) are ignored in version control via `.gitignore`.
