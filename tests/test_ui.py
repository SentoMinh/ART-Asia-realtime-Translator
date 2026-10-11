import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PySide6.QtWidgets import QApplication

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
        assert window.send_button.text() == "发送 · 自动 EN" and window.status.text() == "启动中…"
        window.ui_lang_actions["en"].trigger()
        assert window.send_button.text() == "Send · Auto EN" and "You" in window.log.rows()[0].header.text()
    finally:
        i18n.set_lang("en")


def test_cantonese_is_its_own_option(window, tmp_path):
    def codes(combo):
        return [combo.itemData(i) for i in range(combo.count())]
    assert codes(window.my_lang) == ["en", "zh", "yue", "vi"]
    assert codes(window.their_lang) == ["auto", "en", "zh", "yue", "vi"]
    assert list(window.send_lang_actions) == ["auto", "en", "zh", "yue", "vi"]
    path = tmp_path / "ui.json"
    path.write_text('{"my_lang": "yue", "their_lang": "yue", "send_lang": "yue"}', encoding="utf-8")
    loaded = config.load(path)
    assert (loaded.my_lang, loaded.their_lang, loaded.send_lang) == ("yue", "yue", "yue")
    window.backend.target_lang = lambda: "yue"
    window.show_utterance(Utterance(id=1, source="speaker", original="你食咗飯未", translation="Eaten yet?",
                                    src_lang="yue", dst_lang="en", final=True))
    assert "ZH(HK) → EN" in window.log.rows()[0].header.text()
    assert window.send_button.text() == "Send · Auto ZH(HK)" and "Cantonese" in window.send_button.toolTip()


def test_a_language_off_the_list_is_only_announced(app):
    log = LogView()
    korean = log.add_or_update(Utterance(id=1, source="speaker", original="안녕하세요", translation="Hello",
                                         src_lang="ko", dst_lang="en", final=True, latency_ms=700))
    assert "【Speaking Korean】" in korean.original.text() and "안녕" not in korean.original.text()
    assert korean.translation.isHidden() and "→" not in korean.header.text()
    assert korean.main_text() == "【Speaking Korean】"
    rare = log.add_or_update(Utterance(id=2, source="speaker", original="x", src_lang="sw", final=True))
    assert "【Speaking SW】" in rare.original.text()                    # no name known: the code
    ours = log.add_or_update(Utterance(id=3, source="speaker", original="你食咗飯未", translation="Eaten?",
                                       src_lang="yue", dst_lang="en", final=True))
    assert ours.other_language() == "" and "Eaten?" in ours.translation.text()
    mine = log.add_or_update(Utterance(id=4, source="mic", original="안녕", src_lang="ko", final=True))
    still = log.add_or_update(Utterance(id=5, source="speaker", original="안녕", src_lang="ko"))
    assert mine.other_language() == "" and still.other_language() == ""   # only finished lines of others
    try:
        i18n.set_lang("vi")
        log.refresh()
        assert "【Đang nói tiếng Hàn】" in korean.original.text()
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
    dialog = SettingsWindow(window.settings, window)
    dialog.changed.connect(window.settings_changed)
    slider, label, _, _ = dialog._sliders["vad_sensitivity"]
    assert slider.value() == 70 and label.text() == "70%" and dialog.hearing.currentData() == "dev"
    slider.setValue(55)
    assert window.settings.vad_sensitivity == 0.55 and label.text() == "55%"
    mic_slider, mic_label, _, _ = dialog._sliders["mic_vad_sensitivity"]
    assert mic_slider.value() == 50 and mic_label.text() == "50%"
    mic_slider.setValue(65)
    assert window.settings.mic_vad_sensitivity == 0.65 and window.settings.vad_sensitivity == 0.55
    dialog.hearing.setCurrentIndex(dialog.hearing.findData("qwen"))
    assert window.settings.hearing == "qwen" and window.saved[-1].hearing == "qwen"
    dialog.translating.setCurrentIndex(dialog.translating.findData("mimo"))
    assert window.settings.translating == "mimo" and window.saved[-1].translating == "mimo"
    assert dialog.translating.findData("local") == -1          # this PC can only hear
    dialog._sliders["font_px"][0].setValue(20)
    assert window.settings.font_px == 20 and isinstance(window.settings.font_px, int)
    path = tmp_path / "ui.json"
    config.save(window.settings, path)
    loaded = config.load(path)
    assert loaded.vad_sensitivity == 0.55 and (loaded.hearing, loaded.translating) == ("qwen", "mimo")
    path.write_text('{"vad_sensitivity": 5.0, "mic_vad_sensitivity": 0.01, "hearing": "cloud"}',
                    encoding="utf-8")
    loaded = config.load(path)
    assert loaded.vad_sensitivity == config.VAD_RANGE[1] and loaded.hearing == "dev"
    assert loaded.mic_vad_sensitivity == config.VAD_RANGE[0]


def test_settings_from_version_0_9_7_keep_the_local_model(tmp_path):
    path = tmp_path / "ui.json"
    path.write_text('{"stt_engine": "local"}', encoding="utf-8")
    assert config.load(path).hearing == "local"
    path.write_text('{"stt_engine": "cloud"}', encoding="utf-8")    # the old online engine
    assert config.load(path).hearing == "dev"


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
    assert list(dialog._service_status) == ["dev", "openai", "gemini", "qwen", "mimo", "openrouter", "custom"]
    assert dialog._service_status["dev"].text() == "Not set up"
    code = ServiceDialog("dev", dialog)
    assert code.url.isHidden() and code.hear_model.isHidden()     # friends only paste a code
    code.key.setText("  dev-key-1  ")
    code.save()
    dialog.show_service_status("dev")
    assert dialog._service_status["dev"].text() == "Ready"
    openai = ServiceDialog("openai", dialog)
    assert openai.hear_model.placeholderText() == "whisper-1"     # the default shows, the field is empty
    openai.key.setText("sk-1")
    openai.translate_model.setText("gpt-5.4-nano, gpt-5.4-mini")
    openai.save()
    again = ServiceDialog("openai", dialog)
    assert again.key.text() == "" and "Saved" in again.key.placeholderText()
    again.save()                                                  # an empty key field keeps the key
    saved = json.loads(services.models_file().read_text(encoding="utf-8"))
    assert saved["dev"] == {"key": "dev-key-1"}
    assert saved["openai"] == {"key": "sk-1", "translate_model": "gpt-5.4-nano, gpt-5.4-mini"}
    assert services.translate_models("openai") == ["gpt-5.4-nano", "gpt-5.4-mini"]
    mimo = ServiceDialog("mimo", dialog)
    assert mimo.hear_model.isHidden() and not mimo.translate_model.isHidden()   # MiMo only translates


def test_status_tooltip_is_translated_line_by_line(window):
    from ui.backend import Status
    try:
        window.ui_lang_actions["vi"].trigger()
        window.show_status(Status("warn", "No game sound", "Start VRChat. The window finds it by itself.\n"
                                  "VRChat's sound is not captured: access denied"))
        assert window.status.text() == "Không có âm thanh game"
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
