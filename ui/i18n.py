"""The window's own language. Texts are written in English in the code; tr() looks them up."""
from __future__ import annotations

UI_LANGS = {"en": "English", "zh": "中文", "vi": "Tiếng Việt"}   # shown in their own language

_ZH = {
    'Microphone input': '麦克风输入',
    'Subtitle audio source': '字幕音频来源',
    'Unavailable': '不可用',
    'Click Fetch models to try again': '点击获取模型以重试',
    'Currently in use:': '当前使用：',
    'Custom domain': '自定义域名',
    'Fetch models': '获取模型',
    'Fetching models…': '正在获取模型…',
    'Found {count} models': '找到 {count} 个模型',
    'No models found': '未找到模型',
    'Pick a model…': '选择模型…',
    'Timed out after 30s. Click Fetch models to try again.': '30秒后超时，请点击获取模型重试。',
    'Try again': '重试',
    'Turns speech into text.': '将语音转换为文字。',
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
    "listening…": "聆听中…", "translating…": "翻译中…", "Click to copy the original text": "点击复制原文",
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
    "Turns speech into text. The Local Model runs on your graphics card (about 2.4 GB) and comes "
    "with the source version.":
        "把语音变成文字。本地模型在你的显卡上运行（约 2.4 GB），只有源代码版本才有。",
    "Turns text into the other language.": "把文字翻译成另一种语言。",
    "Dev key": "开发者密钥", "Local Model (this PC)": "本地模型（这台电脑）",
    "Google Gemini": "Google Gemini", "Qwen (Alibaba Cloud)": "通义千问（阿里云）",
    "Xiaomi MiMo": "小米 MiMo", "Custom (OpenAI-compatible)": "自定义（兼容 OpenAI）",
    "Ask the developer for a key. It is used to hear speech and to translate.":
        "请向开发者索取密钥。它用于语音识别和翻译。",
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
    "Background darkness": "背景深度",
    "100% is a solid panel. 0% leaves only the text over the game.":
        "100% 是不透明的面板。0% 只留下文字浮在游戏上。",
    "Always on top": "窗口置顶",
    "Keeps the window above the game. Needs VRChat in windowed or borderless mode.":
        "让窗口保持在游戏上方。VRChat 需要使用窗口或无边框模式。",
    "Hide the bars when the mouse is away": "鼠标离开时隐藏工具栏",
    "Only the chat log stays; move the mouse over the window to bring the buttons back.":
        "只保留聊天记录；把鼠标移到窗口上，按钮就会回来。",
}

_VI = {
    'Microphone input': 'Đầu vào micrô',
    'Subtitle audio source': 'Nguồn âm thanh phụ đề',
    'Unavailable': 'Không khả dụng',
    'Click Fetch models to try again': 'Nhấp Tải mô hình để thử lại',
    'Currently in use:': 'Đang dùng:',
    'Custom domain': 'Tên miền tùy chỉnh',
    'Fetch models': 'Tải mô hình',
    'Fetching models…': 'Đang tải mô hình…',
    'Found {count} models': 'Tìm thấy {count} mô hình',
    'No models found': 'Không tìm thấy mô hình',
    'Pick a model…': 'Chọn mô hình…',
    'Timed out after 30s. Click Fetch models to try again.': 'Hết thời gian sau 30 giây. Nhấp Tải mô hình để thử lại.',
    'Try again': 'Thử lại',
    'Turns speech into text.': 'Chuyển giọng nói thành văn bản.',
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
    "listening…": "đang nghe…", "translating…": "đang dịch…", "Click to copy the original text": "Bấm để chép câu gốc",
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
    "Turns speech into text. The Local Model runs on your graphics card (about 2.4 GB) and comes "
    "with the source version.":
        "Chuyển giọng nói thành chữ. Mô hình cục bộ chạy trên card đồ họa của bạn (khoảng 2,4 GB) "
        "và chỉ có trong bản mã nguồn.",
    "Turns text into the other language.": "Dịch chữ sang ngôn ngữ kia.",
    "Dev key": "Khóa Dev", "Local Model (this PC)": "Mô hình cục bộ (máy này)",
    "Google Gemini": "Google Gemini", "Qwen (Alibaba Cloud)": "Qwen (Alibaba Cloud)",
    "Xiaomi MiMo": "Xiaomi MiMo", "Custom (OpenAI-compatible)": "Tùy chỉnh (tương thích OpenAI)",
    "Ask the developer for a key. It is used to hear speech and to translate.":
        "Hãy xin khóa từ nhà phát triển. Khóa dùng để nghe giọng nói và để dịch.",
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
    "Background darkness": "Độ tối của nền",
    "100% is a solid panel. 0% leaves only the text over the game.":
        "100% là nền đặc. 0% chỉ còn chữ nổi trên game.",
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
