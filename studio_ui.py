"""Simplified Chinese interface for the locally deployed speech studio."""
from pathlib import Path

import gradio as gr
from reference_asr import (IDLE_STATUS, LANGUAGES, result_is_current,
                           transcribe_reference, validate_reference_sources)
from voice_library import VoiceLibrary, VoiceLibraryError, describe_voice

# Gradio 6.5.1 exposes its shared locale store from the bundled i18n module.
# Resolve the hashed filename from this installation instead of editing the package.
_i18n_assets = list((Path(gr.__file__).parent / "templates/frontend/assets").glob("i18n-*.js"))
_locale_import = (f"import {{ d as setLocale }} from './assets/{_i18n_assets[0].name}';\n"
                  "setLocale('zh-CN');") if len(_i18n_assets) == 1 else ""
LOCALE_HEAD = '<script type="module">' + _locale_import + r"""
// A few Gradio 6 controls still use literal English accessibility labels.
const words = {
  'Upload file': '上传音频', 'Record audio': '录制音频',
  'Reset to default value': '恢复默认值', 'Empty value': '生成后在这里试听',
  'Download': '下载音频', 'Download audio': '下载音频', 'Play': '播放',
  'Pause': '暂停', 'Clear': '清除音频', 'Remove': '移除音频',
  'Loading...': '正在加载…', 'Error': '发生错误', 'Playback speed': '播放速度',
  'Show transcript': '显示转写', 'Hide transcript': '隐藏转写',
  'Volume': '音量', 'Mute': '静音', 'Unmute': '取消静音',
  'Adjust volume': '调整音量', 'High volume': '高音量', 'Low volume': '低音量',
  'Reset audio': '恢复原始音频', 'Trim audio to selection': '裁剪到选中片段', 'undo': '撤销',
  'Trim': '裁剪', 'Stop': '停止', 'Submit': '提交', 'Cancel': '取消'
};
function translate(root) {
  if (!(root instanceof Element) || root.closest('textarea,input,script,style')) return;
  for (const el of [root, ...root.querySelectorAll('[aria-label],[title],[alt]')]) {
    for (const attr of ['aria-label', 'title', 'alt']) {
      const val = el.getAttribute(attr);
      const cn = words[val] || (val?.startsWith('Adjust playback speed to ') ? val.replace('Adjust playback speed to ', '调整播放速度为 ') :
        val?.startsWith('Skip backwards by ') ? '向后跳转一小段' :
        val?.startsWith('Skip forward by ') ? '向前跳转一小段' :
        val?.startsWith('number input for ') ? val.replace('number input for ', '数值：') :
        val?.startsWith('range slider for ') ? val.replace('range slider for ', '滑动调整：') : null);
      if (cn && cn !== val) el.setAttribute(attr, cn);
    }
  }
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (!node.parentElement?.closest('textarea,input,script,style')) {
      const key = node.textContent.trim();
      const translated = words[key] || (/^Uploading \d+ files?\.\.\.$/.test(key) ? '正在上传音频…' :
        /^queue:/.test(key) ? key.replace('queue:', '排队进度：').replace(/([\d.]+)s\b/g, '$1 秒') : null);
      if (translated) node.textContent = node.textContent.replace(key, translated);
    }
  }
}
translate(document.body);
new MutationObserver(records => {
  for (const r of records) {
    if (r.type === 'attributes') translate(r.target);
    else if (r.type === 'characterData') translate(r.target.parentElement);
    else for (const n of r.addedNodes) translate(n.nodeType === 1 ? n : n.parentElement);
  }
}).observe(document.body, {subtree:true, childList:true, characterData:true,
  attributes:true, attributeFilter:['aria-label','title','alt']});
document.addEventListener('play', event => {
 if (event.target instanceof HTMLAudioElement) {
   document.querySelectorAll('audio').forEach(audio => { if(audio !== event.target) audio.pause(); });
 }
}, true);
</script>
"""

EXAMPLES = {
    "双人对话": (2, "[S1]你好，欢迎来到我们的语音工作室。\n[S2]你好，今天我们来测试中文对话生成。"),
    "单人朗读": (1, "[S1]你好，欢迎来到我们的语音工作室。今天我们来测试中文语音生成。"),
    "播客开场": (2, "[S1]欢迎收听今天的播客，我是主持人小林。今天我们来聊聊人工智能如何帮助我们的日常工作。\n[S2]大家好，我是小陈。我们就从一个简单的例子开始吧。"),
}

CSS = """
.gradio-container {max-width:1240px!important;margin:auto;padding:24px 32px!important;
 font-family:'PingFang SC','Microsoft YaHei',system-ui,sans-serif!important;
 --body-text-color:#253b35;--body-text-color-subdued:#62756d;--block-info-text-color:#62756d;
 --background-fill-primary:#f7f9f8;--background-fill-secondary:#f1f5f3;
 --block-background-fill:#fff;--block-border-color:#e1e8e4;
 --border-color-primary:#dce5df;--input-border-color:#dce5df;
 --color-accent:#19674f;--slider-color:#19674f;--button-primary-background-fill:#19674f;
 --button-primary-text-color:white;}
.gradio-container .main {padding:0!important;max-width:none!important;}
.gradio-container .html-container {padding:0!important;}
.gradio-container input[type=radio]:checked {background-color:#19674f!important;border-color:#19674f!important;}
#brand {display:flex;align-items:center;justify-content:space-between;padding:4px 0 20px;border-bottom:1px solid #dce5df;}
#brand h1 {font-size:22px;font-weight:650;letter-spacing:-.5px;margin:0;color:#193e31;}
#brand p {font-size:13px;color:#62756d;margin:5px 0 0;}
.brand-note {font-size:12px;color:#62756d;border:1px solid #dce5df;padding:6px 12px;border-radius:99px;}
.tab-nav {border-bottom:1px solid #dce5df!important;gap:24px!important;margin-bottom:20px!important;}
.tab-nav button {font-size:15px!important;padding:14px 4px!important;border-radius:0!important;}
.tab-nav button.selected {color:#19674f!important;border-bottom:3px solid #19674f!important;background:transparent!important;}
#studio-layout {gap:22px;align-items:flex-start;}
#script-column {min-width:0;gap:18px;}
.surface {padding:22px!important;border:1px solid #e1e8e4!important;border-radius:14px!important;background:white!important;gap:14px!important;}
.surface h2 {font-size:18px;margin:0 0 4px!important;font-weight:650;}
.surface h3 {font-size:15px;margin:0!important;}
#dialogue textarea {font-size:16px;line-height:1.95;padding:16px;min-height:230px;}
#script-meta {font-size:12px;color:#62756d;}
#studio-output {position:sticky;top:20px;min-width:0;}
#run-btn {min-height:48px;background:#19674f!important;border:0;color:white!important;border-radius:10px;font-size:16px;font-weight:600;}
#run-btn:hover {background:#12533f!important;}
#output-status textarea {font-size:13px;line-height:1.8;border:0!important;background:#f5f8f6!important;}
.role-card {border-top:1px solid #e6ece8;padding:14px 0 2px!important;background:white!important;gap:10px!important;}
.role-card:first-child {border-top:0;}
.role-title {font-size:13px;color:#19674f;font-weight:650;}
.voice-preview {background:#f5f8f6;border-radius:10px;padding:10px 12px;font-size:12px;color:#62756d;}
.voice-preview audio {display:block;width:100%;height:36px;margin-top:6px;}
.voice-grid {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;}
.voice-card {border:1px solid #dce5df;border-radius:12px;padding:18px;background:white;min-width:0;}
.voice-card h3 {font-size:15px;margin:0 0 8px;color:#193e31;}
.voice-card p {font-size:12px;color:#62756d;line-height:1.7;margin:8px 0;}
.voice-card audio {display:block;width:100%;height:36px;margin:12px 0;}
.voice-card button {width:100%;border:1px solid #cbded3;border-radius:8px;background:#edf5f0;color:#195c44;padding:8px 10px;margin-top:12px;font-size:13px;cursor:pointer;}
.voice-card button:hover {background:#dfeee5;}
.gradio-container input[type=radio] {accent-color:#19674f!important;}
.voice-source {font-size:11px;color:#62756d;}
#library-intro h2 {font-size:22px;margin:0 0 6px;}
#library-intro p,#library-status {color:#62756d;font-size:13px;}
.empty-voice {padding:10px 12px;color:#62756d;background:#f5f8f6;border-radius:8px;font-size:12px;}
#studio-footer {padding:20px 0 4px;text-align:center;color:#73837b;font-size:12px;}
#studio-footer a {color:#526e60;}
.gradio-container button:focus-visible,.gradio-container input:focus-visible,.gradio-container textarea:focus-visible {outline:2px solid #19674f!important;outline-offset:3px;}
@media(max-width:800px){.gradio-container{padding:16px!important;}#brand{align-items:flex-start;}#brand h1{font-size:18px;}.brand-note{display:none;}
 #studio-layout{flex-direction:column;}#studio-output,#script-column{width:100%;position:static;flex-basis:auto!important;}
 .surface{padding:16px!important;}.voice-grid{grid-template-columns:repeat(2,minmax(0,1fr));}}
@media(max-width:520px){.voice-grid{grid-template-columns:1fr;}#dialogue textarea{min-height:190px;}}
.dark .gradio-container {--body-text-color:#253b35;--body-text-color-subdued:#62756d;
 --background-fill-primary:#f7f9f8;--background-fill-secondary:#f1f5f3;--block-label-text-color:#253b35;
 --input-background-fill:white;--input-text-color:#253b35;--block-title-text-color:#253b35;}
"""


def select_example(name):
    count, text = EXAMPLES[name]
    # Clear all five voices, including hidden panels, so a preset cannot reuse
    # an unrelated reference recording from an earlier dialogue.
    return (count, text, *([None] * 5), *([""] * 5),
            *[gr.update(visible=i < count) for i in range(5)],
            *([None] * 5), *([IDLE_STATUS] * 5), *([""] * 5))


def prepare_transcription(audio_path):
    return "", ("音频已收到，正在排队识别原文，请稍候…" if audio_path else IDLE_STATUS), audio_path


def apply_transcription(audio_path, current_text, result):
    # Upload B / clearing / switching examples must not receive upload A's text.
    # Also preserve manual corrections entered while the worker was running.
    if not result_is_current(audio_path, result):
        return gr.skip(), gr.skip(), gr.skip()
    if (current_text or "").strip():
        return gr.skip(), "已保留你手动填写的原文。", audio_path
    return result["text"], result["status"], audio_path


def voice_library_summary() -> str:
    try:
        voices = VoiceLibrary().list_voices()
    except VoiceLibraryError as exc:
        return f"音色库暂时不可用：{exc}"
    builtins = sum(bool(voice.get("builtin")) for voice in voices)
    personal = len(voices) - builtins
    return f"音色库现有 **{len(voices)}** 个音色：内置 {builtins} 个，我的音色 {personal} 个。"


def current_voice_choices():
    try:
        return VoiceLibrary().choices()
    except VoiceLibraryError:
        return [("音色库暂时不可用", "")]


def select_library_voice(voice_id):
    try:
        voice = VoiceLibrary().get(voice_id)
        if voice is None:
            return None, "", None, IDLE_STATUS, "自动识别"
        language = voice.get("language", "自动识别")
        if language not in LANGUAGES:
            language = "自动识别"
        return (audio_value(voice["audio_path"]), voice["prompt_text"], voice["audio_path"],
                describe_voice(voice), language)
    except VoiceLibraryError as exc:
        return None, "", None, f"选择音色失败：{exc}", "自动识别"


def save_library_voice(audio_path, prompt_text, name, language, rights_confirmed):
    try:
        voice = VoiceLibrary().save_user_voice(
            audio_path, prompt_text, name, language, rights_confirmed=rights_confirmed
        )
        choices = VoiceLibrary().choices()
        status = f"已保存“{voice['name']}”。以后可直接从音色库选择，不需要重新上传或识别。"
        return (status, gr.update(choices=choices, value=voice["id"]), voice_library_summary(),
                audio_value(voice["audio_path"]), voice["prompt_text"], voice["audio_path"], "")
    except VoiceLibraryError as exc:
        return (f"保存失败：{exc}", gr.update(), voice_library_summary(),
                gr.skip(), gr.skip(), gr.skip(), gr.skip())
    except Exception:
        import logging
        logging.exception("Saving reference voice failed")
        return ("保存失败：服务器无法写入音色库，请管理员检查日志。", gr.update(),
                voice_library_summary(), gr.skip(), gr.skip(), gr.skip(), gr.skip())


def refresh_voice_library():
    try:
        choices = VoiceLibrary().choices()
        return (*[gr.update(choices=choices) for _ in range(5)], voice_library_summary())
    except VoiceLibraryError as exc:
        return (*[gr.update() for _ in range(5)], f"刷新失败：{exc}")



def voice_audio_html(voice):
    from html import escape
    from urllib.parse import quote
    path = Path(voice["audio_path"]).as_posix()
    url = "/gradio_api/file=" + quote(path, safe="/:")
    return ('<audio controls preload="metadata" aria-label="试听：' + escape(voice["name"], quote=True) +
            '" src="' + escape(url, quote=True) + '"></audio>')


def preview_voice(voice_id):
    from html import escape
    try:
        voice = VoiceLibrary().get(voice_id)
        if voice:
            return ('<div class="voice-preview">音色原声试听 · ' +
                    escape(voice["name"]) + voice_audio_html(voice) + '</div>')
    except VoiceLibraryError:
        pass
    return '<div class="empty-voice">自动分配声音；选择音色后可在这里试听。</div>'


def library_gallery(query="", category="全部"):
    from html import escape
    try:
        voices = VoiceLibrary().list_voices()
    except VoiceLibraryError as exc:
        return '<p>' + escape(str(exc)) + '</p>'
    cards = []
    for v in voices:
        if category == "我的音色" and v.get("builtin"):
            continue
        if category == "内置音色" and not v.get("builtin"):
            continue
        if query.strip().casefold() not in (v["name"] + " " + v.get("source", "")).casefold():
            continue
        cards.append('<article class="voice-card"><h3>' + escape(v["name"]) + '</h3><p>' +
            ('内置音色' if v.get("builtin") else '我的音色') + ' · ' +
            str(round(v.get("duration_seconds", 0), 1)) + ' 秒参考片段</p>' +
            voice_audio_html(v) + '<p>' + escape(v["prompt_text"]) + '</p><div class="voice-source">' +
            escape(v.get("source", "")) + ' · ' + escape(v.get("license", "")) + '</div>' +
            '<button type="button" data-voice="' + escape(v["id"], quote=True) + '" aria-label="使用音色：' +
            escape(v["name"], quote=True) + '">使用这个音色</button></article>')
    return '<div class="voice-grid">' + ''.join(cards) + '</div>' if cards else '<p class="empty-voice">没有找到音色。可以换个关键词，或在创作台上传并保存自己的声音。</p>'


def script_summary(text, requested=0):
    from speech_guard import estimate_seconds, generation_budget, normalized
    seconds = estimate_seconds(text)
    limit = (generation_budget(text, requested) - 16) / 12.5
    return f"{len(normalized(text))} 字符 · 预计成品约 {max(1, round(seconds * .8))}–{round(seconds * 1.2)} 秒 · 生成保护上限约 {limit:.0f} 秒"


def audio_value(path):
    # Returning decoded audio lets Gradio create the canonical cache URL, rather
    # than reusing a FileData URL relative to /gradio_api/run/predict/.
    import soundfile as sf
    samples, rate = sf.read(path, dtype="float32")
    return rate, samples


def build_studio(args, generate, update_panels, max_tokens):
    with gr.Blocks(title="云途觉晓多人云音创作平台") as demo:
        gr.HTML('<header id="brand"><div><h1>云途觉晓多人云音创作平台</h1><p>让每个角色，都有自己的声音。</p></div><span class="brand-note">多人配音 · 本地创作</span></header>')
        with gr.Tabs() as workspace_tabs:
            with gr.Tab("创作台", id="create"):
                with gr.Row(equal_height=False, elem_id="studio-layout"):
                    with gr.Column(scale=7, min_width=360, elem_id="script-column"):
                        with gr.Column(elem_classes="surface"):
                            gr.Markdown("## 01  对话台词")
                            with gr.Row():
                                example_buttons = [gr.Button(name, size="sm", min_width=0) for name in EXAMPLES]
                            speaker_count = gr.Radio([(f"{n} 人", n) for n in range(1, 6)], value=2, label="角色人数")
                            dialogue = gr.Textbox(value=EXAMPLES["双人对话"][1], label="台词",
                                lines=7, placeholder="[S1]你好！\n[S2]很高兴见到你。",
                                info="用 [S1]、[S2] 标记角色。加载示例会重置已选音色。", elem_id="dialogue")
                            script_meta = gr.Markdown(script_summary(EXAMPLES["双人对话"][1]), elem_id="script-meta")
                        with gr.Column(elem_classes="surface"):
                            gr.Markdown("## 02  角色与声音\n先选声音，点击播放器试听；也可以使用自己的录音。")
                            refs, prompts, panels, sources, asr_statuses, languages, retries = [], [], [], [], [], [], []
                            voice_selects, voice_names, save_buttons, previews, rights = [], [], [], [], []
                            for idx in range(1, 6):
                                with gr.Column(visible=idx <= 2, elem_classes="role-card") as panel:
                                    gr.HTML(f'<div class="role-title">角色 {idx} · [S{idx}]</div>')
                                    voice_selects.append(gr.Dropdown(current_voice_choices(), value="",
                                        label=f"角色 {idx} 的音色", filterable=True))
                                    previews.append(gr.HTML(preview_voice(""), elem_id=f"voice-preview-{idx}"))
                                    with gr.Accordion("使用自己的录音 / 编辑参考原文", open=False):
                                        refs.append(gr.Audio(label=f"角色 {idx} 的参考录音", type="filepath",
                                            sources=["upload"], buttons=["download"], elem_id=f"reference-{idx}"))
                                        asr_statuses.append(gr.Markdown(IDLE_STATUS))
                                        prompts.append(gr.Textbox(label=f"角色 {idx} 的参考原文", lines=2,
                                            placeholder="上传录音后自动识别；选择内置音色时已自动填写。"))
                                        with gr.Row():
                                            languages.append(gr.Dropdown(list(LANGUAGES), value="自动识别", label="录音语言"))
                                            retries.append(gr.Button("重新识别原文", size="sm"))
                                        voice_names.append(gr.Textbox(label="保存音色名称", placeholder="例如：我的播客主持人"))
                                        rights.append(gr.Checkbox(label="我拥有此录音的声音使用授权"))
                                        save_buttons.append(gr.Button("保存到我的音色", size="sm"))
                                    sources.append(gr.State(None))
                                panels.append(panel)
                            refresh_library = gr.Button("刷新音色列表", size="sm")
                    with gr.Column(scale=4, min_width=300, elem_id="studio-output", elem_classes="surface"):
                        gr.Markdown("## 03  生成作品")
                        length = gr.Radio([("自动", 0), ("15 秒", 204), ("30 秒", 392), ("60 秒", 767)],
                            value=0, label="最长时长", info="自动按台词估算；时长为上限，不会强行拉长。")
                        run = gr.Button("生成语音", variant="primary", elem_id="run-btn")
                        status = gr.Textbox(label="生成状态", value="准备就绪。写好台词、选好声音，即可开始。",
                            lines=4, interactive=False, elem_id="output-status")
                        output = gr.Audio(label="作品试听", type="numpy", interactive=False,
                            buttons=["download"], elem_id="output-audio")
                        gr.Markdown("成品会自动核对台词，并清理多余尾音。\n\n点击播放器的下载按钮，保存 WAV 后可用于 ComfyUI。")
                        with gr.Accordion("高级设置", open=False):
                            normalize = gr.Checkbox(value=True, label="自动整理台词格式")
                            resample = gr.Checkbox(value=False, label="统一参考录音采样率")
                            temperature = gr.Slider(.1, 2.0, value=1.1, step=.05, label="声音变化程度",
                                info="影响随机性，不能指定情绪。")
                            top_p = gr.Slider(.1, 1., value=.9, step=.01, label="候选概率范围")
                            top_k = gr.Slider(1, 200, value=50, step=1, label="候选数量")
                            repetition = gr.Slider(.8, 2., value=1.1, step=.05, label="重复抑制")
            with gr.Tab("音色库 · 先听再选", id="library"):
                gr.HTML('<div id="library-intro"><h2>找到适合角色的声音</h2><p>点击播放试听原声片段，再点击“使用这个音色”带回创作台。</p></div>')
                library_status = gr.Markdown(voice_library_summary(), elem_id="library-status")
                with gr.Row():
                    search = gr.Textbox(label="搜索音色", placeholder="试试：女声、北方、长者…", scale=2)
                    category = gr.Radio(["全部", "内置音色", "我的音色"], value="全部", label="音色来源")
                target_role = gr.Radio([(f"角色 {n}", n) for n in range(1, 6)], value=1,
                    label="将音色用于", info="如果选中未启用的角色，会自动增加角色人数。")
                gallery = gr.HTML(library_gallery(), js_on_load="""
                    element.addEventListener('click', event => {
                        const button = event.target.closest('button[data-voice]');
                        if (button) trigger('click', {voice_id: button.dataset.voice});
                    });
                """)
                library_refresh = gr.Button("刷新音色库", size="sm")
        gr.HTML('<footer id="studio-footer">基于 <a href="https://github.com/OpenMOSS/MOSS-TTSD" target="_blank" rel="noopener">OpenMOSS / MOSS-TTSD</a> · 内置参考音色来自 AISHELL-3（Apache-2.0）</footer>')

        speaker_count.input(fn=update_panels, inputs=[speaker_count], outputs=panels, queue=False)

        def apply_gallery_voice(role, count, evt: gr.EventData):
            role = max(1, min(5, int(role)))
            voice_id = evt._data.get("voice_id", "")
            voice = VoiceLibrary().get(voice_id)
            if not voice:
                raise gr.Error("音色不存在，请刷新音色库。")
            chosen = select_library_voice(voice_id)
            new_count = max(int(count), role)
            # Each group of outputs is indexed by role; preserve every other role.
            values = []
            for value in (voice_id, *chosen):
                values.extend(value if i == role - 1 else gr.skip() for i in range(5))
            return (*values, new_count, *[gr.update(visible=i < new_count) for i in range(5)],
                    gr.update(selected="create"))

        applied = gallery.click(fn=apply_gallery_voice, inputs=[target_role, speaker_count],
            outputs=[*voice_selects, *refs, *prompts, *sources, *asr_statuses, *languages,
                     speaker_count, *panels, workspace_tabs], queue=False)
        applied.then(fn=lambda *paths: paths, inputs=refs, outputs=sources, queue=False)
        gr.on([dialogue.change, length.change], fn=script_summary, inputs=[dialogue, length],
            outputs=[script_meta], queue=False)
        for ref, prompt, source, asr_status, language, retry in zip(
                refs, prompts, sources, asr_statuses, languages, retries):
            result = gr.State(None)
            gr.on(triggers=[ref.input, retry.click], fn=prepare_transcription, inputs=[ref],
                  outputs=[prompt, asr_status, source], queue=False, trigger_mode="multiple").then(
                fn=transcribe_reference, inputs=[ref, language], outputs=[result],
                concurrency_limit=1, concurrency_id="speech-generation", trigger_mode="always_last").then(
                fn=apply_transcription, inputs=[ref, prompt, result],
                outputs=[prompt, asr_status, source], queue=False, trigger_mode="multiple")
            prompt.input(fn=lambda path: path, inputs=[ref], outputs=[source], queue=False)
        for selector, ref, prompt, source, asr_status, language, preview in zip(
                voice_selects, refs, prompts, sources, asr_statuses, languages, previews):
            selection = selector.input(fn=select_library_voice, inputs=[selector],
                outputs=[ref, prompt, source, asr_status, language], queue=False)
            selection.then(fn=lambda path: path, inputs=[ref], outputs=[source], queue=False)
            selector.change(fn=preview_voice, inputs=[selector], outputs=[preview], queue=False)
            ref.input(fn=lambda: "", outputs=[selector], queue=False)
        for selector, ref, prompt, source, asr_status, language, name, save, confirmed in zip(
                voice_selects, refs, prompts, sources, asr_statuses, languages, voice_names, save_buttons, rights):
            saved = save.click(fn=save_library_voice,
                inputs=[ref, prompt, name, language, confirmed],
                outputs=[asr_status, selector, library_status, ref, prompt, source, name], queue=False)
            saved.then(fn=lambda path: path, inputs=[ref], outputs=[source], queue=False)
            saved.then(fn=refresh_voice_library, outputs=[*voice_selects, library_status], queue=False)
            saved.then(fn=library_gallery, inputs=[search, category], outputs=[gallery], queue=False)
        gr.on([refresh_library.click, library_refresh.click], fn=refresh_voice_library,
            outputs=[*voice_selects, library_status], queue=False).then(
                fn=library_gallery, inputs=[search, category], outputs=[gallery], queue=False)
        gr.on([search.change, category.change], fn=library_gallery, inputs=[search, category], outputs=[gallery], queue=False)
        for name, button in zip(EXAMPLES, example_buttons):
            button.click(fn=lambda name=name: select_example(name),
                outputs=[speaker_count, dialogue, *refs, *prompts, *panels, *sources, *asr_statuses,
                         *voice_selects], queue=False).then(fn=script_summary, inputs=[dialogue, length],
                            outputs=[script_meta], queue=False)

        def generate_with_progress(count, *inputs, progress=gr.Progress()):
            inputs, source_paths = inputs[:-5], inputs[-5:]
            mismatch = validate_reference_sources(inputs[:5], inputs[5:10], source_paths, count)
            if mismatch:
                return None, "请检查参考音色：" + mismatch
            for idx in range(int(count)):
                if inputs[idx] and not str(inputs[5 + idx] or "").strip():
                    return None, f"请等待角色 {idx + 1} 的原文识别完成，再生成语音。"
            progress(None, desc="正在配音并核对台词…")
            result = generate(count, *inputs, args.model_path, args.codec_path,
                              args.device, args.attn_implementation, args.dtype, args.codec_device)
            progress(1, desc="处理完成")
            return result

        submitted = run.click(fn=lambda: (None, "任务已提交，正在排队、配音或核对台词…", gr.update(interactive=False)),
            outputs=[output, status, run], queue=False)
        generation = submitted.then(fn=generate_with_progress,
            inputs=[speaker_count, *refs, *prompts, dialogue, normalize, resample,
                    temperature, top_p, top_k, repetition, length, *sources], outputs=[output, status],
            concurrency_limit=1, concurrency_id="speech-generation")
        generation.then(fn=lambda: gr.update(interactive=True), outputs=[run], queue=False)
    return demo
