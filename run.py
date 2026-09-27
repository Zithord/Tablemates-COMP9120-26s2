"""Start the backend; the frontend can use the JSON endpoints under /api."""

import os

from app import create_app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("APP_HOST", "127.0.0.1"),
        port=int(os.environ.get("APP_PORT", "5000")),
        debug=False,
    )
