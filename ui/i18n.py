"""The window's own language. Texts are written in English in the code; tr() looks them up."""
from __future__ import annotations

UI_LANGS = {"en": "English", "zh": "中文", "vi": "Tiếng Việt"}   # shown in their own language

_ZH = {
    "Follow 'They speak'": "跟随“对方说”",
    "Custom languages": "自选语言",
    "Chatbox languages": "聊天框语言",
    "Send your voice and Auto typed messages in up to 3 languages. Auto-detect follows the last language heard, or English until then.": "将您的语音和自动模式下的输入消息发送为最多 3 种语言。自动检测跟随最近听到的语言，尚未听到时使用英语。",
    "Auto — follow chatbox languages": "自动 — 跟随聊天框语言",
    "Auto: follows chatbox languages (right now: {lang})": "自动：跟随聊天框语言（当前：{lang}）",
    "Chatbox messages now follow all languages in They speak. Choose custom languages in Settings → Translation.": "聊天框消息现在跟随“对方说”中选择的所有语言。可在设置 → 翻译中自选语言。",
    "Translated to controls the panel. Shared translations are reused for the chatbox.": "“翻译为”控制面板语言。聊天框会复用相同语言的翻译。",
    "Local translation now keeps separate sentences and retries runaway repetition.": "本地翻译现在会分别处理各个句子，并在出现大量重复时重试。",
    "Music setup now shows when the mixer is installed on another microphone and lets you select it.": "音乐设置现在会显示已安装混音器的其他麦克风，并允许您选择它。",
    "The mixer is installed on {microphone}. Use that microphone here and in VRChat. Moving it requires removing the existing attachment first.": "混音器已安装在 {microphone} 上。请在此处和 VRChat 中选择该麦克风。要更换安装位置，需先移除现有连接。",
    "Use {microphone}": "使用 {microphone}",
    "The installed mixer is no longer available. Refresh and try again.": "已安装的混音器不再可用。请刷新后重试。",
    "Translations appear as each language finishes, without waiting for the remaining languages.": "每种语言翻译完成后立即显示，无需等待其余语言。",
    "Speech recognition settings and VRChat chatbox timing are unchanged.": "语音识别设置和 VRChat 聊天框发送时序保持不变。",
    "Translated to": "翻译为",
    "Choose up to 3 languages you speak.": "最多选择 3 种您使用的语言。",
    "Choose up to 3 languages they speak, or Auto-detect.": "最多选择 3 种对方使用的语言，或选择自动检测。",
    "Choose up to 3 translation languages to show on the panel.": "最多选择 3 种在面板上显示的翻译语言。",
    "Choose up to 3 languages in I speak and They speak.": "在“我说”和“对方说”中分别最多选择 3 种语言。",
    "Translated to chooses up to 3 languages shown on the panel.": "“翻译为”可选择最多 3 种在面板上显示的语言。",
    "Connect": "连接",
    "Connected": "已连接",
    "Fetch models and save, then choose models under Hearing and Translating.": "获取模型并保存，然后在语音识别和翻译下选择模型。",
    "Name": "名称",
    "Add domain": "添加域名",
    "Remove domain": "移除域名",
    "Local model": "本地模型",
    "Use model": "使用模型",
    "Choose a hearing or translation model to download and run on this PC. No API key is needed.": "选择语音识别或翻译模型，下载后在本机运行。无需 API 密钥。",
    "Download: {size}. The model becomes active when the download finishes. You can close this window while it continues.": "下载大小：{size}。下载完成后会启用此模型。关闭此窗口后下载仍会继续。",
    "SenseVoice runs on CPU: Chinese, Cantonese, English, Japanese and Korean. Use Whisper for Vietnamese.": "SenseVoice 使用 CPU，支持普通话、粤语、英语、日语和韩语。越南语请使用 Whisper。",
    "NLLB-200 translates locally on CPU using CTranslate2 (INT8).": "NLLB-200 使用 CTranslate2（INT8）在本机 CPU 上翻译。",
    "Whisper runs on your NVIDIA graphics card. Large-v3 needs more memory than turbo.": "Whisper 使用 NVIDIA 显卡。Large-v3 比 turbo 需要更多显存。",
    "You can switch to your downloaded local hearing model.": "可以切换到已下载的本地语音识别模型。",
    "Choose a local hearing model to download and run on this PC.": "选择本地语音识别模型，下载后在本机运行。",
    "None": "无",
    "Second language": "第二种语言",
    "Optional second translation of your microphone. OSC shows the original and each translation on a separate line.": "可选的第二种麦克风翻译语言。OSC 将原文和每种译文分别显示在独立的一行。",
    "Include the original with typed translations. Microphone messages always include the original on its own line.": "在输入文字的翻译中附上原文。麦克风消息始终将原文单独显示一行。",
    "VRChat uses {microphone}. Select the same microphone in the translator to send music there.": "VRChat 正在使用 {microphone}。请在翻译器中选择同一个麦克风，才能将音乐发送到那里。",
    "Connection timed out after 30 seconds.": "连接超时，已等待 30 秒。",
    "Checking connection…": "正在检查连接…",
    "Online": "在线",
    "Connection issue": "连接异常",
    "Timed out. Click Fetch models to try again.": "请求超时。点击“获取模型”重试。",
    "Install microphone mixer…": "安装麦克风混音器…",
    "Microphone audio setup required": "需要配置麦克风音频",
    "Install the microphone mixer to play music through your selected microphone?": "安装麦克风混音器，以便通过所选麦克风播放音乐？",
    "Windows will ask for administrator permission. Setup uses the local mixer files and briefly restarts Windows audio.": "Windows 将请求管理员权限。安装程序使用本地混音器文件，并短暂重启 Windows 音频。",
    "Install": "安装",
    "Not now": "暂不安装",
    "Waiting for administrator approval and microphone setup…": "正在等待管理员授权并配置麦克风…",
    "Microphone setup failed.": "麦克风配置失败。",
    "Microphone mixer is already installed.": "麦克风混音器已安装。",
    "Microphone mixer installed. You can start music.": "麦克风混音器已安装。现在可以开始播放音乐。",
    "App audio capture currently requires Windows 11.": "应用音频捕获目前需要 Windows 11。",
    "No source audio detected. Play audio in the selected app.": "未检测到来源音频。请在所选应用中播放音频。",
    "Source audio": "来源音频",
    "Silent": "无声音",
    "Sending music to": "正在发送音乐到",
    "No source audio detected. Play audio in the selected app or file.": "未检测到来源音频。请在所选应用或文件中播放音频。",
    "Source audio detected, but music volume is zero.": "已检测到来源音频，但音乐音量为零。",
    "Testing in Discord: use Studio instead of Voice Isolation. If music is still missing, use Custom and turn off Bypass System Audio Input Processing, noise suppression and echo cancellation.": "在 Discord 中测试：选择 Studio（录音室），不要选择 Voice Isolation（人声隔离）。如果仍无音乐，请选择 Custom（自定义），关闭 Bypass System Audio Input Processing（绕过系统音频输入处理）、噪声抑制和回声消除。",
    "Ready to play music.": "可以开始播放音乐。",
    "WAV file": "WAV 文件",
    "Running app": "运行中的应用",
    "Music source": "音乐来源",
    "Choose WAV file…": "选择 WAV 文件…",
    "Audio file": "音频文件",
    "Refresh apps": "刷新应用",
    "Music reaches apps using this microphone. Browser capture includes all audio from that browser.": "使用此麦克风的应用都能收到音乐。浏览器捕获包含该浏览器的全部音频。",
    "Installed and validated": "已安装并验证",
    "Mixer not installed on this microphone": "此麦克风尚未安装混音器",
    "Choose a source, then start music. Your voice stays on the same microphone.": "选择来源，然后开始播放音乐。语音仍使用同一个麦克风。",
    "Microphone setup is required before live playback. The internal test does not install the mixer.": "实时播放前需要配置麦克风。内部测试不会安装混音器。",
    "Internal mixer test passed. This test did not play sound through your microphone.": "内部混音测试通过。本次测试未通过麦克风播放声音。",
    "Music will be mixed into your selected microphone. Keep that same microphone selected in VRChat.": "音乐将混入所选麦克风。请在 VRChat 中选择同一个麦克风。",
    "Not connected — in development": "尚未连接 — 开发中",
    "Music connection": "音乐连接",
    "Live music playback is not available yet. Microphone setup and app integration are still being built.": "暂不支持实时播放音乐。麦克风配置和应用集成功能仍在开发中。",
    "Planned sources: WAV files on Windows 10; WAV files and selected apps on Windows 11.": "计划支持：Windows 10 上的 WAV 文件；Windows 11 上的 WAV 文件及所选应用。",
    "The internal mixer test checks the prototype without playing sound or changing your microphone settings.": "内部混音测试用于检查原型，不会播放声音或更改麦克风设置。",
    "Mixer test output": "混音测试输出",
    "Run mixer test": "运行混音测试",
    "Live music playback is not available yet.": "暂不支持实时播放音乐。",
    "Ready for an internal test.": "可以运行内部测试。",
    "Internal tests are available in the development build only.": "内部测试仅在开发版本中提供。",
    "Running internal mixer test…": "正在运行内部混音测试…",
    "The internal test timed out. Your microphone settings were not changed.": "内部测试超时。麦克风设置未被更改。",
    "Internal test passed. Music is not connected to your microphone yet.": "内部测试通过。音乐尚未连接到麦克风。",
    "Internal test failed. See the details below.": "内部测试失败。请查看下方详情。",
    "Could not start the internal test. See the details below.": "无法启动内部测试。请查看下方详情。",
    "Audio driver detected.": "已检测到音频驱动程序。",
    "Audio driver is installed, but its audio device is unavailable. Restart the translator or Windows, then refresh.": "音频驱动程序已安装，但音频设备不可用。请重启翻译器或 Windows，然后刷新。",
    "Could not check the audio driver. Refresh and try again.": "无法检查音频驱动程序。请刷新后重试。",
    "Install audio driver…": "安装音频驱动程序…",
    "Audio driver required": "需要音频驱动程序",
    "The virtual microphone driver is missing. Download and install it? Windows may ask for administrator permission. Choosing No leaves music routing off.": "未安装虚拟麦克风驱动程序。是否下载并安装？Windows 可能要求管理员权限。选择否将保持音乐路由关闭。",
    "A signed audio driver installer is not available yet. Nothing was downloaded or installed.": "已签名的音频驱动安装程序尚未发布。未下载或安装任何内容。",
    "Downloading and verifying the audio driver…": "正在下载并验证音频驱动程序…",
    "Driver setup finished. Restart the translator to refresh audio devices.": "驱动程序安装已结束。请重启翻译器以刷新音频设备。",
    "Driver setup failed or was cancelled. You can try again.": "驱动程序安装失败或已取消。您可以重试。",
    "In VRChat, select VRChat Translator Microphone. Keep your physical microphone selected in this translator.": "在 VRChat 中选择 VRChat Translator Microphone。在翻译器中保留实体麦克风。",
    "Windows 10: open app audio settings and set only your music app's output to VRChat Translator Music. All apps sent to that device will be mixed. Keep your Windows default output on your speakers or headphones.": "Windows 10：打开应用音频设置，仅将音乐应用的输出设为 VRChat Translator Music。发送到此设备的所有应用音频都会混入。请将 Windows 默认输出保持为扬声器或耳机。",
    "Choose a running music app. Browser capture includes all audio from that browser. The VRChat Translator audio driver is required.": "选择正在运行的音乐应用。浏览器捕获包含该浏览器的全部音频。需要 VRChat Translator 音频驱动程序。",
    "Open app audio settings": "打开应用音频设置",
    "Install the VRChat Translator audio driver and select the music source first.": "请先安装 VRChat Translator 音频驱动程序并选择音乐来源。",
    "Open Windows Settings > System > Sound > App volume and device preferences.": "打开 Windows 设置 > 系统 > 声音 > 应用音量和设备首选项。",
    "Virtual microphone driver not installed": "未安装虚拟麦克风驱动程序",
    "Music to microphone": "将音乐发送到麦克风",
    "Music app": "音乐应用",
    "Send audio to": "音频发送到",
    "Include selected microphone": "混入所选麦克风",
    "Music volume": "音乐音量",
    "Stopped": "已停止",
    "Refresh apps and devices": "刷新应用和设备",
    "Start music": "开始播放音乐",
    "Stop music": "停止音乐",
    "Pick a running app…": "选择正在运行的应用…",
    "Starting music…": "正在启动音乐…",
    "Playing to": "正在发送到",
    "Microphone changed. Start music again to use it.": "麦克风已更改。请重新启动音乐以使用它。",
    "Microphone input": "麦克风输入",
    "Subtitle audio source": "字幕音频来源",
    "Unavailable": "不可用",
    # top bar and language row
    "Settings": "设置", "Minimise": "最小化", "Maximise": "最大化", "Close": "关闭",
    "Language of the window": "界面语言",
    "Swap the two languages": "交换两种语言", "Clear the chat log": "清空聊天记录",
    "How long the last translation took": "上一条翻译用时",
    "I speak": "我说", "They speak": "对方说",
    "My mic → chatbox": "我的麦克风 → 聊天框", "Other players → subtitles": "其他玩家 → 字幕",
    "Voice detector": "语音检测",
    "{what}: on (click to turn off)": "{what}：开（点击关闭）",
    "{what}: off (click to turn on)": "{what}：关（点击开启）",
    "Always on top: on": "窗口置顶：开", "Always on top: off": "窗口置顶：关",
    "Auto-detect": "自动检测", "English": "英语", "Chinese": "中文", "Vietnamese": "越南语",
    "Cantonese": "粤语",
    "【Speaking {lang}】": "【正在说{lang}】",
    "Korean": "韩语", "Japanese": "日语", "Spanish": "西班牙语", "French": "法语", "German": "德语",
    "Russian": "俄语", "Thai": "泰语", "Indonesian": "印尼语", "Portuguese": "葡萄牙语",
    "Italian": "意大利语", "Arabic": "阿拉伯语", "Hindi": "印地语",
    # text box
    "Type a message — Enter translates and sends it": "输入消息 — 按 Enter 翻译并发送",
    "Message to translate and send": "要翻译并发送的消息",
    "Send": "发送", "Auto": "自动",
    "Auto — the language heard last": "自动 — 最近听到的语言",
    "Auto: translates into the language heard last from audio (right now: {lang})":
        "自动：翻译成最近从语音中听到的语言（当前：{lang}）",
    "Translates into {lang}": "翻译成{lang}",
    "Pick the language your typed text is translated into": "选择输入文字要翻译成的语言",
    # chat log
    "You": "你", "Speaker {n}": "说话人 {n}", "Speaker": "说话人", "typed": "输入",
    "not sent": "未发送", "copied": "已复制",
    "listening…": "聆听中…", "translating…": "翻译中…", "Click to copy the original text. Drag to select and copy only that text.": "点击复制原文，拖动选择并仅复制选中的文字。",
    "not translated": "未翻译", "cut to 144 characters": "已截短到 144 个字符",
    "VRChat is not running": "VRChat 未运行", "OSC is off in VRChat": "VRChat 的 OSC 已关闭",
    "could not send": "发送失败",
    "demo: nothing was sent": "演示：没有发送任何内容",
    "demo: no engine yet, nothing was translated or sent": "演示：还没有引擎，没有翻译也没有发送",
    # status
    "Starting…": "启动中…", "Connected": "已连接", "VRChat not found": "未找到 VRChat",
    "OSC is off": "OSC 已关闭", "Demo": "演示",
    "Start VRChat. The window finds it by itself.": "请启动 VRChat，窗口会自动找到它。",
    "VRChat is running but does not listen for chatbox messages. In VRChat: Action Menu → "
    "Options → OSC → Enabled.":
        "VRChat 正在运行，但没有接收聊天框消息。在 VRChat 中：Action Menu → Options → OSC → Enabled。",
    "VRChat is running and takes chatbox messages. Typed text is translated and sent.":
        "VRChat 正在运行并接收聊天框消息。输入的文字会被翻译并发送。",
    "VRChat's sound is being captured. Turning speech into text is not connected yet.":
        "正在采集 VRChat 的声音。语音转文字尚未接入。",
    "VRChat's sound is being captured and turned into text.": "正在采集 VRChat 的声音并转成文字。",
    "Speech engine": "语音引擎",
    "Update downloaded, it starts the next time you open the program": "新版本已下载，下次打开程序时生效",
    "VRChat's sound is not captured": "没有采集到 VRChat 的声音",
    "Your microphone is not captured": "没有采集到你的麦克风",
    "No game sound": "没有游戏声音",
    # Settings → Models
    "Models": "模型", "Hearing": "语音识别", "Translating": "翻译", "Services": "服务",
    "Turns speech into text, through an online service or with the Local Model on your own "
    "graphics card.":
        "把语音变成文字：通过在线服务，或用你自己显卡上的本地模型。",
    "Turns text into the other language.": "把文字翻译成另一种语言。",
    "Currently in use:": "当前使用：",
    "Turns speech into text.": "将语音转换为文字。",
    "Local Whisper": "本地 Whisper",
    "Switch Model": "切换模型",
    "The {category} model for {service} is unavailable.": "{service} 的{category}模型不可用。",
    "Would you like to switch to {model}?": "是否要切换到 {model}？",
    "Switch to {model}": "切换到 {model}",
    "Would you like to switch to an already set up model?": "是否要切换到已设置的模型？",
    "No other set up model was found.": "未找到其他已设置的模型。",
    "We recommend switching to the Local Model (Whisper on your graphics card).": "建议切换到本地模型（显卡上的 Whisper）。",
    "We recommend downloading the Local Model (Whisper on your graphics card) for free, private speech recognition.": "建议下载本地模型（显卡上的 Whisper），无需联网且完全免费。",
    "Switch to Local Model": "切换到本地模型",
    "Download Local Model": "下载本地模型",
    "No other set up translating model was found.": "未找到其他已设置的翻译模型。",
    "Please set up a translation service in Settings → Models.": "请在 设置 → 模型 中配置翻译服务。",
    "Open Settings": "打开设置",
    "Or switch to Local Model": "或切换到本地模型",
    "Local Model (this PC)": "本地模型（这台电脑）",
    "Whisper on your own NVIDIA graphics card: no key and no limits. Downloaded once.":
        "在你自己的 NVIDIA 显卡上运行 Whisper：不需要密钥，也没有限额。只需下载一次。",
    "The download is {size}; the model then uses about 2.4 GB of the graphics card's memory. When "
    "everything has arrived, hearing switches to the Local Model. You can close this window: the "
    "download carries on.":
        "下载大小为 {size}；之后模型会占用显卡约 2.4 GB 的显存。全部下载完成后，语音识别会切换到本地模型。"
        "你可以关闭这个窗口，下载会继续进行。",
    "Not downloaded": "未下载", "Download": "下载", "Stop": "停止", "{done} of {size}": "{done} / {size}",
    "Google Gemini": "Google Gemini", "Qwen (Alibaba Cloud)": "通义千问（阿里云）",
    "Xiaomi MiMo": "小米 MiMo", "Custom (OpenAI-compatible)": "自定义（兼容 OpenAI）",
    "Custom domain": "自定义域名", "Custom domain (OpenAI-compatible)": "自定义域名（兼容 OpenAI）",
    "API address": "API 地址", "API key": "API 密钥",
    "Address of your OpenAI-compatible API or proxy.": "兼容 OpenAI 的 API 地址或代理地址。",
    "Your API key. Leave empty if none is needed.": "你的 API 密钥。如果不需要可留空。",
    "Fetch models": "获取模型", "Fetching models…": "正在获取模型…", "Pick a model…": "选择模型…",
    "Try again": "重试", "Timed out after 30s. Click Fetch models to try again.": "30秒后超时，请点击获取模型重试。",
    "Click Fetch models to try again": "点击获取模型以重试",
    "Found {count} models": "找到 {count} 个模型", "No models found": "未找到模型",
    "Fetch available models from your API to pick from.": "从你的 API 获取可用模型列表以供选择。",
    "Model that turns speech into text (e.g. whisper-1).": "把语音转成文字的模型（例如 whisper-1）。",
    "Model that translates text (e.g. gpt-4o-mini).": "翻译文字的模型（例如 gpt-4o-mini）。",
    "Whisper hears, GPT translates. Paid per use.": "Whisper 识别语音，GPT 翻译。按用量付费。",
    "Hears and translates. Google gives a small free daily allowance.":
        "可以语音识别和翻译。Google 每天提供少量免费额度。",
    "Qwen3-ASR knows Cantonese; its open version heard best in the benchmark. Paid per use.":
        "Qwen3-ASR 能识别粤语；它的开源版本在测试中识别得最准。按用量付费。",
    "Translates only. Paid per use, at low prices.": "只能翻译。按用量付费，价格很低。",
    "One key for many models, Qwen and MiMo among them. Paid per use.":
        "一个密钥就能用很多模型，包括千问和 MiMo。按用量付费。",
    "Any OpenAI-compatible address, such as a server on your own PC.":
        "任何兼容 OpenAI 的地址，比如你自己电脑上的服务器。",
    "Any OpenAI-compatible address or custom domain, such as a proxy or server on your own PC.":
        "任何兼容 OpenAI 的 API 地址或自定义域名，比如你自己电脑上的代理或服务器。",
    "Set up…": "设置…", "Ready": "可以使用", "Not set up": "未设置",
    "Saved. Leave empty to keep it.": "已保存。留空则保持不变。",
    "Paste the key here": "在这里粘贴密钥",
    "e.g. whisper-1": "例如 whisper-1", "e.g. gpt-5.4-mini": "例如 gpt-5.4-mini",
    "Address": "地址", "Key": "密钥",
    "Hearing model": "语音识别模型", "Translating models": "翻译模型",
    "Empty fields use the defaults shown. Several translating models can be listed with commas: "
    "when one is at its limit, the next answers.":
        "留空的栏位会使用显示的默认值。可以用逗号列出多个翻译模型：一个用完额度时，由下一个接替。",
    "Get a key": "获取密钥", "Test": "测试", "Testing…": "正在测试…",
    "Cancel": "取消", "Save": "保存", "Could not save": "无法保存",
    "Sound": "声音", "Microphone": "麦克风", "Windows default": "Windows 默认",
    "Detector strictness: other players": "语音检测严格度：其他玩家",
    "Higher ignores music and noise better but can miss quiet voices. 70% is the tested default.":
        "数值越高越能忽略音乐和噪音，但可能漏掉小声的话。70% 是测试过的默认值。",
    "Detector strictness: my microphone": "语音检测严格度：我的麦克风",
    "Higher ignores keyboard clicks and room noise better but can miss your quiet words. 50% is the default.":
        "数值越高越能忽略键盘声和房间噪音，但可能漏掉你小声说的话。默认值是 50%。",
    "The microphone the translator listens to. Pick the same one as in VRChat.":
        "翻译器聆听的麦克风。请选择和 VRChat 里相同的那个。",
    "The translator engine is not connected yet. These lines are examples.":
        "翻译引擎尚未接入，这些只是示例。",
    # settings
    "Translation": "翻译", "Chatbox": "聊天框", "Appearance": "外观",
    "Your language. Subtitles are translated into it.": "你的语言。字幕会翻译成这种语言。",
    "Your microphone is translated into this language. Auto-detect uses the language heard last. "
    "Typed text uses the Send menu.":
        "你的麦克风语音会翻译成这种语言。自动检测使用最近听到的语言。输入文字的翻译语言在发送菜单中选择。",
    "Only listens while someone talks. Turn it off if it cuts words or misses quiet voices.":
        "只在有人说话时聆听。如果它截断词语或漏掉小声的话，请关闭。",
    "Show the original text": "显示原文",
    "Shows what was heard above its translation.": "在译文上方显示听到的原文。",
    "Show “typing” while I talk": "我说话时显示“正在输入”",
    "After 30 seconds without a message, other players see the typing dots until your next one "
    "arrives. Messages right after it switch without dots.":
        "超过 30 秒没有发消息时，其他玩家会看到输入中的圆点，直到你的下一条消息出现。紧接着的消息会直接替换，不再显示圆点。",
    "Add my own words": "附上我的原话",
    "The chatbox shows the translation, then what you said.": "聊天框先显示译文，再显示你说的原话。",
    "Add Speaker words": "附上对方的话",
    "Send other players' translation and original words to your VRChat chatbox.":
        "将其他玩家话语的译文和原文发送到你的 VRChat 聊天框。",
    "Message text size": "消息文字大小", "Size of the text in the chat log.": "聊天记录中文字的大小。",
    "What's new in {version}": "{version} 更新内容",
    "Drag over subtitle text to copy just the selection. A normal click still copies the original text.": "拖动选择字幕文字可仅复制选中部分，单击仍会复制原文。",
    "Background darkness now fades smoothly across 30%. Below 30%, blank space still lets clicks through.": "背景深度在 30% 附近平滑变化，低于 30% 时空白区域仍可点击穿透。",
    "Below 30% background darkness, empty overlay space lets clicks through. Text and the typing box stay clickable.": "背景深度低于 30% 时可点击穿透空白区域，文字和输入框仍可点击。",
    "Drag the bottom-right corner grip to resize the window. Drag the top controls to move it.": "拖动右下角的手柄调整窗口大小，拖动顶部控件移动窗口。",
    "Domain setup and model downloads now open inside Settings and move with it.": "域名设置和模型下载现在在设置窗口内打开，并随窗口一起移动。",
    "This update notice appears once per version.": "每个版本只显示一次更新提示。",
    "Resize window": "调整窗口大小",
    "Drag to resize the window": "拖动以调整窗口大小",
    "Move to VRChat's top-left corner": "移到 VRChat 左上角",
    "VRChat window not found. Open or restore VRChat first.": "未找到 VRChat 窗口，请先打开或还原 VRChat。",
    "Could not move the translator window.": "无法移动翻译器窗口。",
    "Use the button beside VRChat to move the translator to the game's top-left corner.": "使用 VRChat 旁的按钮将翻译器移到游戏左上角。",
    "Background darkness": "背景深度",
    "Below 30%, empty space lets clicks through. Text and top controls stay clickable.":
        "低于 30% 时可点击穿透空白区域，文字和顶部控件仍可点击。",
    "Always on top": "窗口置顶",
    "Keeps the window above the game. Needs VRChat in windowed or borderless mode.":
        "让窗口保持在游戏上方。VRChat 需要使用窗口或无边框模式。",
    "Hide the bars when the mouse is away": "鼠标离开时隐藏工具栏",
    "Only the chat log stays; move the mouse over the window to bring the buttons back.":
        "只保留聊天记录；把鼠标移到窗口上，按钮就会回来。",
}

_VI = {
    "Follow 'They speak'": "Theo ‘Họ nói’",
    "Custom languages": "Ngôn ngữ tùy chọn",
    "Chatbox languages": "Ngôn ngữ khung chat",
    "Send your voice and Auto typed messages in up to 3 languages. Auto-detect follows the last language heard, or English until then.": "Gửi giọng nói và tin nhắn nhập ở chế độ Tự động bằng tối đa 3 ngôn ngữ. Tự động nhận diện dùng ngôn ngữ nghe gần nhất, hoặc tiếng Anh nếu chưa nghe được.",
    "Auto — follow chatbox languages": "Tự động — theo ngôn ngữ khung chat",
    "Auto: follows chatbox languages (right now: {lang})": "Tự động: theo ngôn ngữ khung chat (hiện tại: {lang})",
    "Chatbox messages now follow all languages in They speak. Choose custom languages in Settings → Translation.": "Tin nhắn khung chat giờ theo tất cả ngôn ngữ trong Họ nói. Chọn ngôn ngữ riêng tại Cài đặt → Dịch.",
    "Translated to controls the panel. Shared translations are reused for the chatbox.": "Dịch sang điều khiển ngôn ngữ trên bảng. Khung chat dùng lại các bản dịch chung.",
    "Local translation now keeps separate sentences and retries runaway repetition.": "Dịch cục bộ giờ xử lý từng câu riêng và thử lại khi kết quả lặp quá nhiều.",
    "Music setup now shows when the mixer is installed on another microphone and lets you select it.": "Cài đặt nhạc sẽ hiển thị micro khác đã cài bộ trộn và cho phép bạn chọn micro đó.",
    "The mixer is installed on {microphone}. Use that microphone here and in VRChat. Moving it requires removing the existing attachment first.": "Bộ trộn đã được cài trên {microphone}. Hãy chọn micro đó ở đây và trong VRChat. Muốn chuyển sang micro khác, cần gỡ kết nối hiện tại trước.",
    "Use {microphone}": "Dùng {microphone}",
    "The installed mixer is no longer available. Refresh and try again.": "Bộ trộn đã cài không còn khả dụng. Hãy làm mới và thử lại.",
    "Translations appear as each language finishes, without waiting for the remaining languages.": "Bản dịch xuất hiện ngay khi từng ngôn ngữ hoàn tất, không cần chờ các ngôn ngữ còn lại.",
    "Speech recognition settings and VRChat chatbox timing are unchanged.": "Cài đặt nhận dạng giọng nói và thời điểm gửi vào khung chat VRChat không thay đổi.",
    "Translated to": "Dịch sang",
    "Choose up to 3 languages you speak.": "Chọn tối đa 3 ngôn ngữ bạn nói.",
    "Choose up to 3 languages they speak, or Auto-detect.": "Chọn tối đa 3 ngôn ngữ họ nói, hoặc Tự nhận diện.",
    "Choose up to 3 translation languages to show on the panel.": "Chọn tối đa 3 ngôn ngữ dịch để hiển thị trên bảng.",
    "Choose up to 3 languages in I speak and They speak.": "Chọn tối đa 3 ngôn ngữ cho mỗi mục Tôi nói và Họ nói.",
    "Translated to chooses up to 3 languages shown on the panel.": "Dịch sang chọn tối đa 3 ngôn ngữ hiển thị trên bảng.",
    "Connect": "Kết nối",
    "Connected": "Đã kết nối",
    "Fetch models and save, then choose models under Hearing and Translating.": "Lấy danh sách mô hình và lưu, rồi chọn mô hình bên dưới Nhận dạng và Dịch.",
    "Name": "Tên",
    "Add domain": "Thêm tên miền",
    "Remove domain": "Xóa tên miền",
    "Local model": "Mô hình cục bộ",
    "Use model": "Dùng mô hình",
    "Choose a hearing or translation model to download and run on this PC. No API key is needed.": "Chọn mô hình nhận dạng giọng nói hoặc dịch để tải về và chạy trên máy này. Không cần khóa API.",
    "Download: {size}. The model becomes active when the download finishes. You can close this window while it continues.": "Dung lượng tải: {size}. Mô hình sẽ được dùng khi tải xong. Bạn có thể đóng cửa sổ này trong khi vẫn tiếp tục tải.",
    "SenseVoice runs on CPU: Chinese, Cantonese, English, Japanese and Korean. Use Whisper for Vietnamese.": "SenseVoice chạy trên CPU: tiếng Trung, Quảng Đông, Anh, Nhật và Hàn. Hãy dùng Whisper cho tiếng Việt.",
    "NLLB-200 translates locally on CPU using CTranslate2 (INT8).": "NLLB-200 dịch trên CPU của máy bằng CTranslate2 (INT8).",
    "Whisper runs on your NVIDIA graphics card. Large-v3 needs more memory than turbo.": "Whisper chạy trên card NVIDIA. Large-v3 cần nhiều bộ nhớ hơn turbo.",
    "You can switch to your downloaded local hearing model.": "Bạn có thể chuyển sang mô hình nhận dạng giọng nói cục bộ đã tải.",
    "Choose a local hearing model to download and run on this PC.": "Chọn mô hình nhận dạng giọng nói cục bộ để tải về và chạy trên máy này.",
    "None": "Không",
    "Second language": "Ngôn ngữ thứ hai",
    "Optional second translation of your microphone. OSC shows the original and each translation on a separate line.": "Ngôn ngữ dịch thứ hai cho micrô (tùy chọn). OSC hiển thị bản gốc và mỗi bản dịch trên một dòng riêng.",
    "Include the original with typed translations. Microphone messages always include the original on its own line.": "Kèm bản gốc khi dịch văn bản nhập. Tin nhắn từ micrô luôn có bản gốc trên một dòng riêng.",
    "VRChat uses {microphone}. Select the same microphone in the translator to send music there.": "VRChat đang dùng {microphone}. Chọn cùng micrô trong trình dịch để gửi nhạc đến đó.",
    "Connection timed out after 30 seconds.": "Kết nối hết thời gian chờ sau 30 giây.",
    "Checking connection…": "Đang kết nối…",
    "Online": "Trực tuyến",
    "Connection issue": "Lỗi kết nối",
    "Timed out. Click Fetch models to try again.": "Yêu cầu hết thời gian chờ. Nhấn Lấy danh sách model để thử lại.",
    "Install microphone mixer…": "Cài bộ trộn micrô…",
    "Microphone audio setup required": "Cần thiết lập âm thanh micrô",
    "Install the microphone mixer to play music through your selected microphone?": "Cài bộ trộn micrô để phát nhạc qua micrô đã chọn?",
    "Windows will ask for administrator permission. Setup uses the local mixer files and briefly restarts Windows audio.": "Windows sẽ yêu cầu quyền quản trị. Trình cài đặt dùng các tệp bộ trộn có sẵn và khởi động lại âm thanh Windows trong giây lát.",
    "Install": "Cài đặt",
    "Not now": "Để sau",
    "Waiting for administrator approval and microphone setup…": "Đang chờ quyền quản trị và thiết lập micrô…",
    "Microphone setup failed.": "Thiết lập micrô thất bại.",
    "Microphone mixer is already installed.": "Bộ trộn micrô đã được cài đặt.",
    "Microphone mixer installed. You can start music.": "Đã cài bộ trộn micrô. Bạn có thể bắt đầu phát nhạc.",
    "App audio capture currently requires Windows 11.": "Thu âm thanh ứng dụng hiện yêu cầu Windows 11.",
    "No source audio detected. Play audio in the selected app.": "Không phát hiện âm thanh nguồn. Hãy phát âm thanh trong ứng dụng đã chọn.",
    "Source audio": "Âm thanh nguồn",
    "Silent": "Không có âm thanh",
    "Sending music to": "Đang gửi nhạc đến",
    "No source audio detected. Play audio in the selected app or file.": "Không phát hiện âm thanh nguồn. Hãy phát âm thanh trong ứng dụng hoặc tệp đã chọn.",
    "Source audio detected, but music volume is zero.": "Đã phát hiện âm thanh nguồn, nhưng âm lượng nhạc đang bằng không.",
    "Testing in Discord: use Studio instead of Voice Isolation. If music is still missing, use Custom and turn off Bypass System Audio Input Processing, noise suppression and echo cancellation.": "Thử trong Discord: chọn Studio thay vì Voice Isolation. Nếu vẫn không có nhạc, chọn Custom rồi tắt Bypass System Audio Input Processing, khử tiếng ồn và khử tiếng vọng.",
    "Ready to play music.": "Sẵn sàng phát nhạc.",
    "WAV file": "Tệp WAV",
    "Running app": "Ứng dụng đang chạy",
    "Music source": "Nguồn nhạc",
    "Choose WAV file…": "Chọn tệp WAV…",
    "Audio file": "Tệp âm thanh",
    "Refresh apps": "Làm mới ứng dụng",
    "Music reaches apps using this microphone. Browser capture includes all audio from that browser.": "Nhạc được gửi đến các ứng dụng dùng micrô này. Thu âm trình duyệt bao gồm mọi âm thanh của trình duyệt đó.",
    "Installed and validated": "Đã cài đặt và xác thực",
    "Mixer not installed on this microphone": "Bộ trộn chưa được cài cho micrô này",
    "Choose a source, then start music. Your voice stays on the same microphone.": "Chọn nguồn rồi bắt đầu phát nhạc. Giọng nói vẫn dùng cùng micrô.",
    "Microphone setup is required before live playback. The internal test does not install the mixer.": "Cần thiết lập micrô trước khi phát trực tiếp. Kiểm tra nội bộ không cài đặt bộ trộn.",
    "Internal mixer test passed. This test did not play sound through your microphone.": "Kiểm tra bộ trộn nội bộ thành công. Bài kiểm tra này không phát âm thanh qua micrô.",
    "Music will be mixed into your selected microphone. Keep that same microphone selected in VRChat.": "Nhạc sẽ được trộn vào micrô đã chọn. Hãy chọn cùng micrô đó trong VRChat.",
    "Not connected — in development": "Chưa kết nối — đang phát triển",
    "Music connection": "Kết nối nhạc",
    "Live music playback is not available yet. Microphone setup and app integration are still being built.": "Chưa thể phát nhạc trực tiếp. Phần thiết lập micrô và tích hợp ứng dụng vẫn đang được xây dựng.",
    "Planned sources: WAV files on Windows 10; WAV files and selected apps on Windows 11.": "Nguồn dự kiến: tệp WAV trên Windows 10; tệp WAV và ứng dụng đã chọn trên Windows 11.",
    "The internal mixer test checks the prototype without playing sound or changing your microphone settings.": "Bài kiểm tra bộ trộn nội bộ kiểm tra bản thử nghiệm mà không phát âm thanh hay thay đổi cài đặt micrô.",
    "Mixer test output": "Kết quả kiểm tra bộ trộn",
    "Run mixer test": "Kiểm tra bộ trộn",
    "Live music playback is not available yet.": "Chưa thể phát nhạc trực tiếp.",
    "Ready for an internal test.": "Sẵn sàng kiểm tra nội bộ.",
    "Internal tests are available in the development build only.": "Kiểm tra nội bộ chỉ có trong bản phát triển.",
    "Running internal mixer test…": "Đang kiểm tra bộ trộn nội bộ…",
    "The internal test timed out. Your microphone settings were not changed.": "Kiểm tra nội bộ đã hết thời gian. Cài đặt micrô không bị thay đổi.",
    "Internal test passed. Music is not connected to your microphone yet.": "Kiểm tra nội bộ thành công. Nhạc vẫn chưa được kết nối với micrô.",
    "Internal test failed. See the details below.": "Kiểm tra nội bộ thất bại. Xem chi tiết bên dưới.",
    "Could not start the internal test. See the details below.": "Không thể bắt đầu kiểm tra nội bộ. Xem chi tiết bên dưới.",
    "Audio driver detected.": "Đã phát hiện trình điều khiển âm thanh.",
    "Audio driver is installed, but its audio device is unavailable. Restart the translator or Windows, then refresh.": "Đã cài trình điều khiển nhưng thiết bị âm thanh chưa khả dụng. Khởi động lại trình dịch hoặc Windows, rồi làm mới.",
    "Could not check the audio driver. Refresh and try again.": "Không thể kiểm tra trình điều khiển âm thanh. Hãy làm mới và thử lại.",
    "Install audio driver…": "Cài trình điều khiển âm thanh…",
    "Audio driver required": "Cần trình điều khiển âm thanh",
    "The virtual microphone driver is missing. Download and install it? Windows may ask for administrator permission. Choosing No leaves music routing off.": "Chưa có trình điều khiển micrô ảo. Bạn có muốn tải xuống và cài đặt không? Windows có thể yêu cầu quyền quản trị viên. Chọn Không sẽ giữ chức năng truyền nhạc tắt.",
    "A signed audio driver installer is not available yet. Nothing was downloaded or installed.": "Chưa có bộ cài trình điều khiển âm thanh đã ký số. Chưa tải xuống hay cài đặt gì.",
    "Downloading and verifying the audio driver…": "Đang tải xuống và xác minh trình điều khiển âm thanh…",
    "Driver setup finished. Restart the translator to refresh audio devices.": "Đã hoàn tất cài đặt trình điều khiển. Khởi động lại trình dịch để cập nhật thiết bị âm thanh.",
    "Driver setup failed or was cancelled. You can try again.": "Cài đặt trình điều khiển thất bại hoặc đã bị hủy. Bạn có thể thử lại.",
    "In VRChat, select VRChat Translator Microphone. Keep your physical microphone selected in this translator.": "Trong VRChat, chọn VRChat Translator Microphone. Giữ micrô vật lý được chọn trong trình dịch.",
    "Windows 10: open app audio settings and set only your music app's output to VRChat Translator Music. All apps sent to that device will be mixed. Keep your Windows default output on your speakers or headphones.": "Windows 10: mở cài đặt âm thanh ứng dụng và chỉ đặt đầu ra của ứng dụng nhạc thành VRChat Translator Music. Âm thanh của mọi ứng dụng gửi đến thiết bị này sẽ được trộn. Giữ đầu ra mặc định của Windows là loa hoặc tai nghe.",
    "Choose a running music app. Browser capture includes all audio from that browser. The VRChat Translator audio driver is required.": "Chọn ứng dụng nhạc đang chạy. Thu từ trình duyệt bao gồm mọi âm thanh của trình duyệt đó. Cần trình điều khiển âm thanh VRChat Translator.",
    "Open app audio settings": "Mở cài đặt âm thanh ứng dụng",
    "Install the VRChat Translator audio driver and select the music source first.": "Hãy cài trình điều khiển âm thanh VRChat Translator và chọn nguồn nhạc trước.",
    "Open Windows Settings > System > Sound > App volume and device preferences.": "Mở Cài đặt Windows > Hệ thống > Âm thanh > Tùy chọn thiết bị và âm lượng ứng dụng.",
    "Virtual microphone driver not installed": "Chưa cài trình điều khiển micrô ảo",
    "Music to microphone": "Phát nhạc qua micrô",
    "Music app": "Ứng dụng phát nhạc",
    "Send audio to": "Gửi âm thanh đến",
    "Include selected microphone": "Trộn micrô đã chọn",
    "Music volume": "Âm lượng nhạc",
    "Stopped": "Đã dừng",
    "Refresh apps and devices": "Làm mới ứng dụng và thiết bị",
    "Start music": "Bắt đầu phát nhạc",
    "Stop music": "Dừng nhạc",
    "Pick a running app…": "Chọn ứng dụng đang chạy…",
    "Starting music…": "Đang bắt đầu phát nhạc…",
    "Playing to": "Đang phát đến",
    "Microphone changed. Start music again to use it.": "Micrô đã thay đổi. Bắt đầu phát nhạc lại để dùng micrô mới.",
    "Microphone input": "Đầu vào micrô",
    "Subtitle audio source": "Nguồn âm thanh phụ đề",
    "Unavailable": "Không khả dụng",
    # top bar and language row
    "Settings": "Cài đặt", "Minimise": "Thu nhỏ", "Maximise": "Phóng to", "Close": "Đóng",
    "Language of the window": "Ngôn ngữ giao diện",
    "Swap the two languages": "Đổi chỗ hai ngôn ngữ", "Clear the chat log": "Xóa nhật ký trò chuyện",
    "How long the last translation took": "Thời gian dịch câu gần nhất",
    "I speak": "Tôi nói", "They speak": "Họ nói",
    "My mic → chatbox": "Mic của tôi → chatbox", "Other players → subtitles": "Người chơi khác → phụ đề",
    "Voice detector": "Nhận biết giọng nói",
    "{what}: on (click to turn off)": "{what}: bật (bấm để tắt)",
    "{what}: off (click to turn on)": "{what}: tắt (bấm để bật)",
    "Always on top: on": "Luôn ở trên cùng: bật", "Always on top: off": "Luôn ở trên cùng: tắt",
    "Auto-detect": "Tự nhận biết", "English": "Tiếng Anh", "Chinese": "Tiếng Trung",
    "Vietnamese": "Tiếng Việt", "Cantonese": "Tiếng Quảng Đông",
    "【Speaking {lang}】": "【Đang nói {lang}】",
    "Korean": "tiếng Hàn", "Japanese": "tiếng Nhật", "Spanish": "tiếng Tây Ban Nha",
    "French": "tiếng Pháp", "German": "tiếng Đức", "Russian": "tiếng Nga", "Thai": "tiếng Thái",
    "Indonesian": "tiếng Indonesia", "Portuguese": "tiếng Bồ Đào Nha", "Italian": "tiếng Ý",
    "Arabic": "tiếng Ả Rập", "Hindi": "tiếng Hindi",
    # text box
    "Type a message — Enter translates and sends it": "Nhập tin nhắn — Enter để dịch và gửi",
    "Message to translate and send": "Tin nhắn cần dịch và gửi",
    "Send": "Gửi", "Auto": "Tự động",
    "Auto — the language heard last": "Tự động — ngôn ngữ nghe được gần nhất",
    "Auto: translates into the language heard last from audio (right now: {lang})":
        "Tự động: dịch sang ngôn ngữ nghe được gần nhất từ âm thanh (hiện tại: {lang})",
    "Translates into {lang}": "Dịch sang {lang}",
    "Pick the language your typed text is translated into": "Chọn ngôn ngữ để dịch chữ bạn nhập",
    # chat log
    "You": "Bạn", "Speaker {n}": "Người nói {n}", "Speaker": "Người nói", "typed": "nhập",
    "not sent": "chưa gửi", "copied": "đã chép",
    "listening…": "đang nghe…", "translating…": "đang dịch…", "Click to copy the original text. Drag to select and copy only that text.": "Bấm để chép câu gốc. Kéo để chọn và chỉ chép phần chữ đã chọn.",
    "not translated": "chưa dịch", "cut to 144 characters": "đã cắt còn 144 ký tự",
    "VRChat is not running": "VRChat chưa chạy", "OSC is off in VRChat": "OSC trong VRChat đang tắt",
    "could not send": "không gửi được",
    "demo: nothing was sent": "bản thử: không gửi gì cả",
    "demo: no engine yet, nothing was translated or sent": "bản thử: chưa có bộ dịch, không dịch và không gửi gì",
    # status
    "Starting…": "Đang khởi động…", "Connected": "Đã kết nối", "VRChat not found": "Không thấy VRChat",
    "OSC is off": "OSC đang tắt", "Demo": "Bản thử",
    "Start VRChat. The window finds it by itself.": "Hãy mở VRChat. Cửa sổ sẽ tự tìm thấy nó.",
    "VRChat is running but does not listen for chatbox messages. In VRChat: Action Menu → "
    "Options → OSC → Enabled.":
        "VRChat đang chạy nhưng không nhận tin nhắn chatbox. Trong VRChat: Action Menu → Options → "
        "OSC → Enabled.",
    "VRChat is running and takes chatbox messages. Typed text is translated and sent.":
        "VRChat đang chạy và nhận tin nhắn chatbox. Chữ bạn nhập được dịch rồi gửi.",
    "VRChat's sound is being captured. Turning speech into text is not connected yet.":
        "Đang thu âm thanh của VRChat. Phần chuyển giọng nói thành chữ chưa được nối.",
    "VRChat's sound is being captured and turned into text.":
        "Đang thu âm thanh của VRChat và chuyển thành chữ.",
    "Speech engine": "Bộ nhận giọng nói",
    "Update downloaded, it starts the next time you open the program":
        "Đã tải bản cập nhật, bản mới sẽ chạy vào lần mở chương trình tiếp theo",
    "VRChat's sound is not captured": "Không thu được âm thanh của VRChat",
    "Your microphone is not captured": "Không thu được micro của bạn",
    "No game sound": "Không có âm thanh game",
    # Settings → Models
    "Models": "Mô hình", "Hearing": "Nghe giọng nói", "Translating": "Dịch", "Services": "Dịch vụ",
    "Turns speech into text, through an online service or with the Local Model on your own "
    "graphics card.":
        "Chuyển giọng nói thành chữ, qua một dịch vụ trực tuyến hoặc bằng Mô hình cục bộ trên card "
        "đồ họa của bạn.",
    "Turns text into the other language.": "Dịch chữ sang ngôn ngữ kia.",
    "Currently in use:": "Đang dùng:",
    "Turns speech into text.": "Chuyển giọng nói thành văn bản.",
    "Local Whisper": "Whisper cục bộ",
    "Switch Model": "Chuyển mô hình",
    "The {category} model for {service} is unavailable.": "Mô hình {category} của {service} hiện không khả dụng.",
    "Would you like to switch to {model}?": "Bạn có muốn chuyển sang {model} không?",
    "Switch to {model}": "Chuyển sang {model}",
    "Would you like to switch to an already set up model?": "Bạn có muốn chuyển sang một mô hình đã thiết lập không?",
    "No other set up model was found.": "Không tìm thấy mô hình nào khác đã thiết lập.",
    "We recommend switching to the Local Model (Whisper on your graphics card).": "Khuyến nghị chuyển sang Mô hình cục bộ (Whisper trên card đồ họa).",
    "We recommend downloading the Local Model (Whisper on your graphics card) for free, private speech recognition.": "Khuyến nghị tải về Mô hình cục bộ (Whisper trên card đồ họa) để nhận dạng giọng nói miễn phí và riêng tư.",
    "Switch to Local Model": "Chuyển sang Mô hình cục bộ",
    "Download Local Model": "Tải Mô hình cục bộ",
    "No other set up translating model was found.": "Không tìm thấy mô hình dịch nào khác đã thiết lập.",
    "Please set up a translation service in Settings → Models.": "Vui lòng thiết lập dịch vụ dịch trong Cài đặt → Mô hình.",
    "Open Settings": "Mở Cài đặt",
    "Or switch to Local Model": "Hoặc chuyển sang Mô hình cục bộ",
    "Local Model (this PC)": "Mô hình cục bộ (máy này)",
    "Whisper on your own NVIDIA graphics card: no key and no limits. Downloaded once.":
        "Whisper chạy trên card đồ họa NVIDIA của chính bạn: không cần khóa, không giới hạn. Chỉ tải "
        "về một lần.",
    "The download is {size}; the model then uses about 2.4 GB of the graphics card's memory. When "
    "everything has arrived, hearing switches to the Local Model. You can close this window: the "
    "download carries on.":
        "Dung lượng tải về là {size}; sau đó mô hình dùng khoảng 2,4 GB bộ nhớ của card đồ họa. Khi tải "
        "xong, phần nghe sẽ chuyển sang Mô hình cục bộ. Bạn có thể đóng cửa sổ này: việc tải vẫn tiếp tục.",
    "Not downloaded": "Chưa tải về", "Download": "Tải về", "Stop": "Dừng",
    "{done} of {size}": "{done} trên {size}",
    "Google Gemini": "Google Gemini", "Qwen (Alibaba Cloud)": "Qwen (Alibaba Cloud)",
    "Xiaomi MiMo": "Xiaomi MiMo", "Custom (OpenAI-compatible)": "Tùy chỉnh (tương thích OpenAI)",
    "Custom domain": "Tên miền tùy chỉnh", "Custom domain (OpenAI-compatible)": "Tên miền tùy chỉnh (tương thích OpenAI)",
    "API address": "Địa chỉ API", "API key": "Khóa API",
    "Address of your OpenAI-compatible API or proxy.": "Địa chỉ API tương thích OpenAI hoặc proxy của bạn.",
    "Your API key. Leave empty if none is needed.": "Khóa API của bạn. Để trống nếu không cần.",
    "Fetch models": "Tải mô hình", "Fetching models…": "Đang tải mô hình…", "Pick a model…": "Chọn mô hình…",
    "Try again": "Thử lại", "Timed out after 30s. Click Fetch models to try again.": "Hết thời gian sau 30 giây. Nhấp Tải mô hình để thử lại.",
    "Click Fetch models to try again": "Nhấp Tải mô hình để thử lại",
    "Found {count} models": "Tìm thấy {count} mô hình", "No models found": "Không tìm thấy mô hình",
    "Fetch available models from your API to pick from.": "Tải danh sách mô hình từ API để chọn.",
    "Model that turns speech into text (e.g. whisper-1).": "Mô hình chuyển giọng nói thành chữ (ví dụ whisper-1).",
    "Model that translates text (e.g. gpt-4o-mini).": "Mô hình dịch chữ (ví dụ gpt-4o-mini).",
    "Whisper hears, GPT translates. Paid per use.": "Whisper nghe, GPT dịch. Trả tiền theo lượng dùng.",
    "Hears and translates. Google gives a small free daily allowance.":
        "Nghe và dịch. Google cho một ít lượt miễn phí mỗi ngày.",
    "Qwen3-ASR knows Cantonese; its open version heard best in the benchmark. Paid per use.":
        "Qwen3-ASR nghe được tiếng Quảng Đông; bản mở của nó nghe chuẩn nhất trong bài kiểm tra. "
        "Trả tiền theo lượng dùng.",
    "Translates only. Paid per use, at low prices.": "Chỉ dịch. Trả tiền theo lượng dùng, giá rẻ.",
    "One key for many models, Qwen and MiMo among them. Paid per use.":
        "Một khóa dùng được nhiều mô hình, có cả Qwen và MiMo. Trả tiền theo lượng dùng.",
    "Any OpenAI-compatible address, such as a server on your own PC.":
        "Bất kỳ địa chỉ nào tương thích OpenAI, ví dụ máy chủ trên chính máy bạn.",
    "Any OpenAI-compatible address or custom domain, such as a proxy or server on your own PC.":
        "Bất kỳ địa chỉ API tương thích OpenAI hoặc tên miền tùy chỉnh nào, ví dụ máy chủ trên máy bạn.",
    "Set up…": "Thiết lập…", "Ready": "Sẵn sàng", "Not set up": "Chưa thiết lập",
    "Saved. Leave empty to keep it.": "Đã lưu. Để trống thì giữ nguyên.",
    "Paste the key here": "Dán khóa vào đây",
    "e.g. whisper-1": "ví dụ whisper-1", "e.g. gpt-5.4-mini": "ví dụ gpt-5.4-mini",
    "Address": "Địa chỉ", "Key": "Khóa",
    "Hearing model": "Mô hình nghe", "Translating models": "Mô hình dịch",
    "Empty fields use the defaults shown. Several translating models can be listed with commas: "
    "when one is at its limit, the next answers.":
        "Ô để trống sẽ dùng giá trị mặc định đang hiện. Có thể ghi nhiều mô hình dịch, cách nhau bằng "
        "dấu phẩy: khi một mô hình hết lượt, mô hình tiếp theo sẽ trả lời.",
    "Get a key": "Lấy khóa", "Test": "Kiểm tra", "Testing…": "Đang kiểm tra…",
    "Cancel": "Hủy", "Save": "Lưu", "Could not save": "Không lưu được",
    "Sound": "Âm thanh", "Microphone": "Micro", "Windows default": "Mặc định của Windows",
    "Detector strictness: other players": "Độ chặt nhận biết giọng nói: người chơi khác",
    "Higher ignores music and noise better but can miss quiet voices. 70% is the tested default.":
        "Càng cao càng bỏ qua nhạc và tiếng ồn tốt hơn, nhưng có thể bỏ sót giọng nhỏ. 70% là mức mặc "
        "định đã thử nghiệm.",
    "Detector strictness: my microphone": "Độ chặt nhận biết giọng nói: micro của tôi",
    "Higher ignores keyboard clicks and room noise better but can miss your quiet words. 50% is the default.":
        "Càng cao càng bỏ qua tiếng bàn phím và tiếng ồn trong phòng tốt hơn, nhưng có thể bỏ sót lời "
        "bạn nói nhỏ. Mặc định là 50%.",
    "The microphone the translator listens to. Pick the same one as in VRChat.":
        "Micro mà bộ dịch lắng nghe. Hãy chọn cùng micro với VRChat.",
    "The translator engine is not connected yet. These lines are examples.":
        "Bộ dịch chưa được nối. Các dòng này chỉ là ví dụ.",
    # settings
    "Translation": "Dịch", "Chatbox": "Chatbox", "Appearance": "Giao diện",
    "Your language. Subtitles are translated into it.": "Ngôn ngữ của bạn. Phụ đề được dịch sang ngôn ngữ này.",
    "Your microphone is translated into this language. Auto-detect uses the language heard last. "
    "Typed text uses the Send menu.":
        "Giọng nói qua micro của bạn được dịch sang ngôn ngữ này. Tự nhận biết dùng ngôn ngữ nghe "
        "được gần nhất. Chữ bạn nhập dùng ngôn ngữ chọn trong menu Gửi.",
    "Only listens while someone talks. Turn it off if it cuts words or misses quiet voices.":
        "Chỉ nghe khi có người nói. Hãy tắt nếu nó cắt mất chữ hoặc bỏ sót giọng nhỏ.",
    "Show the original text": "Hiện câu gốc",
    "Shows what was heard above its translation.": "Hiện câu nghe được ở phía trên bản dịch.",
    "Show “typing” while I talk": "Hiện “đang nhập” khi tôi nói",
    "After 30 seconds without a message, other players see the typing dots until your next one "
    "arrives. Messages right after it switch without dots.":
        "Sau 30 giây không có tin nhắn, người chơi khác thấy dấu chấm đang nhập cho đến khi tin nhắn tiếp "
        "theo của bạn hiện ra. Các tin nhắn ngay sau đó đổi luôn, không có dấu chấm.",
    "Add my own words": "Kèm lời gốc của tôi",
    "The chatbox shows the translation, then what you said.": "Chatbox hiện bản dịch, rồi đến lời bạn nói.",
    "Add Speaker words": "Kèm lời người nói",
    "Send other players' translation and original words to your VRChat chatbox.":
        "Gửi bản dịch và lời gốc của người chơi khác vào chatbox VRChat của bạn.",
    "Message text size": "Cỡ chữ tin nhắn", "Size of the text in the chat log.": "Cỡ chữ trong nhật ký trò chuyện.",
    "What's new in {version}": "Có gì mới trong {version}",
    "Drag over subtitle text to copy just the selection. A normal click still copies the original text.": "Kéo chọn chữ trong phụ đề để chỉ chép phần đã chọn. Bấm bình thường vẫn chép câu gốc.",
    "Background darkness now fades smoothly across 30%. Below 30%, blank space still lets clicks through.": "Độ tối nền giờ thay đổi mượt qua mức 30%. Dưới 30%, vùng trống vẫn cho phép nhấp xuyên.",
    "Below 30% background darkness, empty overlay space lets clicks through. Text and the typing box stay clickable.": "Khi độ tối nền dưới 30%, có thể nhấp xuyên vùng trống. Chữ và ô nhập vẫn bấm được.",
    "Drag the bottom-right corner grip to resize the window. Drag the top controls to move it.": "Kéo tay nắm ở góc dưới bên phải để đổi kích thước cửa sổ. Kéo các nút phía trên để di chuyển.",
    "Domain setup and model downloads now open inside Settings and move with it.": "Thiết lập tên miền và tải mô hình mở bên trong Cài đặt và di chuyển cùng cửa sổ.",
    "This update notice appears once per version.": "Thông báo cập nhật này chỉ xuất hiện một lần mỗi phiên bản.",
    "Resize window": "Đổi kích thước cửa sổ",
    "Drag to resize the window": "Kéo để đổi kích thước cửa sổ",
    "Move to VRChat's top-left corner": "Chuyển đến góc trên trái VRChat",
    "VRChat window not found. Open or restore VRChat first.": "Không tìm thấy cửa sổ VRChat. Hãy mở hoặc khôi phục VRChat trước.",
    "Could not move the translator window.": "Không thể di chuyển cửa sổ dịch.",
    "Use the button beside VRChat to move the translator to the game's top-left corner.": "Dùng nút cạnh VRChat để chuyển cửa sổ dịch đến góc trên trái của game.",
    "Background darkness": "Độ tối của nền",
    "Below 30%, empty space lets clicks through. Text and top controls stay clickable.":
        "Dưới 30%, có thể nhấp xuyên vùng trống. Chữ và nút phía trên vẫn bấm được.",
    "Always on top": "Luôn ở trên cùng",
    "Keeps the window above the game. Needs VRChat in windowed or borderless mode.":
        "Giữ cửa sổ nằm trên game. VRChat cần chạy ở chế độ cửa sổ hoặc không viền.",
    "Hide the bars when the mouse is away": "Ẩn các thanh khi chuột rời đi",
    "Only the chat log stays; move the mouse over the window to bring the buttons back.":
        "Chỉ còn nhật ký trò chuyện; đưa chuột vào cửa sổ để các nút hiện lại.",
}

TABLES = {"zh": _ZH, "vi": _VI}
_lang = "en"


def lang() -> str:
    return _lang


def set_lang(code: str) -> None:
    global _lang
    _lang = code if code in UI_LANGS else "en"


def tr(text: str) -> str:
    return TABLES.get(_lang, {}).get(text, text)


def tr_lines(text: str) -> str:
    """A status tooltip: one sentence per line; a line may end in ": <reason>" kept as it is."""
    lines = []
    for line in text.split("\n"):
        head, colon, rest = line.partition(": ")
        lines.append(tr(head) + colon + rest if colon and tr(head) != head else tr(line))
    return "\n".join(lines)


def tr_note(note: str) -> str:
    """A line's note is built from parts like "not translated: <reason>, cut to 144 characters"."""
    parts = []
    for part in note.split(", "):
        head, colon, rest = part.partition(": ")
        parts.append(tr(head) + colon + rest if colon and tr(head) != head else tr(part))
    return ", ".join(parts)
