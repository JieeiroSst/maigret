"""Standalone JSON polling API for Maigret username search.

Wraps `maigret.search()` directly (independent of the bundled Flask web UI in
maigret/web/app.py) and exposes a submit/poll JSON API:

    POST /api/search           {"username": "exampleuser"} -> {"job_id": ...}
    GET  /api/status/<job_id>  -> {"state": "running"|"completed"|"failed", ...}

Run with:
    python api_server.py
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from threading import Thread
from typing import Any, Dict

from flask import Flask, jsonify, request

import maigret
from maigret.sites import MaigretDatabase

app = Flask(__name__)

DB_FILE = os.path.join(os.path.dirname(__file__), 'maigret', 'resources', 'data.json')
DEFAULT_TOP_SITES = 500

jobs: Dict[str, Dict[str, Any]] = {}


def run_search(job_id: str, username: str, top_sites: int, timeout: int) -> None:
    logger = logging.getLogger('maigret')
    logger.setLevel(logging.WARNING)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        db = MaigretDatabase().load_from_path(DB_FILE)
        sites = db.ranked_sites_dict(top=top_sites, id_type='username', disabled=False)

        search_results = loop.run_until_complete(
            maigret.search(
                username=username,
                site_dict=sites,
                timeout=timeout,
                logger=logger,
                id_type='username',
                is_parsing_enabled=True,
            )
        )

        site_results = []
        for site_data in search_results.values():
            status = site_data.get('status')
            if status is None:
                continue
            http_status = site_data.get('http_status')
            if not isinstance(http_status, int) or not (200 <= http_status < 300):
                continue
            entry = status.json()
            entry['url_main'] = site_data.get('url_main')
            entry['http_status'] = http_status
            entry['rank'] = site_data.get('rank')
            entry['is_similar'] = site_data.get('is_similar', False)
            site_results.append(entry)

        jobs[job_id].update(
            state='completed',
            finished_at=datetime.now(timezone.utc).isoformat(),
            results=site_results,
        )
    except Exception as e:
        logger.error(f"Search failed for job {job_id}: {e}")
        jobs[job_id].update(
            state='failed',
            finished_at=datetime.now(timezone.utc).isoformat(),
            error=str(e),
        )
    finally:
        loop.close()


@app.route('/api/search', methods=['POST'])
def start_search():
    payload = request.get_json(silent=True) or {}
    username = (payload.get('username') or '').strip()
    if not username:
        return jsonify({'error': 'username is required'}), 400

    top_sites = int(payload.get('top_sites', DEFAULT_TOP_SITES))
    timeout = int(payload.get('timeout', 30))

    job_id = uuid.uuid4().hex
    jobs[job_id] = {
        'username': username,
        'state': 'running',
        'started_at': datetime.now(timezone.utc).isoformat(),
    }
    Thread(
        target=run_search, args=(job_id, username, top_sites, timeout), daemon=True
    ).start()

    return jsonify({'job_id': job_id, 'state': 'running'}), 202


@app.route('/api/status/<job_id>', methods=['GET'])
def get_status(job_id):
    job = jobs.get(job_id)
    if job is None:
        return jsonify({'error': 'unknown job_id'}), 404
    return jsonify({'job_id': job_id, **job})


if __name__ == '__main__':
    from waitress import serve

    logging.basicConfig(level=logging.INFO)
    host = os.getenv('API_HOST', '127.0.0.1')
    port = int(os.getenv('API_PORT', '5050'))
    serve(app, host=host, port=port)
