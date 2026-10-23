"""The online services that can hear speech and translate, and their keys.

Every service speaks OpenAI's API (or something close to it), so one piece of code reaches
them all; what differs is the address, the models, and how sound is sent:
  "whisper"  sound to /audio/transcriptions, like OpenAI's Whisper
  "qwen"     sound inside a chat message; the answer says the language (knows Cantonese)
  "gemini"   sound inside a chat message, with the request to write it down

Keys and chosen models are kept in %APPDATA%\\VRChat-Translator\\models.json:
    {"openai": {"key": "...", "hear_model": "whisper-1", "translate_model": "gpt-5.4-mini"},
     "custom": {"url": "https://.../v1", "key": "..."}}
A model left empty there means the service's default below. Several translating models can be
listed with commas: when one is at its limit, the next answers.

All users share the same app. Custom domain accepts a user-supplied API URL and key.
"""
from __future__ import annotations

import json
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

def update_source() -> str:
    """The GitHub repository that publishes application releases."""
    return "SentoMinh/ART-Asia-realtime-Translator"


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    url: str                  # OpenAI-style base address; "" = the user types it (Custom)
    hear_model: str           # default hearing model; "" = this service can't hear
    hear_style: str           # "whisper" | "qwen" | "gemini" (see above)
    translate_model: str      # default translating model(s); "" = the user types it
    get_key: str = ""         # where to get a key
    extra: tuple = ()         # extra request fields for translating, e.g. (("reasoning_effort", "none"),)

    @property
    def can_hear(self) -> bool:
        return bool(self.hear_model) or is_custom(self.id)


SERVICES = {s.id: s for s in (
    Service("openai", "OpenAI", "https://api.openai.com/v1", "whisper-1", "whisper", "gpt-5.4-mini",
            "https://platform.openai.com/api-keys", (("reasoning_effort", "none"),)),
    Service("gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai",
            "gemini-3.5-flash-lite", "gemini", "gemini-3.5-flash-lite",   # the benchmark's best translator
            "https://aistudio.google.com/apikey", (("reasoning_effort", "low"),)),
    Service("qwen", "Qwen (Alibaba Cloud)", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            "qwen3-asr-flash", "qwen", "qwen-flash",
            "https://modelstudio.console.alibabacloud.com/?tab=playground#/api-key",
            (("enable_thinking", False),)),
    Service("mimo", "Xiaomi MiMo", "https://api.xiaomimimo.com/v1", "", "", "mimo-v2-flash",
            "https://platform.xiaomimimo.com"),
    Service("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", "qwen/qwen3-asr-1.7b", "whisper",
            "google/gemini-3.5-flash-lite", "https://openrouter.ai/settings/keys"),
    Service("custom", "Custom domain", "", "", "whisper", ""),
)}
HEARING = TRANSLATING = ("local", "custom")
FIELDS = ("url", "key", "hear_model", "translate_model", "name", "legacy_provider")


def is_custom(service: str) -> bool:
    return service == "custom" or service.startswith("custom_")


def offered(choices: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Custom domains available in the UI; built-in definitions only recover old settings."""
    domains = ("custom", *(key for key, value in saved().items()
                            if key != "custom" and is_custom(key) and isinstance(value, dict)))
    return (("local",) if "local" in choices else ()) + domains


def info(service: str) -> Service:
    if not is_custom(service):
        return SERVICES[service]
    legacy = SERVICES.get(setting(service, "legacy_provider"), SERVICES["custom"])
    return Service(service, title(service), "", "", legacy.hear_style, "", extra=legacy.extra)


def default_service() -> str:
    """New profiles use the first custom domain."""
    return "custom"


def models_file() -> Path:
    return Path(os.environ.get("APPDATA") or str(Path.home())) / "VRChat-Translator" / "models.json"


_cache: tuple = (None, {})     # (file stamp, contents): the file is read again only after a change


def saved() -> dict:
    global _cache
    path = models_file()
    try:
        stat = path.stat()
        stamp = (str(path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return {}
    if _cache[0] != stamp:
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            data = {}
        _cache = (stamp, data if isinstance(data, dict) else {})
    return _cache[1]


def setting(service: str, field: str) -> str:
    """A saved value, or the service's default for the address and the models."""
    entry = saved().get(service)
    value = str(entry.get(field) or "").strip() if isinstance(entry, dict) else ""
    if value:
        return value
    if service == "local":
        return {"hear_model": "large-v3-turbo", "translate_model": "nllb-200-ct2"}.get(field, "")
    known = SERVICES.get(service)
    return getattr(known, field, "") if known and field != "key" else ""


def catalog(service: str) -> list[str]:
    entry = saved().get(service) or {}
    if not isinstance(entry, dict):
        return []
    stamp = hashlib.sha256((setting(service, "url") + "\0" + setting(service, "key")).encode()).hexdigest()
    models = entry.get("models", [])
    return [m for m in models if isinstance(m, str) and m] if (
        isinstance(models, list) and entry.get("models_credentials") == stamp) else []


def save(service: str, *, models: list[str] | None = None, **values: str) -> None:
    """Stores the given fields of one service ("" removes a field: back to the default)."""
    global _cache
    data = dict(saved())
    entry = dict(data.get(service) or {})
    for field, value in values.items():
        if field not in FIELDS:
            raise ValueError(field)
        value = str(value).strip()
        if value:
            entry[field] = value
        else:
            entry.pop(field, None)
    if models is not None:
        entry["models"] = list(dict.fromkeys(m for m in models if isinstance(m, str) and m))
        entry["models_credentials"] = hashlib.sha256(
            (entry.get("url", "") + "\0" + entry.get("key", "")).encode()).hexdigest()
    data[service] = entry
    _write(data)


def _write(data: dict) -> None:
    global _cache
    path = models_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)
    _cache = (None, {})  # Rapid same-size writes can share a Windows file timestamp.


def remove_domain(service: str) -> None:
    if not is_custom(service) or service == "custom":
        raise ValueError("The first custom domain is kept")
    data = dict(saved())
    data.pop(service, None)
    _write(data)


def migrate_provider(service: str) -> str:
    if service not in SERVICES or is_custom(service):
        return service
    if not saved().get(service):
        return "custom"
    target = "custom_legacy_" + service
    if target not in saved():
        from urllib.parse import urlsplit
        values = {field: setting(service, field) for field in ("url", "key", "hear_model", "translate_model")}
        save(target, **values, name="Custom domain — " + (urlsplit(values["url"]).hostname or service),
             legacy_provider=service)
    return target


def migrate_legacy_settings() -> None:
    """Copy recoverable old API settings without overwriting a configured custom API."""
    data = saved()
    if data.get("custom"):
        return
    legacy = data.get("dev")
    entry = dict(legacy) if isinstance(legacy, dict) else {}
    # Older source/folder installs may still have this file. New builds never bundle it.
    path = Path(__file__).resolve().parent.parent / "assets" / "edition.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
        defaults = config.get("dev", {}) if isinstance(config, dict) else {}
    except (OSError, ValueError):
        defaults = {}
    if isinstance(defaults, dict):
        for field in FIELDS:
            if not entry.get(field) and isinstance(defaults.get(field), str):
                entry[field] = defaults[field]
        older = defaults.get("key_file")
        if not entry.get("key") and isinstance(older, str) and Path(older).name == older:
            try:
                entry["key"] = (models_file().parent / older).read_text(encoding="utf-8-sig").strip()
            except OSError:
                pass
    values = {field: value for field, value in entry.items() if field in FIELDS and isinstance(value, str)}
    if values:
        save("custom", **values)


def ready(service: str) -> bool:
    """Has what it needs to be asked: a key (or code), and an address."""
    return not missing(service)


def translate_models(service: str) -> list[str]:
    if service == "local":
        from . import local_model
        return [local_model.selected("translating")]
    return [m.strip() for m in setting(service, "translate_model").split(",") if m.strip()]


def title(service: str) -> str:
    if is_custom(service):
        return setting(service, "name") or "Custom domain"
    return "Local Model (this PC)" if service == "local" else SERVICES[service].name if service in SERVICES else service


def auth(service: str) -> dict:
    key = setting(service, "key")
    return {"Authorization": f"Bearer {key}"} if key else {}


def post_chat(http, service: str, body: dict, plain: set):
    """POST to the service's /chat/completions. Its extra fields (e.g. "think less") go along
    unless the model refused them once; then the request is sent again without them, and the
    model is remembered in `plain`."""
    url = setting(service, "url").rstrip("/") + "/chat/completions"
    extra = dict(info(service).extra) if service in SERVICES or is_custom(service) else {}
    if "gpt-oss" in body.get("model", ""):
        extra.setdefault("reasoning_effort", "low")     # these think first: keep it short
    if extra and body.get("model") not in plain:
        answer = http.post(url, json={**body, **extra}, headers=auth(service))
        if answer.status_code != 400:
            return answer
        plain.add(body.get("model"))
    return http.post(url, json=body, headers=auth(service))


def retry_after(answer, default: float = 20.0) -> float:
    try:
        return max(float(answer.headers.get("retry-after", default)), 1.0)
    except (TypeError, ValueError):
        return default


def error_message(answer) -> str:
    """The service's own explanation, if it gave one."""
    try:
        body = answer.json()
    except ValueError:
        return answer.text.strip()[:160]
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or "").strip()[:160]
    return str(error or "").strip()[:160]


def failure(service: str, answer) -> str:
    """A refused request in plain words."""
    name, message = title(service), error_message(answer)
    if answer.status_code == 429:
        return f"{name}: {message}" if message else f"{name}'s limit was reached"
    if answer.status_code in (401, 403):
        return f"{name} did not accept the key (Settings → Models), or blocks this network (e.g. a VPN)"
    return f"{name} error {answer.status_code}" + (f": {message}" if message else "")


def check(service: str, url: str = "", key: str = "", http=None, *, use_saved: bool = True) -> tuple[bool, str]:
    """Asks the service whether the address and key work (typed values first, then saved
    ones), without using up anything: its list of models. Set use_saved=False when
    checking a credential snapshot so an empty key stays empty."""
    url = (url.strip() or (setting(service, "url") if use_saved else "")).rstrip("/")
    key = key.strip() or (setting(service, "key") if use_saved else "")
    if not url:
        return False, "no address yet"
    if not key and not is_custom(service):
        return False, "no key yet"
    if http is None:
        import httpx
        timeout = 60 if is_custom(service) else 8
        http = httpx.Client(timeout=timeout)
    # OpenRouter shows its model list to anyone; its /key page needs a working key
    page = "key" if service == "openrouter" else "models"
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        answer = http.get(f"{url}/{page}", headers=headers)
    except Exception as error:
        return False, f"can't be reached: {error}"
    if answer.status_code == 200:
        return True, "the key works" if key else "the address works"
    if answer.status_code == 404 and is_custom(service):
        return False, failure(service, answer) + "; check the API base address and model-list endpoint"
    return False, failure(service, answer).replace(" (Settings → Models)", "")


def fetch_models(service: str = "custom", url: str = "", key: str = "", http=None) -> list[str]:
    """Queries the service's /models endpoint and returns a sorted list of model IDs."""
    url = (url.strip() or setting(service, "url")).rstrip("/")
    key = key.strip() or setting(service, "key")
    if not url:
        return []
    if http is None:
        import httpx
        timeout = 30 if is_custom(service) else 8
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            return fetch_models(service, url=url, key=key, http=client)
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        answer = http.get(f"{url}/models", headers=headers)
        if answer.status_code == 404 and not url.endswith("/v1"):
            fallback = http.get(f"{url}/v1/models", headers=headers)
            if fallback.status_code == 200:
                answer = fallback
    except Exception as error:
        raise OSError(f"can't be reached: {error}") from error
    if answer.status_code != 200:
        raise OSError(failure(service, answer).replace(" (Settings → Models)", ""))
    try:
        body = answer.json()
    except Exception as error:
        raise OSError(f"invalid JSON from /models: {error}") from error

    models: list[str] = []
    if isinstance(body, dict):
        raw_list = body.get("data") or body.get("models") or []
        if isinstance(raw_list, list):
            for item in raw_list:
                if isinstance(item, dict):
                    mid = item.get("id") or item.get("name")
                    if mid:
                        models.append(str(mid))
                elif isinstance(item, str) and item:
                    models.append(item)
    elif isinstance(body, list):
        for item in body:
            if isinstance(item, dict):
                mid = item.get("id") or item.get("name")
                if mid:
                    models.append(str(mid))
            elif isinstance(item, str) and item:
                models.append(item)
    return sorted(list(dict.fromkeys(models)))


def missing(service: str) -> str:
    """What to do before this service works, in plain words; "" when it is ready."""
    name = title(service)
    if not setting(service, "url"):
        return f"{name} has no address yet (Settings → Models)"
    if not is_custom(service) and not setting(service, "key"):
        return f"no {name} key yet (Settings → Models)"
    return ""
