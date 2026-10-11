"""The online services that can hear speech and translate, and their keys.

Every service speaks OpenAI's API (or something close to it), so one piece of code reaches
them all; what differs is the address, the models, and how sound is sent:
  "whisper"  sound to /audio/transcriptions, like OpenAI's Whisper
  "qwen"     sound inside a chat message; the answer says the language (knows Cantonese)
  "gemini"   sound inside a chat message, with the request to write it down

Keys and chosen models are kept in %APPDATA%\\VRChat-Translator\\models.json:
    {"openai": {"key": "...", "hear_model": "whisper-1", "translate_model": "gpt-5.4-mini"},
     "custom": {"url": "https://.../v1", "key": "..."}, "dev": {"key": "..."}}
A model left empty there means the service's default below. Several translating models can be
listed with commas: when one is at its limit, the next answers.

The friends' edition. Only the developer's own copy, and the program built from it for friends,
has assets/edition.json. It adds the "Dev key" service (its address and models are in that file,
the key comes from the developer) and says where the program updates itself from (ui/updater.py):
    {"edition": "friends",
     "dev": {"url": "https://.../v1", "hear_model": "...", "translate_model": "a, b, c",
             "key_file": "<an older key file in %APPDATA%\\VRChat-Translator, still read>"},
     "updates": "https://<update service>"  or  "<owner>/<public repository>"}
The public program has no such file: no Dev key, no self-update; everyone brings their own key.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

EDITION_FILE = Path(__file__).resolve().parent.parent / "assets" / "edition.json"


@lru_cache(maxsize=1)
def _edition() -> dict:
    try:
        data = json.loads(EDITION_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def dev() -> dict:
    """The Dev key service of the friends' edition; {} in the public program."""
    entry = _edition().get("dev")
    return entry if isinstance(entry, dict) and entry.get("url") else {}


def update_source() -> str:
    """Where the friends' program gets its updates ("" = none): the developer's update service
    (an https address, for a private repository) or a public GitHub repository ("owner/name")."""
    return str(_edition().get("updates") or "").strip()


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
        return bool(self.hear_model) or self.id == "custom"


SERVICES = {s.id: s for s in (
    Service("dev", "Dev key", "", "", "whisper", ""),     # address and models: dev(), from edition.json
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
HEARING = ("dev", "local", "openai", "gemini", "qwen", "openrouter", "custom")   # "local": this PC
TRANSLATING = ("dev", "openai", "gemini", "qwen", "mimo", "openrouter", "custom")
FIELDS = ("url", "key", "hear_model", "translate_model")


def offered(choices: tuple[str, ...] = tuple(SERVICES)) -> tuple[str, ...]:
    """The choices this copy offers: the Dev key only in the friends' edition."""
    return tuple(choice for choice in choices if choice != "dev" or dev())


def default_service() -> str:
    """Friends hear and translate with the Dev key; everyone else starts with Gemini, which
    has a free daily allowance and translated best in the benchmark."""
    return "dev" if dev() else "gemini"


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
    if service == "dev":
        if field != "key":
            return str(dev().get(field) or "").strip()
        older = str(dev().get("key_file") or "")      # where version 0.9.7 kept the Dev key
        try:
            return (models_file().parent / older).read_text(encoding="utf-8-sig").strip() if older else ""
        except OSError:
            return ""
    known = SERVICES.get(service)
    return getattr(known, field, "") if known and field != "key" else ""


def save(service: str, **values: str) -> None:
    """Stores the given fields of one service ("" removes a field: back to the default)."""
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
    data[service] = entry
    path = models_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def ready(service: str) -> bool:
    """Has what it needs to be asked: a key (or code), and an address."""
    return not missing(service)


def translate_models(service: str) -> list[str]:
    return [m.strip() for m in setting(service, "translate_model").split(",") if m.strip()]


def title(service: str) -> str:
    return SERVICES[service].name if service in SERVICES else service


def auth(service: str) -> dict:
    key = setting(service, "key")
    return {"Authorization": f"Bearer {key}"} if key else {}


def post_chat(http, service: str, body: dict, plain: set):
    """POST to the service's /chat/completions. Its extra fields (e.g. "think less") go along
    unless the model refused them once; then the request is sent again without them, and the
    model is remembered in `plain`."""
    url = setting(service, "url").rstrip("/") + "/chat/completions"
    extra = dict(SERVICES[service].extra) if service in SERVICES else {}
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
    if service == "dev":
        message = ""          # the service's own words would name it and show its account
    if answer.status_code == 429:
        return f"{name}: {message}" if message else f"{name}'s limit was reached"
    if answer.status_code in (401, 403):
        if service == "dev":
            return "the Dev key was not accepted (Settings → Models), or this network is blocked (e.g. a VPN)"
        return f"{name} did not accept the key (Settings → Models), or blocks this network (e.g. a VPN)"
    return f"{name} error {answer.status_code}" + (f": {message}" if message else "")


def check(service: str, url: str = "", key: str = "", http=None) -> tuple[bool, str]:
    """Asks the service whether the address and key work (typed values first, then saved
    ones), without using up anything: its list of models."""
    url = (url.strip() or setting(service, "url")).rstrip("/")
    key = key.strip() or setting(service, "key")
    if not url:
        return False, "no address yet"
    if not key and service != "custom":
        return False, "no key yet"
    if http is None:
        import httpx
        timeout = 60 if service == "custom" else 8
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
    if answer.status_code == 404 and service == "custom":
        return True, "the address answers (it has no model list, so the key was not checked)"
    return False, failure(service, answer).replace(" (Settings → Models)", "")


def fetch_models(service: str = "custom", url: str = "", key: str = "", http=None) -> list[str]:
    """Queries the service's /models endpoint and returns a sorted list of model IDs."""
    url = (url.strip() or setting(service, "url")).rstrip("/")
    key = key.strip() or setting(service, "key")
    if not url:
        return []
    if http is None:
        import httpx
        timeout = 30 if service == "custom" else 8
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
    if service == "dev":
        if not dev():
            return "this version has no Dev key: choose a service in Settings → Models"
        return "" if setting("dev", "key") else "no Dev key yet: ask the developer (Settings → Models)"
    name = SERVICES[service].name if service in SERVICES else service
    if not setting(service, "url"):
        return f"{name} has no address yet (Settings → Models)"
    if service != "custom" and not setting(service, "key"):
        return f"no {name} key yet (Settings → Models)"
    return ""
