# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| 0.1.x | Yes |

## Reporting Vulnerabilities

If you discover a security vulnerability, please report it via [GitHub Issues](https://github.com/DrishtantKaushal/langfuse-mcp/issues) with the label `security`.

For sensitive disclosures, contact the maintainer directly through GitHub.

## API Key Handling

- API keys are passed as **environment variables** (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`)
- Keys are **never stored** in the repository, config files, or logs
- Keys are transmitted to the Langfuse API over HTTPS using Basic Authentication
- Enable **read-only mode** (`LANGFUSE_MCP_READ_ONLY=true`) to prevent write operations

## Security Considerations

- This server makes authenticated API calls to your Langfuse instance. Ensure your API keys have appropriate scopes.
- When using selective tool loading (`LANGFUSE_TOOLS`), only the specified tool groups are registered. This reduces the attack surface.
- The server runs locally as a stdio process. It does not expose any network endpoints.
- For self-hosted Langfuse instances, ensure your `LANGFUSE_HOST` URL uses HTTPS.
