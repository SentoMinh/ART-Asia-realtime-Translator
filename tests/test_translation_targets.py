"""Bounded online concurrency, immediate partial results and local isolation."""
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from engine import services
from engine.translators import Chain, ServiceChain, ServiceTranslator
from vrc.translate import TranslateError, translate_targets


def test_target_timings_reach_engine_log_without_transcript(monkeypatch):
    import logging
    from engine import _log_to_file, log_file
    logger = logging.getLogger("engine")
    monkeypatch.setattr(logger, "handlers", [])
    monkeypatch.setattr(logger, "level", logging.INFO)
    class Translator:
        def translate(self, text, target, source):
            return "translated private words"
    try:
        _log_to_file()
        translate_targets(Translator(), "private source words", ("vi",), "en")
        recorded = log_file().read_text(encoding="utf-8")
        assert "translation target=vi duration_ms=" in recorded
        assert "private" not in recorded
    finally:
        for handler in logger.handlers:
            handler.close()


def test_fast_second_language_is_visible_before_slow_first_fails():
    release, entered = threading.Event(), threading.Event()
    caller = threading.get_ident()
    updates, calls = [], []
    class Translator:
        parallel_targets = True
        def translate(self, text, target, source, heard=False):
            assert heard and source == "en"
            calls.append(target)
            if target == "zh":
                entered.set()
                assert release.wait(3)
                raise TranslateError("slow target unavailable")
            assert entered.wait(3)
            return "Xin chào"
    def progress(values):
        assert threading.get_ident() == caller  # Worker results serialized by the caller.
        updates.append(values)
        if "vi" in values:
            release.set()
    try:
        values, errors = translate_targets(Translator(), "Hello", ("zh", "vi", "en", "vi", ""),
                                          "en", heard=True, on_result=progress)
    finally:
        release.set()
    assert sorted(calls) == ["vi", "zh"]
    assert updates == [{"en": "Hello"}, {"en": "Hello", "vi": "Xin chào"}]
    assert list(values) == ["zh", "vi", "en"]
    assert values == {"zh": "", "vi": "Xin chào", "en": "Hello"}
    assert list(errors) == ["zh"]


def test_two_request_limit_and_all_targets_complete_once():
    pair = threading.Barrier(2)
    lock = threading.Lock()
    active = peak = 0
    class Translator:
        parallel_targets = True
        def translate(self, text, target, source):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            if target in ("zh", "vi"):
                pair.wait(3)
            with lock:
                active -= 1
            return target
    values, errors = translate_targets(Translator(), "Hello", ("zh", "vi", "ja", "ko"), "en")
    assert peak == 2 and active == 0
    assert values == {code: code for code in ("zh", "vi", "ja", "ko")} and errors == {}


def test_local_chain_keeps_inference_on_the_calling_worker(monkeypatch):
    from engine.local_inference import translator
    caller, calls = threading.get_ident(), []
    def translate(text, target, source, heard=False):
        assert threading.get_ident() == caller
        calls.append(target)
        return target
    monkeypatch.setattr(translator, "translate", translate)
    chain = ServiceChain(lambda: "local")
    values, errors = translate_targets(chain, "Hello", ("vi", "zh"), "en")
    assert calls == ["vi", "zh"] and values == {"vi": "vi", "zh": "zh"} and not errors


def test_online_chain_reuses_one_client_and_never_changes_service(monkeypatch):
    services.save("custom", url="https://selected.test/v1", key="test", translate_model="chosen")
    pair = threading.Barrier(2)
    clients, calls = [], []
    class Http:
        def __init__(self, **kwargs):
            clients.append(self)
        def post(self, url, *, json, headers):
            calls.append((url, json["model"]))
            pair.wait(3)
            from types import SimpleNamespace
            return SimpleNamespace(status_code=200, json=lambda: {"choices": [{"message": {"content": "translated"}}]})
    import httpx
    monkeypatch.setattr(httpx, "Client", Http)
    chain = ServiceChain(lambda: "custom")
    values, errors = translate_targets(chain, "Hello", ("vi", "zh"), "en")
    assert not errors and all(values.values())
    assert len(clients) == 1 and len(chain._chains) == 1
    assert calls == [("https://selected.test/v1/chat/completions", "chosen")] * 2


@pytest.mark.parametrize("late_failure", [False, True])
def test_inflight_result_preserves_other_targets_rate_limit(late_failure):
    pair, failed = threading.Barrier(2), threading.Event()
    class Translator:
        def translate(self, text, target, source, heard=False):
            pair.wait(3)
            if target == "vi":
                error = TranslateError("rate limit reached")
                error.wait = 30
                raise error
            assert failed.wait(3)
            if late_failure:
                error = TranslateError("wrong language")
                error.wait = 0
                raise error
            return "translation"
    chain = Chain([("selected", Translator())], clock=lambda: 10)
    with ThreadPoolExecutor(max_workers=2) as pool:
        success = pool.submit(chain.translate, "Hello", "zh", "en")
        failure = pool.submit(chain.translate, "Hello", "vi", "en")
        try:
            with pytest.raises(TranslateError, match="rate limit reached"):
                failure.result(3)
        finally:
            failed.set()
        if late_failure:
            with pytest.raises(TranslateError, match="wrong language"):
                success.result(3)
        else:
            assert success.result(3) == "translation"
    with pytest.raises(TranslateError, match="rate limit reached"):
        chain.translate("Next", "vi", "en")
