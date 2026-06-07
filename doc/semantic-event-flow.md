# Semantic Event Flow

SmartCore handles natural-language event CRUD with a two-stage flow:

1. Parse the user command into an operation, a structured query range, and write fields.
2. Query the database with compact structured filters.
3. Ask the LLM to choose from the returned compact candidates only.
4. Reply directly for query operations, or create a confirmation card for update/delete.
5. After a card confirm or reject succeeds, recall the original card message so stale pending cards do not remain clickable.

To reduce hallucination, first-stage event type filters are treated as hints. For update/delete/query, if the first-stage parser emits a concrete `event_type`, the handler must still run the semantic selection over the same range with `event_type=all` so a guessed category cannot hide the real target. The second-stage selector must only choose ids present in the candidate list and should return `ambiguous` instead of guessing when title/time intent is weak.
