# SSP&A Drift Definitions

## Overview
The SSP&A velocity interpolation method allows for the superposition of analytic elements, called "drifts", onto the kriged velocity field. These drifts represent features like pumping wells, line-sinks (e.g., rivers or drains), and no-flow boundaries.

Drifts are defined as a list of Python dictionaries passed to the `drifts` argument of `fit_sspa()`.

## Supported Drift Types

| Type | Aliases | Description |
|---|---|---|
| Well | `well` | A point sink or source. |
| Line-Sink | `linesink`, `line_sink`, `line-sink` | A line segment representing a sink or source (e.g., a river reach). |
| No-Flow | `noflow`, `no_flow`, `no-flow` | A line segment representing an impermeable boundary. |

## Required Keys

### Common Keys (All Types)
- `type`: The drift type (string, see aliases in the table above).
- `event`: String identifying the stress period or event (e.g., `"SS"`, `"1"`).
- `term`: String or integer identifying the term (integers are converted to strings internally).
- `name`: String identifier for the drift element.
- `value`: Float drift strength coefficient (e.g., pumping rate for wells, flow rate per unit length for line-sinks).

### Well-Specific Keys
- `x`: X-coordinate of the well.
- `y`: Y-coordinate of the well.

### Line-Specific Keys (linesink, noflow)
- `x1`: X-coordinate of the start point.
- `y1`: Y-coordinate of the start point.
- `x2`: X-coordinate of the end point.
- `y2`: Y-coordinate of the end point.

## Line Element Grouping
Line elements (`linesink` and `noflow`) are grouped together to form continuous polylines. Elements are considered part of the same group if they share the exact same combination of `(type, event, term, name)`.

## Validation Rules

The `fit_sspa()` function performs strict validation on the provided drift definitions.

### Unsupported Type
If a drift dictionary contains an unrecognized `type` value, a `ValueError` is raised:
`"drifts[{idx}] has unsupported type '{type}'. Supported types are: well, linesink, noflow"`

### Missing Required Key
If a required key is missing for a given drift type, a `ValueError` is raised:
`"drifts[{idx}] must be a dict with required keys: type, event, term, name, value"`

### Zero-Length Line Segment
For `linesink` and `noflow` drifts, the start and end points must not be identical. If they are, a `ValueError` is raised:
`"drifts[{idx}] has zero-length line geometry (x1,y1) == (x2,y2)"`

### Mixed Values in Group
All line segments within a group (sharing the same `type`, `event`, `term`, and `name`) must have the same `value`. If they differ, a `ValueError` is raised:
`"drifts[{idx}] has value {v1} but previous segment in same (type,event,term,name) group has value {v2}"`

### Array Length Mismatch (at fit time)
All input arrays in `SspaInputs` must have the same length as the number of cells in the grid.

## Runtime Capture Behavior
- **Well Capture**: Fully implemented. Particles entering the capture zone of an extraction well will be terminated.
- **Line-Sink / No-Flow Capture**: Deferred. While these elements influence the velocity field, explicit capture (termination) of particles at line-sinks or reflection at no-flow boundaries is not yet implemented in the tracking engine.

## Examples

### Well Drift
```python
well_drift = {
    "type": "well",
    "event": "SS",
    "term": 1,
    "name": "PW-1",
    "value": -500.0,  # Extraction rate
    "x": 1050.0,
    "y": 2050.0,
}
```

### Line-Sink Drift
```python
linesink_drift = {
    "type": "linesink",
    "event": "SS",
    "term": 2,
    "name": "RiverReachA",
    "value": -10.0,  # Flow rate per unit length
    "x1": 1000.0,
    "y1": 3000.0,
    "x2": 1500.0,
    "y2": 3200.0,
}
```

### No-Flow Drift
```python
noflow_drift = {
    "type": "noflow",
    "event": "SS",
    "term": 3,
    "name": "BedrockBoundary",
    "value": 0.0,
    "x1": 500.0,
    "y1": 500.0,
    "x2": 5000.0,
    "y2": 500.0,
}
```
