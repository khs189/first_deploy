from __future__ import annotations

from web_server import app, load_config


def main() -> None:
    cfg = load_config()
    host = cfg.get("web", "host", fallback="0.0.0.0")
    port = cfg.getint("web", "port", fallback=8000)
    debug = cfg.getboolean("web", "debug", fallback=True)
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
