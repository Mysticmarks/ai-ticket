# Secrets management

Create `ai_ticket_auth_token.txt` in this directory with one bearer token per line. The Docker Compose file mounts it as a Docker secret and the Flask app reads it via the `AI_TICKET_AUTH_TOKEN_FILE` environment variable.

Example:

```
# ops/secrets/ai_ticket_auth_token.txt
my-long-lived-token
another-rotation-token
```

The actual secret file is ignored by Git. Use the `ai_ticket_auth_token.txt.example` helper as a template when preparing new environments.
