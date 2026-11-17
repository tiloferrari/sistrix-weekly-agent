from __future__ import annotations

import json
import os
from typing import Any, Protocol

from .models import KeywordRank


class SistrixClient(Protocol):
    async def competitors(self, domain: str, country: str, limit: int) -> list[str]: ...

    async def visindex(self, domain: str, country: str) -> float | None: ...

    async def kwcount(self, domain: str, country: str) -> int | None: ...

    async def kwcount_top10(self, domain: str, country: str) -> int | None: ...

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

    def _get(self, endpoint: str, params: dict[str, Any]) -> Any:
        query = {"key": self._api_key, "api_key": self._api_key, "format": "json", **params}
        response = self._session.get(f"{self.BASE_URL}/{endpoint}", params=query, timeout=self._timeout)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error") or (payload.get("answer") or {}).get("error") if isinstance(payload.get("answer"), dict) else payload.get("error")
            if error:
                raise RuntimeError(f"Sistrix API error on {endpoint}: {error}")
        return payload

    @staticmethod
    def _rows(payload: Any) -> list[Any]:
        if isinstance(payload, dict) and isinstance(payload.get("answer"), (dict, list)):
            payload = payload["answer"]
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            if isinstance(payload.get("data"), list):
                return payload["data"]
            for value in payload.values():
                if isinstance(value, list) and value:
                    return value
        return []

    @staticmethod
    def _scalar(payload: Any) -> float | None:
        for item in RestSistrixClient._rows(payload):
            if isinstance(item, dict) and "value" in item:
                return float(item["value"])
        return None

    @staticmethod
    def _normalize_domain(value: str) -> str:
        value = value.strip().lower()
        if "://" in value:
            value = value.split("://", 1)[1]
        value = value.split("/", 1)[0]
        return value.removeprefix("www.")

    async def competitors(self, domain: str, country: str, limit: int) -> list[str]:
        payload = self._get(
            "domain.competitors.seo", {"domain": domain, "country": country, "num": limit}
        )
        domains: list[str] = []
        for item in self._rows(payload):
            if isinstance(item, str):
                domains.append(self._normalize_domain(item))
            elif isinstance(item, dict):
                for key in ("domain", "host", "url"):
                    value = item.get(key)
                    if isinstance(value, str) and value:
                        domains.append(self._normalize_domain(value))
                        break
        return domains

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
            keywords: list[dict[str, Any]] = []
            for item in self._rows(payload):
                if isinstance(item.get("keywords"), list):
                    keywords.extend(k for k in item["keywords"] if isinstance(k, dict))
                elif "kw" in item or "keyword" in item:
                    keywords.append(item)
            if not keywords:
                break
            for item in keywords:
                keyword = item.get("kw") or item.get("keyword")
                if not keyword:
                    continue
                rank = KeywordRank(
                    keyword=str(keyword),
                    position=int(item["position"]),
                    url=str(item.get("url") or ""),
                )
                if rank.position <= to_pos and (pattern is None or pattern.search(rank.keyword)):
                    rows.append(rank)
            if len(keywords) < page_size:
                break
            offset += page_size
        return rows
