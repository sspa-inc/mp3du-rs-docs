# Batch Simulation Example

Running multiple particles in a single simulation call.

## Example

```python
import json
import mp3du

# Assume grid, field are already set up (see Minimal Python Script example)
# grid = mp3du.build_grid(...)
# field = mp3du.fit_waterloo(...)

# Load simulation configuration
config = mp3du.SimulationConfig.from_json(json.dumps({
    "velocity_method": "Waterloo",
    "solver": "DormandPrince",
    "adaptive": {
        "tolerance": 1e-6,
        "safety": 0.9,
        "alpha": 0.2,
        "min_scale": 0.2,
        "max_scale": 5.0,
        "max_rejects": 10,
        "min_dt": 1e-10,
        "euler_dt": 1.0
    },
    "dispersion": {"method": "None"},
    "retardation_enabled": False,
    "capture": {
        "max_time": 365250.0,
        "max_steps": 1000000,
        "stagnation_velocity": 1e-12,
        "stagnation_limit": 100
    },
    "initial_dt": 1.0,
    "max_dt": 100.0,
    "direction": 1.0
}))

# Define multiple particle starting positions
particles = [
    mp3du.ParticleStart(id=0, x=100.0, y=200.0, z=50.0, cell_id=42, initial_dt=1.0),
    mp3du.ParticleStart(id=1, x=150.0, y=250.0, z=45.0, cell_id=58, initial_dt=1.0),
    mp3du.ParticleStart(id=2, x=200.0, y=300.0, z=40.0, cell_id=73, initial_dt=1.0),
    mp3du.ParticleStart(id=3, x=250.0, y=350.0, z=35.0, cell_id=91, initial_dt=1.0),
    mp3du.ParticleStart(id=4, x=300.0, y=400.0, z=30.0, cell_id=105, initial_dt=1.0),
]

# Run all particles in a single call
results = mp3du.run_simulation(config, field, particles, parallel=True)

# Print per-particle results
for r in results:
    print(f"Particle {r.particle_id}: status={r.final_status}, steps={len(r)}")
```

## Processing Results in Bulk

```python
from collections import Counter

# Count particles by final status
statuses = Counter(r.final_status for r in results)
print(statuses)
# e.g. Counter({'terminated': 3, 'captured': 2})

# Extract trajectory records for all particles
all_records = []
for r in results:
    records = r.to_records()
    all_records.extend(records)

print(f"Total trajectory points: {len(all_records)}")
```

## Generating Particle Starts Programmatically

```python
# Create a grid of starting positions
particles = []
pid = 0
for x in range(100, 500, 50):
    for y in range(200, 600, 50):
        particles.append(
            mp3du.ParticleStart(
                id=pid,
                x=float(x),
                y=float(y),
                z=25.0,
                cell_id=0,  # Will be resolved by the engine
                initial_dt=1.0,
            )
        )
        pid += 1

results = mp3du.run_simulation(config, field, particles, parallel=True)
print(f"Tracked {len(results)} particles")
```

## Performance Notes

!!! tip
    The simulation engine uses Rayon for parallel dispatch internally. Pass `parallel=True` (the default) and provide all particles in a single `run_simulation` call for best throughput.

!!! warning "Memory"
    Each particle stores its full trajectory. For large particle sets (>10,000), consider processing results in batches or extracting only the data you need via `to_records()`.

## See Also

- [Minimal Python Script](minimal-python-script.md) — Single particle example
- [Running Simulations](../guides/running-simulations.md) — Full workflow guide
