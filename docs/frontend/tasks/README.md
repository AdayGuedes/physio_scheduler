# Frontend tasks: student booking

Each task file is self-contained: objective, acceptance, constraints and notes.
Before implementing a task, read `../decisions.md` and the contracts it lists.

| ID | Task | Owner | Depends on | Status |
|---|---|---|---|---|
| T1 | Fix appointment duration at 30 minutes | Diego | — | Pending |
| T2 | Free start times endpoint | Diego | T1, clinic opening hours (open) | Blocked |
| T3 | Available equipment endpoint | Aday | — | Pending |
| T4 | Optional physio and physio assignment | Diego | T1 | Pending |
| T5 | Booking page and booking JavaScript | Aday | T2, T3, T4, reason list (open) | Blocked |
| T6 | Student appointment list and cancel | Aday | — | Pending |

## Order

1. Start T1, T3 and T6 in parallel. They touch different files.
2. Then T2 and T4. Both change the backend booking code, so they run after T1 is merged.
3. Then T5, once T2, T3 and T4 are merged.

## Open items

- Clinic opening hours: blocks T2. Without them, the candidate start times have no grid.
- Fixed list of reasons for the `reason` dropdown: blocks T5.
