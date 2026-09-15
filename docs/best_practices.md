# Best Practices — Physio Scheduler

## Goal

- Define how to work in this project so that everything written and pushed
  stays secure, readable and efficient.

## Acceptance Criteria

When working on a task there are three types:

1. New feature/create something → `feature`/`feat`
2. Modify something already created → `refactor`
3. Fix a bug → `bugfix`/`fix`

Every branch name must follow the pattern `<type>/PS-X/<task-name>`.
`PS` stands for Physio Scheduler, and `X` is the task number defined in the
project task list below.

In commits use `feat` instead of `feature` and `bugfix` instead of `fix`,
since `fix` is reserved for when a `feature` PR, for example, needs a
small correction along the way.

## Usage Examples

When starting a new task, always create a separate branch — never push
changes directly to `main`. Depending on the type of task, the branch
name should be:

1. Feature → branch name: `feature/PS-x/branch-name`
2. Refactor → branch name: `refactor/PS-x/branch-name`
3. Bugfix → branch name: `bugfix/PS-x/branch-name`

For commits:

1. Feature → `"feat: commit message"`
2. Refactor → `"refactor: commit message"`
3. Bugfix → `"bugfix: commit message"`
4. If a `feature` or `refactor` PR needs a small correction, use
   `"fix: commit message"`

## Project Tasks and Branches

Each `PS-X` item represents one task. Every task must be developed in its own
branch and submitted through its own Pull Request to `main`.

### Database — Aday

| Task | Branch | Scope |
|---|---|---|
| PS-1 | `feature/PS-1/database-models` | Create the `User`, `Resource`, `Appointment`, and `AppointmentResource` models. |
| PS-2 | `feature/PS-2/database-migrations` | Set up and create the database migrations. |
| PS-3 | `feature/PS-3/inventory-seed` | Create the initial resource inventory seed. |

### Backend — Diego

| Task | Branch | Scope |
|---|---|---|
| PS-4 | `feature/PS-4/backend-blueprints` | Create and register the auth, student, physio, and API Blueprints. |
| PS-5 | `feature/PS-5/authentication` | Implement registration, login, logout, and Flask-Login. |
| PS-6 | `feature/PS-6/appointment-availability` | Implement the appointment and resource availability logic. |
| PS-7 | `feature/PS-7/student-appointments` | Implement student appointment creation, listing, and cancellation. |
| PS-8 | `feature/PS-8/physio-management` | Implement the physio dashboard, appointment management, notes, and inventory. |
| PS-9 | `feature/PS-9/calendar-api` | Create the JSON events endpoint for FullCalendar. |
| PS-10 | `feature/PS-10/backend-security` | Add role permissions, route protection, and validation. |
| PS-11 | `feature/PS-11/backend-tests` | Add tests for authentication, appointments, availability, permissions, and the API. |

### Frontend — Vitor

| Task | Branch | Scope |
|---|---|---|
| PS-12 | `feature/PS-12/base-layout` | Create the base template, navigation, Bootstrap setup, and common styling. |
| PS-13 | `feature/PS-13/auth-templates` | Create the registration and login pages. |
| PS-14 | `feature/PS-14/student-templates` | Create the student appointments and new appointment pages. |
| PS-15 | `feature/PS-15/physio-dashboard` | Create the physio dashboard and appointment detail pages. |
| PS-16 | `feature/PS-16/inventory-interface` | Create the inventory management page. |
| PS-17 | `feature/PS-17/fullcalendar-interface` | Add and configure FullCalendar. |
| PS-18 | `feature/PS-18/responsive-design` | Make the interface responsive and improve accessibility. |

### Shared Tasks

| Task | Branch | Scope |
|---|---|---|
| PS-19 | `feature/PS-19/frontend-backend-integration` | Connect the templates, backend routes, and database. |
| PS-20 | `feature/PS-20/integration-tests` | Test the complete workflows and fix integration problems. |
| PS-21 | `feature/PS-21/production-configuration` | Prepare environment variables, the production database, and the WSGI server. |
| PS-22 | `feature/PS-22/application-deployment` | Deploy and verify the complete application. |
