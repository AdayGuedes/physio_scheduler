# Frontend tasks: student booking

Each task file is self-contained: objective, acceptance, constraints and notes.
Before implementing a task, read `../decisions.md` and the contracts it lists.

| ID | Task | Depends on | Status |
|---|---|---|---|
| T1 | Fix appointment duration at 30 minutes | — | Done |
| T2 | Free start times endpoint | T1 | Done |
| T3 | Available equipment endpoint | — | Done |
| T4 | Optional physio and physio assignment | T1 | Done |
| T5 | Booking page and booking JavaScript | T2, T3, T4 | Pending |
| T6 | Student appointment list and cancel | — | Pending |
| T7 | Enforce the start-time grid on booking | T4 | Pending |

## Order

1. Start T1, T3 and T6 in parallel. They touch different files.
2. Then T2 and T4. Both change the backend booking code, so they run after T1 is merged.
3. Then T5, once T2, T3 and T4 are merged.
4. T7 can run in parallel with T5, once T4 is merged. It changes only the backend booking validation.

## Open items

None. Clinic hours (08:00 to 18:00) and the reason list are in `../decisions.md`.
