# Runtime Vertical Slice Review Packet

Review the generated runtime traces and evidence objects before treating any
worker output as accepted evidence.

Expected checks:

- `async-research runtime validate research_ops`
- `async-research runtime inspect-evidence research_ops EVID-000001`
- `async-research runtime inspect-evidence research_ops EVID-000002`
