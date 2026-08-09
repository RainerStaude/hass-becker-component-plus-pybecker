"""HTTP download view for the Becker database import/export feature."""

import os
from pathlib import Path
import tempfile

from aiohttp import web
from aiohttp.hdrs import CONTENT_DISPOSITION

from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.const import CONF_FILENAME
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .db_transfer import consistent_copy, dump_state_json, read_units


class BeckerDownloadView(HomeAssistantView):
    """Serve the shutter database as a JSON state file or a raw .db file."""

    url = "/api/becker/download/{entry_id}/{fmt}"
    name = "api:becker:download"

    async def get(
        self, request: web.Request, entry_id: str, fmt: str
    ) -> web.StreamResponse:
        """Return the requested export as a file attachment."""
        hass: HomeAssistant = request.app[KEY_HASS]
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN or fmt not in ("json", "db"):
            return web.Response(status=404)

        from . import _resolve_db_path  # local import avoids an import cycle

        db_path = await hass.async_add_executor_job(
            _resolve_db_path, hass.config.config_dir, entry.data.get(CONF_FILENAME)
        )
        stamp = dt_util.now().strftime("%Y%m%d_%H%M%S")

        if fmt == "json":
            units = await hass.async_add_executor_job(read_units, db_path)
            body = dump_state_json(units, dt_util.now().isoformat())
            return web.Response(
                body=body,
                content_type="application/json",
                headers={
                    CONTENT_DISPOSITION: (
                        f'attachment; filename="becker_state_{stamp}.json"'
                    )
                },
            )

        tmp = await hass.async_add_executor_job(_copy_db, db_path)
        return web.FileResponse(
            tmp,
            headers={
                CONTENT_DISPOSITION: (
                    f'attachment; filename="centronic-stick_{stamp}.db"'
                )
            },
        )


def _copy_db(db_path: str) -> str:
    """Write a consistent copy of the db to a temp file and return its path."""
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    consistent_copy(Path(db_path), Path(tmp))
    return tmp
