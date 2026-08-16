"""
Thin wrapper around openeo.connect() + OIDC login, shared by both scripts.
"""
import openeo


def connect(backend_url: str) -> "openeo.Connection":
    """Connect to the openEO backend and authenticate.

    First run opens an interactive OIDC device-code login (browser popup,
    or a URL+code printed to the console if headless). Subsequent runs
    reuse the cached token via the openeo client's local token store, so
    this generally only prompts once per machine.
    """
    connection = openeo.connect(backend_url)
    connection.authenticate_oidc()
    return connection
