from __future__ import annotations

import json
import os
from collections.abc import Iterable, Iterator
from typing import Any, Protocol

from .models import KeywordRank

_VOLUME_KEYS = ("searchvolume", "search_volume", "searchvolume_monthly", "searches", "volume", "traffic", "queries")


def _find_volume(payload: Any) -> int | None:
    if isinstance(payload, dict):
        for key in _VOLUME_KEYS:
            value = payload.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return int(value)
        for value in payload.values():
            if isinstance(value, (dict, list)):
                found = _find_volume(value)
                if found is not None:
                    return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_volume(item)
            if found is not None:
                return found
    return None


class SistrixClient(Protocol):
    async def competitors(self, domain: str, country: str, limit: int) -> list[str]: ...

    async def visindex(self, domain: str, country: str) -> float | None: ...

    async def kwcount(self, domain: str, country: str) -> int | None: ...

    async def kwcount_top10(self, domain: str, country: str) -> int | None: ...

    async def search_volumes(self, keywords: Iterable[str], country: str) -> dict[str, int]: ...

    async def domain_keywords(
        self,
        domain: str,
        country: str,
        to_pos: int,
        regex_keyword: str | None = None,
        page_size: int = 1000,
        max_pages: int = 10,
    ) -> list[KeywordRank]: ...


def _unwrap_json(payload: Any) -> Any:
    if isinstance(payload, str):
        return json.loads(payload)
    if isinstance(payload, dict):
        content = payload.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    return json.loads(item["text"])
        if "text" in payload and isinstance(payload["text"], str):
            return json.loads(payload["text"])
    return payload


class ConnectorSistrixClient:
    def __init__(self, tool_call_client: Any, connector_prefix: str = "sistrix_e5d7") -> None:
        self._client = tool_call_client
        self._prefix = connector_prefix

    async def _call(self, tool: str, arguments: dict[str, Any]) -> Any:
        raw = await self._client.call_tool(tool_name=f"{self._prefix}_{tool}", arguments=arguments)
        return _unwrap_json(raw)

    async def competitors(self, domain: str, country: str, limit: int) -> list[str]:
        data = await self._call("domain", {"domain": domain, "view": "competitors", "country": country, "limit": limit})
        return [str(d) for d in data]

    async def _metric(self, domain: str, country: str, view: str, key: str) -> float | None:
        data = await self._call("domain", {"domain": domain, "view": view, "country": country})
        rows = data.get(key) or []
        if not rows:
            return None
        value = rows[0].get("value")
        return float(value) if value is not None else None

    async def visindex(self, domain: str, country: str) -> float | None:
        return await self._metric(domain, country, "visindex", "sichtbarkeitsindex")

    async def kwcount(self, domain: str, country: str) -> int | None:
        value = await self._metric(domain, country, "kwcount", "kwcount.seo")
        return int(value) if value is not None else None

    async def kwcount_top10(self, domain: str, country: str) -> int | None:
        value = await self._metric(domain, country, "kwcount_top10", "kwcount.seo.top10")
        return int(value) if value is not None else None

    async def search_volumes(self, keywords: Iterable[str], country: str) -> dict[str, int]:
        volumes: dict[str, int] = {}
        for keyword in keywords:
            data = await self._call("keyword", {"keyword": keyword, "view": "traffic", "country": country})
            volume = _find_volume(data)
            if volume is not None:
                volumes[keyword] = volume
        return volumes

    async def domain_keywords(
        self,
        domain: str,
        country: str,
        to_pos: int,
        regex_keyword: str | None = None,
        page_size: int = 1000,
        max_pages: int = 10,
    ) -> list[KeywordRank]:
        rows: list[KeywordRank] = []
        offset = 0
        for _ in range(max_pages):
            args: dict[str, Any] = {
                "domain": domain,
                "country": country,
                "to_pos": to_pos,
                "limit": page_size,
                "offset": offset,
            }
            if regex_keyword:
                args["regex_keyword"] = regex_keyword
            data = await self._call("keyword_domain_seo", args)
            if not isinstance(data, list) or not data:
                break
            for item in data:
                rows.append(
                    KeywordRank(
                        keyword=str(item["keyword"]),
                        position=int(item["position"]),
                        url=str(item.get("url") or ""),
                    )
                )
            if len(data) < page_size:
                break
            offset += page_size
        return rows


class StaticSistrixClient:
    def __init__(self, capture: dict[str, Any]) -> None:
        self._capture = capture

    def _profile(self, domain: str) -> dict[str, Any]:
        if domain == self._capture["own"]["domain"]:
            return self._capture["own"]
        for entry in self._capture["competitor_candidates"]:
            if entry["domain"] == domain:
                return entry
        raise KeyError(domain)

    async def competitors(self, domain: str, country: str, limit: int) -> list[str]:
        return list(self._capture["competitor_list"])[:limit]

    async def visindex(self, domain: str, country: str) -> float | None:
        value = self._profile(domain).get("visindex")
        return float(value) if value is not None else None

    async def kwcount(self, domain: str, country: str) -> int | None:
        value = self._profile(domain).get("kwcount")
        return int(value) if value is not None else None

    async def kwcount_top10(self, domain: str, country: str) -> int | None:
        value = self._profile(domain).get("kwcount_top10")
        return int(value) if value is not None else None

    async def search_volumes(self, keywords: Iterable[str], country: str) -> dict[str, int]:
        known = self._capture.get("search_volumes") or {}
        return {kw: int(known[kw]) for kw in keywords if kw in known}

    async def domain_keywords(
        self,
        domain: str,
        country: str,
        to_pos: int,
        regex_keyword: str | None = None,
        page_size: int = 1000,
        max_pages: int = 10,
    ) -> list[KeywordRank]:
        import re

        rows = [
            KeywordRank(keyword=r["keyword"], position=int(r["position"]), url=r.get("url", ""))
            for r in self._profile(domain).get("keywords", [])
            if int(r["position"]) <= to_pos
        ]
        if regex_keyword:
            pattern = re.compile(regex_keyword)
            rows = [r for r in rows if pattern.search(r.keyword)]
        return rows


class RestSistrixClient:
    BASE_URL = "https://api.sistrix.com"

    def __init__(self, api_key: str | None = None, timeout: float = 60.0) -> None:
        import requests

        self._api_key = api_key or os.environ.get("SISTRIX_API_KEY")
        if not self._api_key:
            raise ValueError("SISTRIX_API_KEY is not set")
        self._timeout = timeout
        self._session = requests.Session()

    @staticmethod
    def _find_error(payload: Any) -> Any:
        if isinstance(payload, dict):
            error = payload.get("error")
            if error:
                return error
            if str(payload.get("status", "")).lower() == "error":
                return payload
            if "error_code" in payload or "error_message" in payload:
                return payload
            for value in payload.values():
                if isinstance(value, (dict, list)):
                    found = RestSistrixClient._find_error(value)
                    if found is not None:
                        return found
        elif isinstance(payload, list):
            for item in payload:
                found = RestSistrixClient._find_error(item)
                if found is not None:
                    return found
        return None

    def _get(self, endpoint: str, params: dict[str, Any]) -> Any:
        query = {"key": self._api_key, "api_key": self._api_key, "format": "json", **params}
        response = self._session.get(f"{self.BASE_URL}/{endpoint}", params=query, timeout=self._timeout)
        response.raise_for_status()
        payload = response.json()
        error = self._find_error(payload)
        if error is not None:
            raise RuntimeError(f"Sistrix API error on {endpoint}: {str(error)[:500]}")
        return payload

    def raw_get(self, endpoint: str, params: dict[str, Any], with_format: bool = True) -> dict[str, Any]:
        query = {"key": self._api_key, "api_key": self._api_key, **params}
        if with_format:
            query["format"] = "json"
        response = self._session.get(f"{self.BASE_URL}/{endpoint}", params=query, timeout=self._timeout)
        return {"http_status": response.status_code, "body": response.text[:800]}

    @staticmethod
    def _unwrap_answer(payload: Any) -> Any:
        if isinstance(payload, dict) and "answer" in payload:
            return payload["answer"]
        return payload

    @staticmethod
    def _walk_dicts(node: Any) -> Iterator[dict[str, Any]]:
        if isinstance(node, dict):
            yield node
            for value in node.values():
                yield from RestSistrixClient._walk_dicts(value)
        elif isinstance(node, list):
            for item in node:
                yield from RestSistrixClient._walk_dicts(item)

    @classmethod
    def _rows(cls, payload: Any) -> list[Any]:
        payload = cls._unwrap_answer(payload)
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            if isinstance(payload.get("data"), list):
                return payload["data"]
            for value in payload.values():
                if isinstance(value, list) and value:
                    return value
        return []

    @classmethod
    def _scalar(cls, payload: Any) -> float | None:
        for d in cls._walk_dicts(cls._unwrap_answer(payload)):
            if "value" in d:
                try:
                    return float(d["value"])
                except (TypeError, ValueError):
                    continue
        return None

    @staticmethod
    def _normalize_domain(value: str) -> str:
        value = value.strip().lower()
        if "://" in value:
            value = value.split("://", 1)[1]
        value = value.split("/", 1)[0]
        return value.removeprefix("www.")

    @classmethod
    def _extract_domains(cls, payload: Any) -> list[str]:
        answer = cls._unwrap_answer(payload)
        domains: list[str] = []
        if isinstance(answer, list) and answer and all(isinstance(x, str) for x in answer):
            domains = [cls._normalize_domain(x) for x in answer]
        else:
            for d in cls._walk_dicts(answer):
                value = d.get("domain") or d.get("host") or d.get("url")
                if isinstance(value, str) and value and "country" not in d:
                    domains.append(cls._normalize_domain(value))
        seen: set[str] = set()
        unique: list[str] = []
        for item in domains:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        return unique

    async def competitors(self, domain: str, country: str, limit: int) -> list[str]:
        payload = self._get(
            "domain.competitors.seo", {"domain": domain, "country": country, "num": limit}
        )
        return self._extract_domains(payload)

    async def visindex(self, domain: str, country: str) -> float | None:
        payload = self._get("domain.visibilityindex", {"domain": domain, "country": country})
        return self._scalar(payload)

    async def kwcount(self, domain: str, country: str) -> int | None:
        payload = self._get("domain.kwcount.seo", {"domain": domain, "country": country})
        value = self._scalar(payload)
        return int(value) if value is not None else None

    async def kwcount_top10(self, domain: str, country: str) -> int | None:
        payload = self._get("domain.kwcount.seo.top10", {"domain": domain, "country": country})
        value = self._scalar(payload)
        return int(value) if value is not None else None

    async def search_volumes(self, keywords: Iterable[str], country: str) -> dict[str, int]:
        volumes: dict[str, int] = {}
        for keyword in keywords:
            try:
                payload = self._get("keyword", {"keyword": keyword, "country": country})
            except RuntimeError:
                continue
            volume = _find_volume(payload)
            if volume is not None:
                volumes[keyword] = volume
        return volumes

    async def domain_keywords(
        self,
        domain: str,
        country: str,
        to_pos: int,
        regex_keyword: str | None = None,
        page_size: int = 1000,
        max_pages: int = 10,
    ) -> list[KeywordRank]:
        import re

        pattern = re.compile(regex_keyword) if regex_keyword else None
        rows: list[KeywordRank] = []
        offset = 0
        for _ in range(max_pages):
            params: dict[str, Any] = {
                "domain": domain,
                "country": country,
                "limit": page_size,
                "offset": offset,
                "to_pos": to_pos,
            }
            if regex_keyword:
                params["regex_keyword"] = regex_keyword
            payload = self._get("keyword.domain.seo", params)
            raw_count = 0
            seen_keywords: set[str] = set()
            for d in self._walk_dicts(self._unwrap_answer(payload)):
                keyword = d.get("kw") or d.get("keyword")
                if not (isinstance(keyword, str) and keyword and "position" in d):
                    continue
                raw_count += 1
                if keyword in seen_keywords:
                    continue
                seen_keywords.add(keyword)
                rank = KeywordRank(
                    keyword=keyword,
                    position=int(d["position"]),
                    url=str(d.get("url") or ""),
                )
                if rank.position <= to_pos and (pattern is None or pattern.search(rank.keyword)):
                    rows.append(rank)
            if raw_count < page_size:
                break
            offset += page_size
        return rows
