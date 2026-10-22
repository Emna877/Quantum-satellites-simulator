# Examples

Standalone runnable demonstrations. These are not regression tests.

| File | Description |
|---|---|
| `demo_phase1_engine.py` | Early asyncio engine demonstration (uses deprecated `datetime.utcnow`). Preserved for reference; use `python -m simulation.engine --offline --seconds 60` for the current engine. |
| `demo_phase2_events.py` | Early event system demonstration. Preserved for reference; use `scripts/test_engine_events.py` for tested event scenarios. |
| `demo_phase2_events_simple.py` | Simplified version of the above, without Orekit. |

Run the tested regression suite instead:

```powershell
python -m unittest scripts.test_runtime_config scripts.test_engine_events scripts.test_orbit scripts.test_experiment_schema scripts.test_communication
```
