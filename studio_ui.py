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
</script>
"""

EXAMPLES = {
    "双人对话": (2, "[S1]你好，欢迎来到我们的语音工作室。\n[S2]你好，今天我们来测试中文对话生成。"),
    "单人朗读": (1, "[S1]你好，欢迎来到我们的语音工作室。今天我们来测试中文语音生成。"),
    "播客开场": (2, "[S1]欢迎收听今天的播客，我是主持人小林。今天我们来聊聊人工智能如何帮助我们的日常工作。\n[S2]大家好，我是小陈。我们就从一个简单的例子开始吧。"),
}

CSS = """
.gradio-container {max-width: 1280px !important; margin: auto; padding: 24px !important;
  font-family: 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif !important;
  --body-text-color-subdued: #596579; --block-info-text-color: #596579;}
.dark .gradio-container {--body-text-color-subdued: #bbc8d8; --block-info-text-color: #bbc8d8;}
#studio-hero {padding: 28px 30px; border-radius: 20px; background: #edf7f3;
  border: 1px solid #d4e8de; margin-bottom: 8px; color: #183c32;}
#studio-hero h1 {font-size: clamp(24px,3vw,32px); line-height: 1.4; margin: 6px 0 10px; color: #183c32;}
#studio-hero p {font-size: 15px; line-height: 1.8; margin: 0; color: #46675b;}
.studio-eyebrow {font-size: 12px; letter-spacing: 1px; font-weight: 600;}
#studio-steps {padding: 8px 4px; color: #52685d;}
#studio-input, #studio-output {border: 1px solid var(--border-color-primary); border-radius: 18px;
  padding: 22px; background: var(--block-background-fill); min-width: 0;}
#dialogue textarea {font-size: 16px; line-height: 1.85;}
#run-btn {min-height: 52px; font-size: 17px; border-radius: 12px; background: #166853; color: white; border: 0;}
#run-btn:hover {background: #105340;}
#output-status textarea {font-size: 14px; line-height: 1.85;}
#studio-output {position: sticky; top: 18px;}
.studio-tip {padding: 12px 14px; border-radius: 10px; background: var(--background-fill-secondary); line-height: 1.8;}
.voice-library-box {padding: 14px; border-radius: 12px; background: var(--background-fill-secondary);}
@media (max-width: 800px) {
 .gradio-container {padding: 12px !important;}
 #studio-hero {padding: 20px;}
 #studio-input, #studio-output {padding: 16px;}
 #studio-output {position: static;}
}
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
        return (voice["audio_path"], voice["prompt_text"], voice["audio_path"],
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
                voice["audio_path"], voice["prompt_text"], voice["audio_path"], "")
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


def build_studio(args, generate, update_panels, max_tokens):
    with gr.Blocks(title="云途觉晓多人云音创作平台") as demo:
        gr.HTML('''<div id="studio-hero"><div class="studio-eyebrow">云途觉晓 · 多人云音创作平台</div>
          <h1>把文字，变成有声音的对话。</h1>
          <p>支持单人朗读、多人对话和参考音色续说。写好台词，就可以开始。</p></div>''')
        gr.Markdown("**① 写台词**　→　**② 按需设置音色**　→　**③ 生成并试听**", elem_id="studio-steps")
        with gr.Row(equal_height=False):
            with gr.Column(scale=3, min_width=320, elem_id="studio-input"):
                gr.Markdown("## ① 写下你想说的话")
                with gr.Row():
                    example_buttons = [gr.Button(name, size="sm", min_width=0) for name in EXAMPLES]
                gr.Markdown("点击示例即可填入台词，同时清空已有参考音色。")
                speaker_count = gr.Slider(1, 5, value=2, step=1, label="说话人数",
                    info="支持 1～5 人。台词中的 [S1] 对应说话人 1，[S2] 对应说话人 2。")
                dialogue = gr.Textbox(value=EXAMPLES["双人对话"][1], label="对话台词", lines=6,
                    placeholder="[S1]你好，欢迎来到今天的节目。\n[S2]很高兴和大家见面。",
                    info="每次换人说话，在句首加上对应标记。单人朗读也需要 [S1]。", elem_id="dialogue")
                with gr.Accordion("② 参考音色 · 可选，不上传也能生成", open=False):
                    gr.Markdown("上传参考音频后，**服务器会自动识别并填写原文**，无需逐字输入。识别完成后核对一下，即可沿用这个声音续说新台词。\n\n"
                                "建议使用 5～30 秒的清晰单人人声；自动识别最长支持 2 分钟。音频仅在本服务器处理，不发送给第三方。")
                    with gr.Group(elem_classes="voice-library-box"):
                        library_status = gr.Markdown(voice_library_summary())
                        with gr.Row():
                            refresh_library = gr.Button("刷新音色列表", size="sm")
                            rights_confirmed = gr.Checkbox(
                                label="我确认拥有所保存声音的使用授权",
                                info="只在把上传音频保存为“我的音色”时需要勾选。",
                            )
                        gr.Markdown("内置音色均显示来源与许可证；“我的音色”永久保存在本服务器。")
                    refs, prompts, panels, sources, asr_statuses, languages, retries = [], [], [], [], [], [], []
                    voice_selects, voice_names, save_buttons = [], [], []
                    initial_voice_choices = current_voice_choices()
                    for idx in range(1, 6):
                        with gr.Group(visible=idx <= 2) as panel:
                            gr.Markdown(f"**说话人 {idx} · [S{idx}]**")
                            voice_selects.append(gr.Dropdown(
                                choices=initial_voice_choices,
                                value="",
                                label=f"从音色库选择 · 说话人 {idx}",
                                info="选择后会自动填入参考音频和已保存的原文。",
                            ))
                            refs.append(gr.Audio(label=f"说话人 {idx} 的参考音频", type="filepath",
                                sources=["upload"], buttons=["download"], elem_id=f"reference-{idx}"))
                            languages.append(gr.Dropdown(list(LANGUAGES), value="自动识别",
                                label="参考音频语言", info="通常无需选择；识别不准时可指定语言后重新识别。"))
                            asr_statuses.append(gr.Markdown(IDLE_STATUS))
                            prompts.append(gr.Textbox(label=f"说话人 {idx} 的参考原文", lines=2,
                                placeholder="上传音频后自动填写，也可手动输入。这里是参考音频的原话，不是新台词。",
                                info="请核对人名、数字和漏字。更换音频或重新识别会清空原文。"))
                            retries.append(gr.Button("重新识别原文（覆盖现有文字）", size="sm"))
                            with gr.Row():
                                voice_names.append(gr.Textbox(
                                    label="保存为我的音色",
                                    placeholder="例如：我的播客主持人",
                                    max_lines=1,
                                ))
                                save_buttons.append(gr.Button("保存当前音色", size="sm"))
                            sources.append(gr.State(None))
                        panels.append(panel)
                with gr.Accordion("高级设置 · 初次使用保持默认即可", open=False):
                    normalize = gr.Checkbox(value=True, label="自动整理台词格式（推荐）",
                        info="整理标点、说话人标记和连续台词。")
                    resample = gr.Checkbox(value=False, label="统一参考音频采样率",
                        info="多段参考音频采样率不一致时可开启。")
                    temperature = gr.Slider(0.1, 3.0, value=1.1, step=0.05, label="语气变化程度",
                        info="数值越高，表达变化越多；过高可能影响稳定性。默认 1.1。")
                    top_p = gr.Slider(0.1, 1.0, value=0.9, step=0.01, label="候选概率范围",
                        info="控制候选声音的累计概率范围。默认 0.9，一般无需调整。")
                    top_k = gr.Slider(1, 200, value=50, step=1, label="候选数量",
                        info="每一步最多考虑多少种候选声音。默认 50。")
                    repetition = gr.Slider(0.8, 2.0, value=1.1, step=0.05, label="重复抑制强度",
                        info="略微提高可减少重复；过高可能影响自然度。默认 1.1。")
                    length = gr.Slider(256, 8192, value=max_tokens, step=1, label="生成长度上限",
                        info="这是生成步数，不是秒数。达到上限可能截断台词；长文本可适当提高。")
                run = gr.Button("生成语音", variant="primary", elem_id="run-btn")
                gr.Markdown("服务会依次处理任务。较长台词需要更多时间，请耐心等待。")
            with gr.Column(scale=2, min_width=300, elem_id="studio-output"):
                gr.Markdown("## ③ 试听你的作品")
                output = gr.Audio(label="生成的语音", type="numpy", interactive=False,
                                  buttons=["download"], elem_id="output-audio")
                status = gr.Textbox(label="生成状态", value="准备好了。可以直接生成示例，也可以先修改台词。",
                    lines=5, interactive=False, elem_id="output-status")
                gr.Markdown("生成完成后，点击播放按钮试听；点击播放器右上角的下载按钮保存音频。", elem_classes="studio-tip")
                with gr.Accordion("使用小贴士", open=True):
                    gr.Markdown("- **只想试一试？** 保持默认，直接点击「生成语音」。\n"
                                "- **想固定声音？** 展开「参考音色」，上传音频后等待自动识别原文。\n"
                                "- **台词没有读完？** 在高级设置中提高生成长度上限，或拆成更短的段落。\n"
                                "- **多人对话？** 检查人数与 [S1]～[S5] 标记是否一致。")
        # Presets update the panels themselves; only user edits need this event.
        speaker_count.input(fn=update_panels, inputs=[speaker_count], outputs=panels, queue=False)
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
        for selector, ref, prompt, source, asr_status, language in zip(
                voice_selects, refs, prompts, sources, asr_statuses, languages):
            selection = selector.change(fn=select_library_voice, inputs=[selector],
                outputs=[ref, prompt, source, asr_status, language], queue=False)
            # Gradio copies returned files into its cache. Record that effective
            # path after the Audio component has processed the library file.
            selection.then(fn=lambda path: path, inputs=[ref], outputs=[source], queue=False)
            ref.input(fn=lambda: "", outputs=[selector], queue=False)
        for selector, ref, prompt, source, asr_status, language, name, save in zip(
                voice_selects, refs, prompts, sources, asr_statuses, languages, voice_names, save_buttons):
            saved = save.click(fn=save_library_voice,
                inputs=[ref, prompt, name, language, rights_confirmed],
                outputs=[asr_status, selector, library_status, ref, prompt, source, name], queue=False)
            saved.then(fn=lambda path: path, inputs=[ref], outputs=[source], queue=False)
        refresh_library.click(fn=refresh_voice_library,
            outputs=[*voice_selects, library_status], queue=False)
        for name, button in zip(EXAMPLES, example_buttons):
            button.click(fn=lambda name=name: select_example(name),
                outputs=[speaker_count, dialogue, *refs, *prompts, *panels, *sources, *asr_statuses,
                         *voice_selects], queue=False)

        def generate_with_progress(count, *inputs, progress=gr.Progress()):
            inputs, source_paths = inputs[:-5], inputs[-5:]
            mismatch = validate_reference_sources(inputs[:5], inputs[5:10], source_paths, count)
            if mismatch:
                return None, "请检查参考音色：" + mismatch
            for idx in range(int(count)):
                if inputs[idx] and not str(inputs[5 + idx] or "").strip():
                    return None, f"请等待说话人 {idx + 1} 的原文识别完成；若识别失败，可重新识别或手动填写。"
            progress(None, desc="正在生成语音，请稍候…")
            result = generate(count, *inputs, args.model_path, args.codec_path,
                              args.device, args.attn_implementation, args.dtype, args.codec_device)
            progress(1, desc="处理完成")
            return result

        run.click(fn=lambda: (None, "任务已提交，正在排队或生成语音，请稍候…"),
            outputs=[output, status], queue=False).then(fn=generate_with_progress,
            inputs=[speaker_count, *refs, *prompts, dialogue, normalize, resample,
                    temperature, top_p, top_k, repetition, length, *sources], outputs=[output, status],
            concurrency_limit=1, concurrency_id="speech-generation")
    return demo
