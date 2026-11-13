"""Serve the compiled Flutter app from the API's own origin."""
import os
from pathlib import Path

from fastapi.staticfiles import StaticFiles


def web_directory():
    configured = os.getenv('AGROPLAN_WEB_DIR')
    return Path(configured) if configured else Path(__file__).resolve().parents[1] / 'build' / 'web'


class AgroPlanFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if path in ('', '.', 'index.html', 'main.dart.js', 'flutter_bootstrap.js', 'flutter_service_worker.js'):
            response.headers['Cache-Control'] = 'no-cache'
        return response


def mount_web_app(app):
    directory = web_directory()
    if (directory / 'index.html').is_file():
        # Registered after API routes, so /auth, /parcels, etc. remain API routes.
        app.mount('/', AgroPlanFiles(directory=directory, html=True), name='web-app')
