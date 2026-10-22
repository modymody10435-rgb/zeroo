from __future__ import annotations

import uvicorn

from server import config


def main() -> None:
    uvicorn.run(
        "server.main:app",
        host=config.HOST,
        port=config.PORT,
        proxy_headers=True,
        forwarded_allow_ips=config.FORWARDED_ALLOW_IPS,
    )


if __name__ == "__main__":
    main()
