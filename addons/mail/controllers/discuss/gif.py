# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import requests
import urllib3
import werkzeug.urls
from werkzeug.exceptions import BadRequest

from odoo.http import request, route, Controller

KLIPY_BASE_URL = "https://api.klipy.com/api/v1"
KLIPY_CONTENT_FILTER = "medium"
KLIPY_GIF_LIMIT = 8

_logger = logging.getLogger(__name__)


class DiscussGifController(Controller):
    def _get_klipy_api_key(self):
        """Get KLIPY API key from config parameters."""
        return request.env["ir.config_parameter"].sudo().get_param("discuss.klipy_api_key")

    def _request_klipy(self, endpoint):
        """Make a request to KLIPY API."""
        response = None
        api_key = self._get_klipy_api_key()
        if not api_key:
            raise BadRequest()
        try:
            url = f"{KLIPY_BASE_URL}/{api_key}/gifs/{endpoint}"
            response = requests.get(url, timeout=3)
            response.raise_for_status()
        except (urllib3.exceptions.MaxRetryError, requests.exceptions.HTTPError):
            _logger.error("Failed to fetch GIFs from KLIPY API.")

        if not response:
            raise BadRequest()
        return response

    def _transform_klipy_gif(self, klipy_gif):
        """Transform KLIPY GIF object to Tenor-compatible format for frontend."""
        # KLIPY uses 'file' with size variants (hd, md, sm, xs), each with format types (gif, webp, etc.)
        file_data = klipy_gif.get("file", {})
        # Use 'sm' (small) size for the tinygif equivalent, fallback to other sizes
        size_data = file_data.get("sm") or file_data.get("md") or file_data.get("xs") or file_data.get("hd") or {}
        gif_format = size_data.get("gif", {})

        return {
            "id": klipy_gif.get("slug", ""),
            "title": klipy_gif.get("title", ""),
            "media_formats": {
                "tinygif": {
                    "url": gif_format.get("url", ""),
                    "dims": [gif_format.get("width", 200), gif_format.get("height", 200)],
                    "duration": 0,
                    "preview": klipy_gif.get("blur_preview", ""),
                    "size": gif_format.get("size", 0),
                }
            },
            "content_description": klipy_gif.get("title", ""),
            "itemurl": gif_format.get("url", ""),
            "url": gif_format.get("url", ""),
            "tags": klipy_gif.get("tags", []),
            "flags": [],
            "hasaudio": False,
            "created": 0,
        }

    def _transform_klipy_category(self, klipy_category):
        """Transform KLIPY category to Tenor-compatible format."""
        return {
            "searchterm": klipy_category.get("query", klipy_category.get("category", "")),
            "path": "",
            "image": klipy_category.get("preview_url", ""),
            "name": f"#{klipy_category.get('category', '')}",
        }

    @route("/discuss/gif/search", type="jsonrpc", auth="user")
    def search(self, search_term, locale="en", country="US", position=None, readonly=True):
        # sudo: ir.config_parameter - read keys are hard-coded and values are only used for server requests
        # Position is now interpreted as page number for KLIPY (1-based)
        page = int(position) if position else 1

        query_string = werkzeug.urls.url_encode(
            {
                "q": search_term,
                "page": page,
                "per_page": KLIPY_GIF_LIMIT,
                "locale": locale,
                "content_filter": KLIPY_CONTENT_FILTER,
            }
        )
        response = self._request_klipy(f"search?{query_string}")
        if response:
            data = response.json()
            # KLIPY returns { result: true, data: { data: [...], current_page, has_next } }
            klipy_data = data.get("data", {})
            gifs = klipy_data.get("data", []) if isinstance(klipy_data, dict) else klipy_data
            has_next = klipy_data.get("has_next", False) if isinstance(klipy_data, dict) else False
            current_page = klipy_data.get("current_page", page) if isinstance(klipy_data, dict) else page

            # Transform to Tenor-compatible format
            transformed = [self._transform_klipy_gif(gif) for gif in gifs]

            return {
                "results": transformed,
                "next": str(current_page + 1) if has_next else "",
            }

    @route("/discuss/gif/categories", type="jsonrpc", auth="user", readonly=True)
    def categories(self, locale="en", country="US"):
        # sudo: ir.config_parameter - read keys are hard-coded and values are only used for server requests
        query_string = werkzeug.urls.url_encode(
            {
                "locale": locale,
            }
        )
        response = self._request_klipy(f"categories?{query_string}")
        if response:
            data = response.json()
            # KLIPY returns { result: true, data: { locale: "...", categories: [...] } }
            klipy_data = data.get("data", {})
            categories = klipy_data.get("categories", []) if isinstance(klipy_data, dict) else []

            # Transform to Tenor-compatible format
            transformed = [self._transform_klipy_category(cat) for cat in categories]

            return {
                "locale": locale,
                "tags": transformed,
            }

    @route("/discuss/gif/add_favorite", type="jsonrpc", auth="user")
    def add_favorite(self, klipy_gif_slug):
        request.env["discuss.gif.favorite"].create({"klipy_gif_slug": klipy_gif_slug})

    def _fetch_gifs_by_slugs(self, slugs):
        """Fetch multiple GIFs by their slugs from KLIPY API."""
        if not slugs:
            return []

        results = []
        for slug in slugs:
            try:
                response = self._request_klipy(slug)
                if response:
                    data = response.json()
                    # KLIPY returns { result: true, data: {...gif data...} }
                    gif_data = data.get("data", {})
                    if gif_data:
                        results.append(self._transform_klipy_gif(gif_data))
            except Exception:
                # Skip GIFs that fail to fetch
                _logger.warning(f"Failed to fetch GIF with slug: {slug}")
                continue

        return results

    @route("/discuss/gif/favorites", type="jsonrpc", auth="user", readonly=True)
    def get_favorites(self, offset=0):
        favorites = request.env["discuss.gif.favorite"].search(
            [("create_uid", "=", request.env.user.id)], limit=20, offset=offset
        )
        slugs = favorites.mapped("klipy_gif_slug")
        return (self._fetch_gifs_by_slugs(slugs) or [],)

    @route("/discuss/gif/remove_favorite", type="jsonrpc", auth="user")
    def remove_favorite(self, klipy_gif_slug):
        request.env["discuss.gif.favorite"].search(
            [
                ("create_uid", "=", request.env.user.id),
                ("klipy_gif_slug", "=", klipy_gif_slug),
            ]
        ).unlink()
