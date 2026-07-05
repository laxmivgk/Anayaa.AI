# Privacy

Anayaa is designed as a local-first app. In the default local setup, the app runs on your machine and your browser talks to `http://127.0.0.1:8000`.

## Default Local-First Behavior

By default:

- The web app is served locally.
- User accounts are stored in local PostgreSQL.
- Sessions, rate limits, and cache entries are stored in local Redis.
- Scripture retrieval uses local corpus data and local Milvus Lite data.
- Embeddings and model assets are cached locally after setup.
- Guidance synthesis uses local Ollama models.
- Cloud LLM routing is not used unless you configure a cloud key.

## Data Stored Locally

Anayaa may store local records such as:

- login user records and password hashes
- session state
- submitted dilemmas after PII scrubbing
- retrieved citations
- guidance outputs
- audit and grounding scores
- feedback records
- request energy and latency metrics

These are stored in local PostgreSQL and Redis according to the app's retention settings.

## Optional Cloud Routing

If you configure a cloud provider key such as `GEMINI_API_KEY`, selected planning or synthesis requests may be sent to that provider depending on the configured routing behavior. Do not enable cloud routing unless you understand and accept that provider's data handling terms.

## Sensitive Information

Avoid entering highly sensitive personal information, including:

- full names of private people
- addresses
- phone numbers
- government IDs
- medical record details
- legal case details
- financial account details

Anayaa includes sanitizer and PII-scrubbing protections, but no automated filter is perfect.

## Public Beta Note

This project is still a technical public-beta candidate. Review the code, configuration, logs, and retention settings before using it with sensitive real-world dilemmas.
