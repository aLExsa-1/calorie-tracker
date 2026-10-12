"""启动入口：python -m backend serve [--host 127.0.0.1] [--port 8787] [--data-dir data]"""
from __future__ import annotations

import argparse
from pathlib import Path

from .config import Config
from .engine import Engine
from .server import make_server
from .store import Store

PROJECT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backend")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="启动 API 与前端")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    serve.add_argument("--data-dir", default=str(PROJECT / "data"))
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    engine = Engine(Store(data_dir / "ct.db"), Config(data_dir / "config.json"))
    httpd = make_server(engine, args.host, args.port)
    print(f"热量管理服务已启动：http://{args.host}:{args.port}  （数据目录：{data_dir}）")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        engine.store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
