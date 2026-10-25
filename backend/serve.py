"""Linux container entry point; never uses the development HTTP server."""
import os


def main():
    port = int(os.environ.get("PORT", "10000"))
    if not 1024 <= port <= 65535:
        raise ValueError("PORT must be between 1024 and 65535.")
    os.execvp("gunicorn", ["gunicorn", "--bind", f"0.0.0.0:{port}", "--workers", "1",
                          "--threads", "4", "--timeout", "180", "--error-logfile", "-",
                          "backend.web:create_app()"])


if __name__ == "__main__":
    main()
