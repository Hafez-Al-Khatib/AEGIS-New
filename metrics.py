from prometheus_client import Counter, Histogram

AGENT_CALLS = Counter("agent_calls_total", "Number of agent calls", ["agent_name"])
AGENT_LATENCY = Histogram("agent_latency_seconds", "Latency of agent calls", ["agent_name"])
