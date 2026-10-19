import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QPushButton

from ui import config, i18n, theme
from ui.backend import AUTO, Backend, Utterance
from ui.config import Settings
from ui.demo_backend import PAUSE_TICKS, DemoBackend
from ui.log_view import MAX_ROWS, LogView
from ui.main_window import MainWindow
from ui.settings_window import SettingsWindow


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


class FakeBackend(Backend):
    def __init__(self):
        super().__init__()
        self.applied = []
        self.sent = []

    def apply_settings(self, settings):
        self.applied.append((settings.mic_on, settings.my_lang, settings.their_lang))

    def send_text(self, text):
        self.sent.append(text)


@pytest.fixture
def window(app):
    saved = []
    backend = FakeBackend()
    win = MainWindow(backend, Settings(), save=saved.append)
    win.saved = saved
    yield win
    win.deleteLater()


def send_header_mouse(target, kind, global_pos, *, held=True):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    button = Qt.NoButton if kind == QEvent.MouseMove else Qt.LeftButton
    event = QMouseEvent(kind, QPointF(target.mapFromGlobal(global_pos)), QPointF(global_pos),
                        button, Qt.LeftButton if held else Qt.NoButton, Qt.NoModifier)
    QApplication.sendEvent(target, event)


@pytest.mark.parametrize("target_name", ["mic_bar", "speaker_bar", "status", "language_label"])
def test_header_meters_and_labels_drag_when_native_move_is_unavailable(window, monkeypatch, target_name):
    from PySide6.QtCore import QEvent, QPoint
    from ui.main_window import TitleBar
    calls = []
    monkeypatch.setattr(TitleBar, "_start_system_move", lambda _: calls.append(True) or False)
    target = window._labels[0][0] if target_name == "language_label" else getattr(window, target_name)
    before = window.pos()
    start = target.mapToGlobal(QPoint(4, 4))
    delta = QPoint(37, 24)
    send_header_mouse(target, QEvent.MouseButtonPress, start)
    send_header_mouse(target, QEvent.MouseMove, start + delta)
    send_header_mouse(target, QEvent.MouseButtonRelease, start + delta, held=False)
    assert window.pos() == before + delta
    assert calls == [True]


def test_header_native_move_is_preferred(window, monkeypatch):
    from PySide6.QtCore import QEvent, QPoint
    from ui.main_window import TitleBar
    calls = []
    monkeypatch.setattr(TitleBar, "_start_system_move", lambda _: calls.append(True) or True)
    before = window.pos()
    start = window.mic_bar.mapToGlobal(QPoint(4, 4))
    send_header_mouse(window.mic_bar, QEvent.MouseButtonPress, start)
    send_header_mouse(window.mic_bar, QEvent.MouseMove, start + QPoint(37, 24))
    send_header_mouse(window.mic_bar, QEvent.MouseButtonRelease, start, held=False)
    assert calls == [True]
    assert window.pos() == before  # Windows, not the fallback, owns this drag.


def test_mic_button_click_toggles_but_drag_does_not(window, monkeypatch):
    from PySide6.QtCore import QEvent, QPoint, Qt
    from PySide6.QtTest import QTest
    from ui.main_window import TitleBar
    monkeypatch.setattr(TitleBar, "_start_system_move", lambda _: False)
    was_on = window.settings.mic_on
    QTest.mouseClick(window.mic_button, Qt.LeftButton)
    assert window.settings.mic_on != was_on
    was_on = window.settings.mic_on
    before = window.pos()
    start = window.mic_button.mapToGlobal(QPoint(4, 4))
    send_header_mouse(window.mic_button, QEvent.MouseButtonPress, start)
    send_header_mouse(window.mic_button, QEvent.MouseMove, start + QPoint(40, 20))
    send_header_mouse(window.mic_button, QEvent.MouseButtonRelease, start + QPoint(40, 20), held=False)
    assert window.settings.mic_on == was_on
    assert not window.mic_button.isDown()
    assert window.pos() == before + QPoint(40, 20)


# ---- settings file ----------------------------------------------------------

def test_settings_round_trip(tmp_path):
    path = tmp_path / "sub" / "ui.json"
    config.save(Settings(my_lang="en", their_lang="zh", font_px=22, mic_on=False), path)
    loaded = config.load(path)
    assert (loaded.my_lang, loaded.their_lang, loaded.font_px, loaded.mic_on) == ("en", "zh", 22, False)


def test_missing_or_broken_file_gives_defaults(tmp_path):
    assert config.load(tmp_path / "none.json") == Settings()
    broken = tmp_path / "ui.json"
    broken.write_text("{not json", encoding="utf-8")
    assert config.load(broken) == Settings()
    broken.write_text("[1, 2]", encoding="utf-8")
    assert config.load(broken) == Settings()


def test_bad_values_are_repaired(tmp_path):
    path = tmp_path / "ui.json"
    path.write_text('{"my_lang": "xx", "their_lang": "fr", "font_px": 999, "backdrop": -5,'
                    ' "mic_on": "yes", "unknown": 1, "w": 10}', encoding="utf-8")
    loaded = config.load(path)
    assert loaded.my_lang == "vi" and loaded.their_lang == AUTO
    assert loaded.font_px == config.FONT_RANGE[1] and loaded.backdrop == 0
    assert loaded.mic_on is True          # wrong type → default
    assert loaded.w == config.MIN_SIZE[0]


# ---- chat log ---------------------------------------------------------------

def test_same_id_updates_the_row(app):
    log = LogView()
    log.add_or_update(Utterance(id=1, source="speaker", speaker=1, original="你", src_lang="zh",
                                dst_lang="en"))
    row = log.add_or_update(Utterance(id=1, source="speaker", speaker=1, original="你好",
                                      translation="Hello", src_lang="zh", dst_lang="en", final=True,
                                      latency_ms=800))
    assert len(log.rows()) == 1
    assert "Hello" in row.translation.text() and "你好" in row.original.text()
    assert "0.8 s" not in row.header.text() and "Speaker 1" in row.header.text()   # no delay shown
    assert row.main_text() == "你好"          # a click copies what was said, not the translation


def test_unfinished_line_says_listening(app):
    log = LogView()
    row = log.add_or_update(Utterance(id=1, source="speaker", speaker=2, original="Wait",
                                      src_lang="en", dst_lang="vi"))
    assert "listening" in row.translation.text() and "Wait" in row.original.text()


def test_original_can_be_hidden_and_text_is_escaped(app):
    log = LogView()
    row = log.add_or_update(Utterance(id=1, source="speaker", original="<b>hi</b>", translation="xin chào",
                                      src_lang="en", dst_lang="vi", final=True))
    assert "&lt;b&gt;" in row.original.text()
    assert not row.original.isHidden()
    log.set_look(17, False, False)
    assert row.original.isHidden() and not row.translation.isHidden()


def test_same_language_shows_only_the_heard_text(app):
    log = LogView()
    row = log.add_or_update(Utterance(id=1, source="speaker", original="Xin chào", src_lang="vi",
                                      dst_lang="vi", final=True))
    assert row.translation.isHidden() and row.main_text() == "Xin chào"


def test_my_lines_show_chatbox_result(app):
    log = LogView()
    ok = log.add_or_update(Utterance(id=1, source="mic", original="a", translation="b", src_lang="vi",
                                     dst_lang="en", final=True, sent=True))
    bad = log.add_or_update(Utterance(id=2, source="typed", original="a", translation="b",
                                      src_lang="vi", dst_lang="en", final=True, sent=False))
    assert "You" in ok.header.text() and "sent" not in ok.header.text()   # success needs no label
    assert "not sent" in bad.header.text() and "typed" in bad.header.text()


def test_old_rows_are_dropped(app):
    log = LogView()
    for number in range(MAX_ROWS + 5):
        log.add_or_update(Utterance(id=number, source="speaker", original="x", final=True))
    assert len(log.rows()) == MAX_ROWS
    assert log.rows()[0].utterance.id == 5
    log.clear()
    assert log.rows() == []


# ---- main window ------------------------------------------------------------

def test_mic_button_flips_tells_backend_and_saves(window):
    before = len(window.backend.applied)
    window.mic_button.click()
    assert window.settings.mic_on is False
    assert len(window.backend.applied) == before + 1 and window.backend.applied[-1][0] is False
    assert window.saved and window.saved[-1].mic_on is False
    assert "off" in window.mic_button.toolTip()


def test_typed_text_goes_to_backend(window):
    assert not window.send_button.isEnabled()
    window.input.setText("   ")
    assert not window.send_button.isEnabled()
    window.send_typed()
    assert window.backend.sent == []
    window.input.setText("  xin chào  ")
    assert window.send_button.isEnabled()
    window.send_typed()
    assert window.backend.sent == ["xin chào"] and window.input.text() == ""


def test_send_language_menu(window):
    assert window.send_button.text() == "Send · Auto EN"
    assert window.send_lang_actions["auto"].isChecked()
    window.send_lang_actions["zh"].trigger()
    assert window.settings.send_lang == "zh" and window.saved[-1].send_lang == "zh"
    assert window.send_lang_actions["zh"].isChecked() and not window.send_lang_actions["auto"].isChecked()
    window.backend.target_lang = lambda: window.settings.send_lang
    window.send_lang_actions["vi"].trigger()
    assert window.send_button.text() == "Send · VI" and "Vietnamese" in window.send_button.toolTip()


def test_voice_language_swap_keeps_the_typed_language_and_saves_both(app, tmp_path):
    path = tmp_path / "ui.json"
    backend = DemoBackend()
    window = MainWindow(backend, Settings(my_lang="en", their_lang="vi"),
                        save=lambda settings: config.save(settings, path))
    try:
        window.send_lang_actions["zh"].trigger()
        assert backend.speech_target_lang() == "vi"
        assert window.send_button.text() == "Send · ZH"
        window.swap_button.click()
        assert (window.my_lang.currentData(), window.their_lang.currentData()) == ("vi", "en")
        assert backend.speech_target_lang() == "en"
        assert window.send_button.text() == "Send · ZH" and window.send_lang_actions["zh"].isChecked()
        loaded = config.load(path)
        assert (loaded.my_lang, loaded.their_lang, loaded.send_lang) == ("vi", "en", "zh")
    finally:
        window.close()
        window.deleteLater()


def test_auto_send_target_follows_the_language_heard(window):
    heard = ["en"]
    window.backend.target_lang = lambda: heard[0]
    heard[0] = "zh"
    window.show_utterance(Utterance(id=1, source="speaker", speaker=1, original="你好", translation="hi",
                                    src_lang="zh", dst_lang="vi", final=True))
    assert window.send_button.text() == "Send · Auto ZH"


def test_bad_send_language_in_file_falls_back(tmp_path):
    path = tmp_path / "ui.json"
    path.write_text('{"send_lang": "fr"}', encoding="utf-8")
    assert config.load(path).send_lang == AUTO


def test_window_language_button(window):
    window.show_utterance(Utterance(id=1, source="typed", original="a", translation="b", src_lang="vi",
                                    dst_lang="en", final=True, sent=False,
                                    note="not translated: no internet, cut to 144 characters"))
    window.open_settings()
    window._dialog.nav.setCurrentRow(2)
    try:
        window.ui_lang_actions["vi"].trigger()
        assert window.settings.ui_lang == "vi" and window.saved[-1].ui_lang == "vi"
        assert window.send_button.text() == "Gửi · Tự động EN"
        assert window.input.placeholderText().startswith("Nhập tin nhắn")
        assert window.their_lang.itemText(0) == "Tự nhận biết" and window.my_lang.itemText(0) == "Tiếng Anh"
        assert "bật" in window.mic_button.toolTip()
        header = window.log.rows()[0].header.text()
        assert "Bạn" in header and "chưa gửi" in header
        assert "chưa dịch: no internet, đã cắt còn 144 ký tự" in header
        assert window._dialog.windowTitle() == "Cài đặt" and window._dialog.nav.currentRow() == 2
        assert window._dialog.nav.item(0).text() == "Dịch"
        window.ui_lang_actions["zh"].trigger()
        assert window.send_button.text() == "发送 · 自动 EN" and window.status.text() == "VRChat"
        window.ui_lang_actions["en"].trigger()
        assert window.send_button.text() == "Send · Auto EN" and "You" in window.log.rows()[0].header.text()
    finally:
        i18n.set_lang("en")


def test_cantonese_is_its_own_option(window, tmp_path):
    def codes(combo):
        return [combo.itemData(i) for i in range(combo.count())]
    assert codes(window.my_lang) == ["en", "zh", "yue", "vi", "ja", "ko"]
    assert codes(window.their_lang) == ["auto", "en", "zh", "yue", "vi", "ja", "ko"]
    assert list(window.send_lang_actions) == ["auto", "en", "zh", "yue", "vi", "ja", "ko"]
    path = tmp_path / "ui.json"
    path.write_text('{"my_lang": "yue", "their_lang": "yue", "send_lang": "yue"}', encoding="utf-8")
    loaded = config.load(path)
    assert (loaded.my_lang, loaded.their_lang, loaded.send_lang) == ("yue", "yue", "yue")
    window.backend.target_lang = lambda: "yue"
    window.show_utterance(Utterance(id=1, source="speaker", original="你食咗飯未", translation="Eaten yet?",
                                    src_lang="yue", dst_lang="en", final=True))
    assert "ZH(HK) → EN" in window.log.rows()[0].header.text()
    assert window.send_button.text() == "Send · Auto ZH(HK)" and "Cantonese" in window.send_button.toolTip()


@pytest.mark.parametrize("code, text", [("ja", "今日は何をしますか？"), ("ko", "오늘 뭐 해요?")])
def test_japanese_and_korean_select_save_and_display_translation(window, tmp_path, code, text):
    window.my_lang.setCurrentIndex(window.my_lang.findData(code))
    window.their_lang.setCurrentIndex(window.their_lang.findData(code))
    window.backend.target_lang = lambda: window.settings.send_lang
    window.send_lang_actions[code].trigger()
    assert window.send_button.text() == "Send · " + code.upper()
    path = tmp_path / "languages.json"
    config.save(window.settings, path)
    loaded = config.load(path)
    assert (loaded.my_lang, loaded.their_lang, loaded.send_lang) == (code, code, code)
    settings = SettingsWindow(loaded, window)
    assert settings.my_lang.currentData() == settings.their_lang.currentData() == code
    row = window.log.add_or_update(Utterance(id=81, source="speaker", original=text,
        translation="What are you doing today?", src_lang=code, dst_lang="en", final=True))
    assert row.other_language() == ""
    assert text in row.original.text() and "What are you doing" in row.translation.text()
    assert code.upper() + " → EN" in row.header.text()
    settings.deleteLater()


def test_a_language_off_the_list_is_only_announced(app):
    log = LogView()
    spanish = log.add_or_update(Utterance(id=1, source="speaker", original="Hola", translation="Hello",
                                         src_lang="es", dst_lang="en", final=True, latency_ms=700))
    assert "【Speaking Spanish】" in spanish.original.text() and "Hola" not in spanish.original.text()
    assert spanish.translation.isHidden() and "→" not in spanish.header.text()
    assert spanish.main_text() == "【Speaking Spanish】"
    rare = log.add_or_update(Utterance(id=2, source="speaker", original="x", src_lang="sw", final=True))
    assert "【Speaking SW】" in rare.original.text()                    # no name known: the code
    ours = log.add_or_update(Utterance(id=3, source="speaker", original="你食咗飯未", translation="Eaten?",
                                       src_lang="yue", dst_lang="en", final=True))
    assert ours.other_language() == "" and "Eaten?" in ours.translation.text()
    mine = log.add_or_update(Utterance(id=4, source="mic", original="Hola", src_lang="es", final=True))
    still = log.add_or_update(Utterance(id=5, source="speaker", original="Hola", src_lang="es"))
    assert mine.other_language() == "" and still.other_language() == ""   # only finished lines of others
    try:
        i18n.set_lang("vi")
        log.refresh()
        assert "【Đang nói tiếng Tây Ban Nha】" in spanish.original.text()
    finally:
        i18n.set_lang("en")


def test_language_boxes_fit_their_text(window):
    def fits(combo):
        text = combo.fontMetrics().horizontalAdvance(combo.currentText())
        return text + 18 <= combo.width() <= text + 26       # padding only: no empty arrow area
    try:
        english = window.their_lang.width()
        window.ui_lang_actions["vi"].trigger()
        assert window.their_lang.currentText() == "Tự nhận biết"
        assert fits(window.their_lang) and fits(window.my_lang)
        assert window.their_lang.width() != english            # resized for the new text
        wide = window.their_lang.width()
        window.their_lang.setCurrentIndex(window.their_lang.findData("en"))   # "Tiếng Anh": shorter
        assert fits(window.their_lang) and window.their_lang.width() < wide
    finally:
        i18n.set_lang("en")


def test_microphone_picker(window, monkeypatch):
    from ui import settings_window
    monkeypatch.setattr(settings_window, "input_devices", lambda: ["Mic A", "Mic B"])
    window.settings.mic_device = "Old headset"                  # saved, but unplugged now
    dialog = SettingsWindow(window.settings, window)
    dialog.changed.connect(window.settings_changed)
    names = [dialog.mic_device.itemText(i) for i in range(dialog.mic_device.count())]
    assert names == ["Windows default", "Mic A", "Mic B", "Old headset"]
    assert dialog.mic_device.currentText() == "Old headset"
    dialog.mic_device.setCurrentIndex(1)
    assert window.settings.mic_device == "Mic A" and window.saved[-1].mic_device == "Mic A"
    dialog.mic_device.setCurrentIndex(0)
    assert window.settings.mic_device == ""


def test_hearing_engine_and_detector_strictness(window, tmp_path):
    from engine import services
    services.save("custom_second", url="https://second.test/v1")
    dialog = SettingsWindow(window.settings, window)
    dialog.changed.connect(window.settings_changed)
    slider, label, _, _ = dialog._sliders["vad_sensitivity"]
    assert slider.value() == 70 and label.text() == "70%" and dialog.hearing.currentData() == "custom"
    slider.setValue(55)
    assert window.settings.vad_sensitivity == 0.55 and label.text() == "55%"
    mic_slider, mic_label, _, _ = dialog._sliders["mic_vad_sensitivity"]
    assert mic_slider.value() == 50 and mic_label.text() == "50%"
    mic_slider.setValue(65)
    assert window.settings.mic_vad_sensitivity == 0.65 and window.settings.vad_sensitivity == 0.55
    dialog.hearing.setCurrentIndex(dialog.hearing.findData("custom_second"))
    assert window.settings.hearing == "custom_second" and window.saved[-1].hearing == "custom_second"
    dialog.translating.setCurrentIndex(dialog.translating.findData("custom_second"))
    assert window.settings.translating == "custom_second" and window.saved[-1].translating == "custom_second"
    assert dialog.translating.findData("local") >= 0          # local translation is available too
    dialog._sliders["font_px"][0].setValue(20)
    assert window.settings.font_px == 20 and isinstance(window.settings.font_px, int)
    path = tmp_path / "ui.json"
    config.save(window.settings, path)
    loaded = config.load(path)
    assert loaded.vad_sensitivity == 0.55 and (loaded.hearing, loaded.translating) == ("custom_second", "custom_second")
    path.write_text('{"vad_sensitivity": 5.0, "mic_vad_sensitivity": 0.01, "hearing": "cloud"}',
                    encoding="utf-8")
    loaded = config.load(path)
    assert loaded.vad_sensitivity == config.VAD_RANGE[1] and loaded.hearing == "custom"
    assert loaded.mic_vad_sensitivity == config.VAD_RANGE[0]


def test_settings_from_version_0_9_7_keep_the_local_model(tmp_path):
    path = tmp_path / "ui.json"
    path.write_text('{"stt_engine": "local"}', encoding="utf-8")
    assert config.load(path).hearing == "local"
    path.write_text('{"stt_engine": "cloud"}', encoding="utf-8")    # the old online engine
    assert config.load(path).hearing == "custom"


def test_settings_show_the_program_picture_and_version(window):
    import ui
    dialog = SettingsWindow(window.settings, window)
    assert not dialog.program_picture.pixmap().isNull()
    assert dialog.version.text() == f"v{ui.__version__}"


def test_models_page_sets_up_each_service(window, tmp_path, monkeypatch):
    import json
    from engine import services
    from ui.settings_window import ServiceDialog
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    dialog = SettingsWindow(window.settings, window)
    assert dialog.nav.item(dialog.nav.count() - 1).text() == "Models"
    assert list(dialog._service_status) == ["custom"]
    assert dialog._service_status["custom"].text() == "Not set up"
    code = ServiceDialog("custom", dialog)
    assert not code.url.isHidden() and code.hear_model.isHidden() and code.translate_model.isHidden()
    assert not code.findChildren(QComboBox)
    code.url.setText("https://custom.test/v1")
    code.key.setText("  custom-key-1  ")
    code._auto_fetch.stop()
    code.save()
    dialog.show_service_status("custom")
    assert dialog._service_status["custom"].text() == "Ready"
    openai = ServiceDialog("openai", dialog)
    assert openai.hear_model.placeholderText() == "whisper-1"     # the default shows, the field is empty
    openai.key.setText("sk-1")
    openai.translate_model.setText("gpt-5.4-nano, gpt-5.4-mini")
    openai.save()
    again = ServiceDialog("openai", dialog)
    assert again.key.text() == "" and "Saved" in again.key.placeholderText()
    again.save()                                                  # an empty key field keeps the key
    saved = json.loads(services.models_file().read_text(encoding="utf-8"))
    assert saved["custom"] == {"key": "custom-key-1", "url": "https://custom.test/v1"}
    assert saved["openai"] == {"key": "sk-1", "translate_model": "gpt-5.4-nano, gpt-5.4-mini"}
    assert services.translate_models("openai") == ["gpt-5.4-nano", "gpt-5.4-mini"]
    mimo = ServiceDialog("mimo", dialog)
    assert mimo.hear_model.isHidden() and not mimo.translate_model.isHidden()   # MiMo only translates


def test_custom_domain_dialog_fetch_and_pick_models(window, tmp_path, monkeypatch):
    import json
    from engine import services
    from ui.settings_window import ServiceDialog
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    dialog = SettingsWindow(window.settings, window)

    monkeypatch.setattr(services, "fetch_models", lambda service="custom", url="", key="", http=None: ["whisper-custom", "gpt-4o-custom"])
    custom_dlg = ServiceDialog("custom", dialog)
    assert hasattr(custom_dlg, "fetch_btn")
    assert not custom_dlg.findChildren(QComboBox)
    custom_dlg.url.setText("http://127.0.0.1:8000/v1")
    custom_dlg.key.setText("my-secret-key")
    custom_dlg.fetch_models()
    wait_for_models(custom_dlg)
    assert "Found 2 models" in custom_dlg.result.text()
    assert custom_dlg._fetched_models == ["whisper-custom", "gpt-4o-custom"]
    custom_dlg.save()
    dialog.sync()
    hear = dialog.model_pickers["hearing"]
    translate = dialog.model_pickers["translating"]
    hear.setCurrentIndex(hear.findData("whisper-custom"))
    translate.setCurrentIndex(translate.findData("gpt-4o-custom"))

    saved = json.loads(services.models_file().read_text(encoding="utf-8"))
    assert saved["custom"]["url"] == "http://127.0.0.1:8000/v1"
    assert saved["custom"]["key"] == "my-secret-key"
    assert saved["custom"]["hear_model"] == "whisper-custom"
    assert saved["custom"]["translate_model"] == "gpt-4o-custom"

    # Test error/timeout behavior and retry button
    def raise_timeout(*args, **kwargs):
        raise TimeoutError("connection timed out")
    monkeypatch.setattr(services, "fetch_models", raise_timeout)
    custom_dlg.fetch_models()
    wait_for_models(custom_dlg)
    assert "Timed out" in custom_dlg.result.text()
    assert custom_dlg.fetch_btn.text() == "Try again"
    assert custom_dlg.fetch_btn.isEnabled()


def wait_for_models(dialog):
    from PySide6.QtTest import QTest
    for _ in range(200):
        QTest.qWait(10)
        if not dialog._fetching and not dialog._auto_fetch.isActive():
            return
    pytest.fail("Model fetch did not finish")


def test_custom_key_auto_fetches_and_saves_separate_model_choices(window, tmp_path, monkeypatch):
    from engine import services
    from ui.settings_window import ServiceDialog
    monkeypatch.setenv("APPDATA", str(tmp_path))
    calls = []
    class Http:
        def get(self, url, headers):
            calls.append((url, headers))
            from types import SimpleNamespace
            return SimpleNamespace(status_code=200, json=lambda: {"data": [{"id": "whisper-new"}, {"id": "chat-new"}]})
    dialog = ServiceDialog("custom", window, http=Http())
    dialog.url.setText("https://custom.test/v1")
    assert dialog.hear_model.placeholderText() == "e.g. whisper-1"
    dialog.key.setText("partial")
    dialog.key.setText("  pasted-custom-key  ")
    assert not calls  # debounce edits before making the request
    wait_for_models(dialog)
    assert calls == [("https://custom.test/v1/models", {"Authorization": "Bearer pasted-custom-key"})]
    assert not services.models_file().exists()  # fetching does not save the key
    dialog.save()
    assert services.setting("custom", "key") == "pasted-custom-key"
    assert services.catalog("custom") == ["chat-new", "whisper-new"]
    models = SettingsWindow(window.settings, window)
    hear = models.model_pickers["hearing"]
    translate = models.model_pickers["translating"]
    hear.setCurrentIndex(hear.findData("whisper-new"))
    translate.setCurrentIndex(translate.findData("chat-new"))
    assert services.setting("custom", "hear_model") == "whisper-new"
    assert services.setting("custom", "translate_model") == "chat-new"


def test_custom_fetch_error_hides_key_and_can_retry(window, tmp_path, monkeypatch):
    from engine import services
    from ui.settings_window import ServiceDialog
    monkeypatch.setenv("APPDATA", str(tmp_path))
    def fail(*a, **kw):
        raise OSError("Rejected credential " + kw["key"])
    monkeypatch.setattr(services, "fetch_models", fail)
    dialog = ServiceDialog("custom", window)
    dialog.url.setText("https://custom.test/v1")
    dialog.key.setText("private-test-key")
    wait_for_models(dialog)
    assert "private-test-key" not in dialog.result.text()
    assert "Rejected credential" in dialog.result.text()
    assert dialog.fetch_btn.isEnabled()
    monkeypatch.setattr(services, "fetch_models", lambda *a, **kw: ["whisper-new"])
    dialog.fetch_btn.click()
    wait_for_models(dialog)
    assert dialog._fetched_models == ["whisper-new"]
    dialog.reject()


def test_model_pickers_follow_domain_and_preserve_each_roles_selection(window):
    from engine import services
    services.save("custom", url="https://a.test", models=["hear-a", "chat-a"], hear_model="hear-a")
    services.save("custom_second", url="https://b.test", models=["hear-b", "chat-b"], translate_model="chat-b")
    dialog = SettingsWindow(window.settings, window)
    hear, translate = dialog.model_pickers["hearing"], dialog.model_pickers["translating"]
    assert hear.currentText() == "hear-a"
    dialog.translating.setCurrentIndex(dialog.translating.findData("custom_second"))
    assert translate.currentText() == "chat-b" and translate.findData("chat-a") == -1
    assert hear.currentText() == "hear-a"
    translate.setEditText("manual-model")
    translate.lineEdit().editingFinished.emit()
    assert services.setting("custom_second", "translate_model") == "manual-model"
    assert services.setting("custom", "hear_model") == "hear-a"


def test_api_setup_preserves_model_choices_when_saving(window):
    from engine import services
    from ui.settings_window import ServiceDialog
    services.save("custom", url="https://a.test", hear_model="hear", translate_model="chat")
    dialog = ServiceDialog("custom", window)
    dialog.domain_name.setText("My API")
    dialog.save()
    assert services.setting("custom", "hear_model") == "hear"
    assert services.setting("custom", "translate_model") == "chat"


@pytest.mark.parametrize("new_key", ["new-key", ""])
def test_custom_key_change_discards_inflight_results(window, tmp_path, monkeypatch, new_key):
    import threading
    from engine import services
    from ui.settings_window import ServiceDialog
    monkeypatch.setenv("APPDATA", str(tmp_path))
    release = threading.Event()
    calls = []
    def fetch(*a, **kw):
        calls.append(kw["key"])
        if kw["key"] == "old-key":
            release.wait(2)
        return [kw["key"] + "-model"]
    monkeypatch.setattr(services, "fetch_models", fetch)
    dialog = ServiceDialog("custom", window)
    dialog.url.setText("https://custom.test/v1")
    try:
        dialog.key.setText("old-key")
        dialog.fetch_models()
        dialog.key.setText(new_key)
        release.set()
        wait_for_models(dialog)
        assert calls == (["old-key", "new-key"] if new_key else ["old-key"])
        assert "old-key-model" not in (dialog._fetched_models or [])
        if new_key:
            assert dialog._fetched_models == ["new-key-model"]
        else:
            assert dialog._fetched_models is None
    finally:
        release.set()
        dialog.reject()


@pytest.mark.parametrize("started", [False, True])
def test_closing_custom_dialog_cancels_pending_auto_fetch(window, tmp_path, monkeypatch, started):
    import threading
    from engine import services
    from ui.settings_window import ServiceDialog
    from PySide6.QtTest import QTest
    monkeypatch.setenv("APPDATA", str(tmp_path))
    calls = []
    release = threading.Event()
    def fetch(*a, **kw):
        calls.append(True)
        release.wait(2)
        return ["late-model"]
    monkeypatch.setattr(services, "fetch_models", fetch)
    dialog = ServiceDialog("custom", window)
    dialog.url.setText("https://custom.test/v1")
    dialog.key.setText("test-key")
    if started:
        dialog.fetch_models()
    dialog.reject()
    release.set()
    QTest.qWait(550)
    assert calls == ([True] if started else [])
    assert dialog._fetched_models is None
    assert not services.models_file().exists()


NOT_DOWNLOADED = "the Local Model is not downloaded yet (Settings → Models)"


def test_the_local_model_is_downloaded_before_hearing_switches_to_it(window, monkeypatch):
    from engine import local_model
    from ui import local_download, settings_window
    state = {"missing": NOT_DOWNLOADED}
    monkeypatch.setattr(local_model, "installed", lambda model=None: True)
    monkeypatch.setattr(local_model, "missing", lambda model=None: state["missing"])
    opened = []
    monkeypatch.setattr(settings_window.LocalModelDialog, "exec", lambda self: opened.append(self))
    dialog = SettingsWindow(window.settings, window)
    dialog.changed.connect(window.settings_changed)
    assert dialog._local_status.text() == "Not downloaded"
    dialog.hearing.setCurrentIndex(dialog.hearing.findData("local"))
    # its window opens; until everything has arrived, hearing stays as it was
    assert len(opened) == 1 and window.settings.hearing == "custom" and dialog.hearing.currentData() == "custom"
    local_download.shared().finished.emit("not enough free space on C:")
    assert window.settings.hearing == "custom"
    state["missing"] = ""
    local_download.shared().finished.emit("")
    assert window.settings.hearing == "local" and window.saved[-1].hearing == "local"
    assert dialog._local_status.text() == "Ready"


def test_the_local_model_s_window_downloads_stops_and_says_how_it_ended(window, monkeypatch):
    from PySide6.QtCore import QObject, Signal

    from engine import local_model
    from ui.settings_window import LocalModelDialog

    class Download(QObject):
        progress = Signal(float, float)
        finished = Signal(str)

        def __init__(self):
            super().__init__()
            self.active, self.calls = False, []

        def start(self, model=None):
            self.model = model
            self.active = True
            self.calls.append("start")

        def stop(self):
            self.calls.append("stop")
    state = {"missing": NOT_DOWNLOADED}
    monkeypatch.setattr(local_model, "installed", lambda model=None: True)
    monkeypatch.setattr(local_model, "nvidia_card", lambda: True)
    monkeypatch.setattr(local_model, "missing", lambda model=None: state["missing"])
    monkeypatch.setattr(local_model, "arrived", lambda root=None, model=None: 0)
    monkeypatch.setattr(local_model, "ready", lambda root=None, model=None: not state["missing"])
    download = Download()
    dialog = LocalModelDialog(window, download=download)
    row = dialog.rows["sensevoice"]
    other = dialog.rows["nllb-200-ct2"]
    assert row["action"].text() == "Download" and not row["action"].isHidden()
    assert not dialog.findChildren(QComboBox)
    row["action"].click()
    assert download.calls == ["start"] and row["action"].text() == "Stop"
    assert download.model == "sensevoice" and not other["action"].isEnabled()
    other_before = other["result"].text()
    download.progress.emit(float(2**30), float(2 * 2**30))
    assert row["bar"].value() == 500 and row["result"].text() == "1.0 GB of 2.0 GB"
    assert other["result"].text() == other_before
    row["action"].click()
    assert download.calls == ["start", "stop"] and not row["action"].isEnabled()
    download.active = False
    download.finished.emit("stopped")
    assert row["action"].text() == "Download" and row["action"].isEnabled()
    download.finished.emit("not enough free space on C:")
    assert row["result"].text() == "✗ not enough free space on C:"
    state["missing"] = ""
    download.finished.emit("")
    assert row["result"].text() == "Ready" and not row["action"].isEnabled() and row["bar"].isHidden()
    assert row["use"].isEnabled()


def test_domain_buttons_add_cancel_and_remove_without_touching_other_settings(window, monkeypatch):
    from engine import services
    from ui.settings_window import ServiceDialog
    dialog = SettingsWindow(window.settings, window)
    assert set(dialog._service_status) == {"custom"}
    monkeypatch.setattr(ServiceDialog, "exec", lambda self: 0)
    dialog.add_domain()
    assert services.offered() == ("custom",)
    def save_new(self):
        assert self.domain_name.text() == "Custom domain 2"
        self.domain_name.setText("Second API")
        self.url.setText("https://second.test/v1")
        self.key.setText("second-key")
        self.save()
        return 1
    monkeypatch.setattr(ServiceDialog, "exec", save_new)
    plus = next(b for b in dialog._domains_host.findChildren(QPushButton) if b.text() == "+")
    plus.click()
    added = next(s for s in services.offered() if s != "custom")
    assert services.title(added) == "Second API"
    assert services.setting(added, "key") == "second-key"
    assert set(dialog._service_status) == {"custom", added}
    dialog.hearing.setCurrentIndex(dialog.hearing.findData(added))
    dialog.translating.setCurrentIndex(dialog.translating.findData(added))
    assert window.settings.hearing == window.settings.translating == added
    minus = next(b for b in dialog._domains_host.findChildren(QPushButton) if b.text() == "−" and b.isEnabled())
    minus.click()
    assert window.settings.hearing == window.settings.translating == "custom"
    assert services.offered() == ("custom",)


def test_local_model_picker_keeps_hearing_and_translation_separate(window, monkeypatch):
    from engine import local_model
    from ui.settings_window import LocalModelDialog
    monkeypatch.setattr(local_model, "missing", lambda model=None: "")
    monkeypatch.setattr(local_model, "ready", lambda root=None, model=None: True)
    dialog = LocalModelDialog(window, role="translating")
    assert set(dialog.rows) == set(local_model.MODELS)
    local_model.select("sensevoice")
    window.settings.hearing = "custom"
    dialog.selected.connect(window._activate_local)
    dialog.rows["nllb-200-ct2"]["use"].click()
    assert window.settings.translating == "local"
    assert window.settings.hearing == "custom"
    assert local_model.selected() == "sensevoice"


def test_cpu_choices_can_download_without_nvidia(window, monkeypatch):
    from engine import local_model
    from ui.settings_window import LocalModelDialog
    monkeypatch.setattr(local_model, "installed", lambda model=None: True)
    monkeypatch.setattr(local_model, "nvidia_card", lambda: False)
    dialog = LocalModelDialog(window)
    for model in ("sensevoice", "nllb-200-ct2"):
        row = dialog.rows[model]
        assert not row["action"].isHidden() and row["action"].isEnabled()
        assert not row["use"].isEnabled()


def test_translation_download_completion_activates_only_translation(window, monkeypatch):
    from engine import local_model
    from ui import local_download
    monkeypatch.setattr(local_download.shared(), "model", "nllb-200-ct2")
    monkeypatch.setattr(local_model, "missing", lambda model=None: "")
    window.settings.hearing = "custom"
    window.settings.translating = "custom"
    window._local_model_arrived("connection failed")
    assert window.settings.translating == "custom"
    window._local_model_arrived("")
    assert window.settings.translating == "local"
    assert window.settings.hearing == "custom"


def test_local_download_captures_model_before_worker_runs(app):
    from ui.local_download import LocalDownload
    calls = []
    download = LocalDownload(fetch=lambda **kwargs: calls.append(kwargs["model"]))
    download.model = "sensevoice"
    download._run()
    assert calls == ["sensevoice"]


def test_a_pc_without_an_nvidia_card_is_told_so_and_offered_no_download(window, monkeypatch):
    from engine import local_model
    from ui.settings_window import LocalModelDialog
    monkeypatch.setattr(local_model, "installed", lambda model=None: True)
    monkeypatch.setattr(local_model, "nvidia_card", lambda: False)
    dialog = LocalModelDialog(window)
    for model in ("large-v3-turbo", "large-v3"):
        row = dialog.rows[model]
        assert "NVIDIA graphics card" in row["result"].text() and not row["action"].isEnabled()


def test_the_download_tells_the_window_how_it_ended(app):
    from engine import local_model
    from ui.local_download import STOPPED, LocalDownload

    def run(fetch) -> list[str]:
        download, ended = LocalDownload(fetch=fetch), []
        download.finished.connect(ended.append)
        download.active = True
        download._run()
        assert download.active is False
        return ended

    def no_room(progress, stop, model=None):
        raise local_model.DownloadError("no room")

    def stopped(progress, stop, model=None):
        raise local_model.Stopped("stopped")
    assert run(lambda progress, stop, model=None: progress(5, 5)) == [""]
    assert run(no_room) == ["no room"] and run(stopped) == [STOPPED]


def test_status_tooltip_is_translated_line_by_line(window):
    from ui.backend import Status
    try:
        window.ui_lang_actions["vi"].trigger()
        window.show_status(Status("warn", "No game sound", "Start VRChat. The window finds it by itself.\n"
                                  "VRChat's sound is not captured: access denied"))
        assert window.status.text() == "VRChat"
        assert window.status.toolTip() == ("Hãy mở VRChat. Cửa sổ sẽ tự tìm thấy nó.\n"
                                           "Không thu được âm thanh của VRChat: access denied")
    finally:
        i18n.set_lang("en")


def test_every_text_has_both_translations():
    assert set(i18n.TABLES["zh"]) == set(i18n.TABLES["vi"])
    for table in i18n.TABLES.values():
        for english, translated in table.items():
            assert translated.strip()
            for slot in ("{what}", "{lang}", "{n}"):
                assert (slot in english) == (slot in translated), english


def test_swap_languages(window):
    assert not window.swap_button.isEnabled()        # "They speak" is Auto-detect
    window._swap()
    assert (window.settings.my_lang, window.settings.their_lang) == ("vi", AUTO)
    window.their_lang.setCurrentIndex(window.their_lang.findData("zh"))
    assert window.settings.their_lang == "zh" and window.swap_button.isEnabled()
    window.swap_button.click()
    assert (window.settings.my_lang, window.settings.their_lang) == ("zh", "vi")
    assert window.my_lang.currentData() == "zh"


def test_utterance_updates_log_and_delay(window):
    window.show_utterance(Utterance(id=1, source="speaker", speaker=1, original="hi", translation="chào",
                                    src_lang="en", dst_lang="vi", final=True, latency_ms=1250))
    assert len(window.log.rows()) == 1 and window.delay.text() == "1.2 s"


def test_bars_hide_and_return(window):
    window._show_bars(False)
    assert window.bars.isHidden() and window.input_bar.isHidden()
    window.settings.auto_hide_bars = False
    window.settings_changed()
    assert window.bars_shown() and not window.input_bar.isHidden()


def test_settings_window_edits_shared_settings(window):
    dialog = SettingsWindow(window.settings, window)
    dialog.changed.connect(window.settings_changed)
    dialog._switches["vad_on"].click()
    assert window.settings.vad_on is False and "off" in window.vad_button.toolTip()
    dialog._sliders["font_px"][0].setValue(24)
    assert window.settings.font_px == 24
    window._dialog = dialog
    window.vad_button.click()                                 # changed in the main window…
    assert dialog._switches["vad_on"].isChecked() is True    # …shows in the dialog
    assert "mic_on" not in dialog._switches and "subtitles_on" not in dialog._switches   # top bar only


def test_add_speaker_words_switch_saves_and_restores(window, tmp_path):
    path = tmp_path / "ui.json"
    window._save = lambda settings: config.save(settings, path)
    window.open_settings()
    switch = window._dialog._switches["chatbox_speaker"]
    assert not switch.isChecked() and not window.settings.chatbox_speaker
    switch.click()
    assert window.settings.chatbox_speaker and config.load(path).chatbox_speaker
    assert not window.settings.chatbox_original
    window._dialog.close()
    window.open_settings()
    assert switch.isChecked()
    switch.click()
    assert not config.load(path).chatbox_speaker


# ---- demo engine ------------------------------------------------------------

def run_demo(demo, ticks):
    heard = []
    demo.utterance.connect(heard.append)
    for _ in range(ticks):
        demo._tick()
    return heard


def test_demo_plays_lines_to_the_end(app):
    demo = DemoBackend()
    heard = run_demo(demo, 400)
    finals = [u for u in heard if u.final]
    assert finals and finals[0].source == "speaker" and finals[0].translation.startswith("Xin chào")
    mine = [u for u in finals if u.source == "mic"]
    assert mine and mine[0].src_lang == "vi" and mine[0].dst_lang == "zh" and mine[0].sent is False


def test_demo_respects_switches(app):
    demo = DemoBackend()
    demo.apply_settings(Settings(subtitles_on=False, mic_on=False))
    assert run_demo(demo, (PAUSE_TICKS + 2) * 6) == []


def test_demo_typed_text_is_marked_not_sent(app):
    demo = DemoBackend()
    heard = []
    demo.utterance.connect(heard.append)
    demo.send_text("hello")
    assert heard[0].source == "typed" and heard[0].sent is False and "demo" in heard[0].note


def test_demo_voice_and_typed_auto_use_the_same_rules_as_live(app):
    demo = DemoBackend()
    demo.apply_settings(Settings(my_lang="en", their_lang="vi", send_lang=AUTO))
    heard = []
    demo.utterance.connect(heard.append)
    for _ in range(300):
        demo._tick()
        if heard and heard[-1].source == "mic" and heard[-1].final:
            break
    mine = [u for u in heard if u.source == "mic" and u.final]
    assert mine and mine[0].dst_lang == "vi"
    demo.send_text("hello")
    assert heard[-1].source == "typed" and heard[-1].dst_lang == "zh"


def test_a_see_through_window_shows_only_the_letters(window):
    """Low background darkness: no box behind a line or behind the buttons, a letter shadow instead."""
    window.backend.utterance.emit(Utterance(id=1, source="speaker", original="你好", translation="xin chào",
                                            src_lang="zh", dst_lang="vi", final=True))
    row = window.log.rows()[0]
    for backdrop, shadow in ((85, False), (20, True), (0, True), (60, False)):
        window.settings.backdrop = backdrop
        window.settings_changed()
        assert (row.graphicsEffect() is not None) is shadow
        assert "rgba(0,0,0" not in row.styleSheet() and "rgba(0,0,0" not in window.bars.styleSheet()
    window.settings.backdrop = 0
    window.settings_changed()
    assert theme.DIM not in row.original.text()          # the small grey text is lighter here


def test_the_program_icon_loads(app):
    from ui.main import ICON_FILE, program_icon
    assert ICON_FILE.exists() and ICON_FILE.with_suffix(".ico").exists()
    sizes = program_icon().availableSizes()
    assert sizes and sizes[0].width() == 512


def test_models_page_shows_currently_in_use_and_updates_on_switch(window, app):
    from engine import services
    services.save("custom_a", name="Domain A", url="https://a.test/v1", hear_model="whisper-1", translate_model="gpt-5.4-mini")
    services.save("custom_b", name="Domain B", url="https://b.test/v1", hear_model="gemini-3.5-flash-lite", translate_model="gemini-3.5-flash-lite")
    dialog = SettingsWindow(window.settings, window)
    window._dialog = dialog
    assert "Currently in use:" in dialog._hearing_desc.text()
    assert "Currently in use:" in dialog._translating_desc.text()

    window.backend.setting_switched.emit("hearing", "custom_a")
    assert window.settings.hearing == "custom_a"
    assert dialog.hearing.currentData() == "custom_a"
    assert "whisper-1" in dialog._hearing_desc.text()

    window.backend.setting_switched.emit("translating", "custom_a")
    assert window.settings.translating == "custom_a"
    assert dialog.translating.currentData() == "custom_a"
    assert "gpt-5.4-mini" in dialog._translating_desc.text()

    from engine import services
    services.save("custom_a", translate_model="gpt-5.4-mini, gpt-4o")
    window.backend.current_translating_model = "gpt-4o"
    window.backend.setting_switched.emit("translating_model", "gpt-4o")
    assert "gpt-4o" in dialog._translating_desc.text()

    # Both model and service are shown in description
    assert "Domain A" in dialog._hearing_desc.text()
    assert "Domain A" in dialog._translating_desc.text()

    # When hearing is local and ready, it shows Whisper and Local Model
    from engine import local_model
    monkeypatch_local = True
    window.settings.hearing = "local"
    dialog.sync()
    assert "Whisper" in dialog._hearing_desc.text()
    assert "Local Model" in dialog._hearing_desc.text()

    # When switching to Gemini via _handle_model_switched, both service dropdown and description update
    window._handle_model_switched("translating", "custom_b", "gemini-3.5-flash-lite")
    assert window.settings.translating == "custom_b"
    assert dialog.translating.currentData() == "custom_b"
    assert "gemini-3.5-flash-lite" in dialog._translating_desc.text()
    assert "Domain B" in dialog._translating_desc.text()


def test_switch_model_dialog_asks_to_switch_to_ready_model(window, app, monkeypatch):
    from engine import services
    from ui.switch_dialog import SwitchModelDialog

    services.save("custom_b", url="https://b.test/v1", hear_model="gemini-3.5-flash-lite")
    monkeypatch.setattr(services, "ready", lambda s: s == "custom_b")
    dlg = SwitchModelDialog("hearing", "custom", window.settings, reason="timeout", parent=window)
    assert len(dlg.candidates) == 1
    assert dlg.candidates[0][0] == "custom_b"

    switched = []
    dlg.switched.connect(lambda cat, svc, m: switched.append((cat, svc, m)))
    buttons = dlg.findChildren(QPushButton)
    switch_btn = [b for b in buttons if "gemini" in b.text().lower() or b.text() == "Switch"][0]
    switch_btn.click()
    assert switched == [("hearing", "custom_b", "gemini-3.5-flash-lite")]


def test_switch_model_dialog_can_switch_to_local_when_ready_models_exist(window, app, monkeypatch):
    from engine import local_model, services
    from ui.switch_dialog import SwitchModelDialog

    services.save("custom_b", url="https://b.test/v1", hear_model="gemini-3.5-flash-lite")
    monkeypatch.setattr(services, "ready", lambda s: s == "custom_b")
    monkeypatch.setattr(local_model, "missing", lambda model=None: "")  # local is ready!
    dlg = SwitchModelDialog("hearing", "custom", window.settings, reason="timeout", parent=window)

    switched = []
    dlg.switched.connect(lambda cat, svc, m: switched.append((cat, svc, m)))
    buttons = dlg.findChildren(QPushButton)
    local_btn = [b for b in buttons if "Local Model" in b.text()][0]
    local_btn.click()
    assert switched == [("hearing", "local", "Whisper large-v3-turbo")]


def test_switch_model_dialog_recommends_local_model_when_none_ready(window, app, monkeypatch):
    from engine import local_model, services
    from ui.switch_dialog import SwitchModelDialog

    monkeypatch.setattr(services, "ready", lambda s: False)
    monkeypatch.setattr(local_model, "missing", lambda model=None: "")  # local is ready!

    dlg = SwitchModelDialog("hearing", "custom", window.settings, parent=window)
    assert len(dlg.candidates) == 0
    switched = []
    dlg.switched.connect(lambda cat, svc, m: switched.append((cat, svc, m)))

    buttons = dlg.findChildren(QPushButton)
    switch_btn = [b for b in buttons if "Local Model" in b.text()][0]
    switch_btn.click()
    assert switched[0][0] == "hearing" and switched[0][1] == "local"


def test_switch_model_dialog_recommends_download_local_when_none_ready_and_missing(window, app, monkeypatch):
    from engine import local_model, services
    from ui.switch_dialog import SwitchModelDialog

    monkeypatch.setattr(services, "ready", lambda s: False)
    monkeypatch.setattr(local_model, "missing", lambda model=None: "not downloaded")

    dlg = SwitchModelDialog("hearing", "custom", window.settings, parent=window)
    assert len(dlg.candidates) == 0
    opened = []
    dlg.open_local_download.connect(lambda: opened.append(True))

    buttons = dlg.findChildren(QPushButton)
    dl_btn = [b for b in buttons if "Download" in b.text()][0]
    dl_btn.click()
    assert opened == [True]



def test_second_language_picker_saves_syncs_and_can_be_removed(window, tmp_path):
    window.their_lang.setCurrentIndex(window.their_lang.findData("vi"))
    window.their_lang2.setCurrentIndex(window.their_lang2.findData("ja"))
    assert window.settings.their_lang2 == "ja"
    assert not window.swap_button.isEnabled()
    window.open_settings()
    assert window._dialog.their_lang2.currentData() == "ja"
    window._dialog.their_lang2.setCurrentIndex(window._dialog.their_lang2.findData("ko"))
    assert window.their_lang2.currentData() == "ko"
    path = tmp_path / "settings.json"
    config.save(window.settings, path)
    assert config.load(path).their_lang2 == "ko"
    window.their_lang2.setCurrentIndex(0)
    assert window.settings.their_lang2 == "" and window.swap_button.isEnabled()


def test_second_language_cannot_duplicate_primary_or_be_invalid(window):
    window.their_lang.setCurrentIndex(window.their_lang.findData("ja"))
    window.their_lang2.setCurrentIndex(window.their_lang2.findData("ja"))
    assert window.settings.their_lang2 == "" and window.their_lang2.currentData() == ""
    assert Settings(their_lang2="invalid").clean().their_lang2 == ""
    assert Settings(their_lang2=AUTO).clean().their_lang2 == ""
    assert Settings().their_lang2 == ""


def test_log_displays_both_translations(app):
    log = LogView()
    row = log.add_or_update(Utterance(id=99, source="mic", original="Hello", translation="Xin chào",
        translation2="こんにちは", src_lang="en", dst_lang="vi", dst_lang2="ja", final=True))
    assert "Xin chào" in row.translation.text() and "こんにちは" in row.translation2.text()
    assert not row.translation.isHidden() and not row.translation2.isHidden()
    row.set_utterance(Utterance(id=99, source="mic", original="Hello", final=True))
    assert row.translation2.isHidden()
