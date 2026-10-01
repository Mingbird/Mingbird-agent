#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""语音输入模块:麦克风录音(手动启停)→ 本地模型转录 → 文字。
- 音频按钮可用性: 动态检测当前模型是否支持音频(/api/show capabilities)
- 转录引擎: v1.9.1 起中英双语内置(sherpa-onnx 流式 zipformer,仅 int8 权重);
  按用户选择的语言加载对应模型,优先本地,不可用则回退 ollama 音频模型
"""
import base64, glob as _glob, json, os, sys, time, wave
import urllib.request
import appconfig

OLLAMA = appconfig.ollama_host()

# 内置 STT 模型目录名(v1.9.1 双语):中/英各一个流式 zipformer,只装 int8 权重
STT_MODEL_DIRS = {
    "zh": "sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23",
    "en": "sherpa-onnx-streaming-zipformer-en-20M-2023-02-17",
}

def _stt_bases():
    """候选根目录:模块同目录(开发版=仓库/打包版=_internal)→ 用户目录。"""
    bases = [os.path.dirname(os.path.abspath(__file__))]
    if getattr(sys, "frozen", False):
        for base in (os.path.dirname(sys.executable), os.path.join(os.path.dirname(sys.executable), "_internal"),
                     getattr(sys, "_MEIPASS", "")):
            if base not in bases:
                bases.append(base)
    bases.append(os.path.join(os.path.expanduser("~"), ".ollama_agent"))
    return bases

def _stt_model_dir(lang):
    """按语言找内置模型目录;找不到返回 None。"""
    name = STT_MODEL_DIRS.get(lang) or STT_MODEL_DIRS["zh"]
    for base in _stt_bases():
        p = os.path.join(base, "stt", name)
        if os.path.isdir(p):
            return p
    return None

def _stt_files(d):
    """目录内 int8 三件套 + tokens;对 epoch 命名鲁棒(glob)。"""
    def one(pat):
        hits = sorted(_glob.glob(os.path.join(d, pat)))
        return hits[0] if hits else None
    enc = one("encoder-*-int8.onnx") or one("*encoder*int8*.onnx")
    dec = one("decoder-*-int8.onnx") or one("*decoder*int8*.onnx")
    joi = one("joiner-*-int8.onnx") or one("*joiner*int8*.onnx")
    tok = one("tokens.txt")
    if enc and dec and joi and tok:
        return {"encoder": enc, "decoder": dec, "joiner": joi, "tokens": tok}
    return None

_RECOG_CACHE = {}   # dir -> OnlineRecognizer(重建约百毫秒级,缓存掉)

def model_audio_capable(model):
    """动态检测模型是否支持音频。"""
    try:
        req = urllib.request.Request(f"{OLLAMA}/api/show",
            data=json.dumps({"model": model}).encode(), headers={"Content-Type": "application/json"})
        r = json.loads(urllib.request.urlopen(req, timeout=60).read())
        return "audio" in r.get("capabilities", [])
    except Exception:
        return False

def list_audio_models():
    try:
        r = json.loads(urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=60).read())
        out = []
        for m in r.get("models", []):
            name = m.get("name", "")
            if model_audio_capable(name) or "whisper" in name.lower():
                out.append(name)
        return out
    except Exception:
        return []

def pick_stt_model(preferred):
    try:
        for m in list_audio_models():
            if "whisper" in m.lower():
                return m
    except Exception:
        pass
    return preferred

class Recorder:
    """麦克风流式录音,支持手动 start/stop。
    vad=True 时做能量检测:出现人声后静音超过 silence_ms 自动置 auto_stop
    (由调用方轮询 auto_stop 决定何时结束),避免"说完还要手动点停"。
    """
    def __init__(self, samplerate=16000, vad=True, silence_ms=1200):
        self.samplerate = samplerate
        self.vad = vad
        self.silence_ms = silence_ms
        self._frames = []
        self._stream = None
        self._running = False
        self._speech_seen = False
        self._silence_since = None
        self._auto_stop = False

    def start(self):
        import sounddevice as sd
        self._frames = []
        self._running = True
        self._speech_seen = False
        self._silence_since = None
        self._auto_stop = False
        block_ms = 25
        blocksize = int(self.samplerate * block_ms / 1000)   # 固定 25ms 块,VAD 响应稳定
        def _cb(indata, frames, t, status):
            if self._running:
                self._frames.append(indata.copy())
                if self.vad:
                    self._vad_feed(indata)
        self._stream = sd.InputStream(samplerate=self.samplerate, channels=1,
                                      blocksize=blocksize, callback=_cb, dtype="float32")
        self._stream.start()

    def _vad_feed(self, indata):
        """能量 VAD:出现人声后静音超过 silence_ms → auto_stop=True。"""
        rms = float((indata * indata).mean()) ** 0.5
        if rms > 0.008:                 # 有语音
            self._speech_seen = True
            self._silence_since = None
        elif self._speech_seen:          # 已经说过话,现在安静
            if self._silence_since is None:
                self._silence_since = time.time()
            elif time.time() - self._silence_since > self.silence_ms / 1000.0:
                self._auto_stop = True   # 静音超时 → 让调用方结束

    def stop(self, path):
        """结束录音并保存 16kHz 单声道 WAV。返回 True/False(无声音)。"""
        self._running = False
        if self._stream:
            self._stream.stop(); self._stream.close(); self._stream = None
        if not self._frames:
            return False
        import numpy as np
        audio = np.concatenate(self._frames)[:, 0]
        audio = np.clip(audio, -1.0, 1.0)
        pcm = (audio * 32767).astype(np.int16)
        with wave.open(path, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(self.samplerate)
            w.writeframes(pcm.tobytes())
        return True

def local_stt_available(lang="zh"):
    """内置 sherpa-onnx 模型(按语言)是否可用。"""
    d = _stt_model_dir(lang)
    try:
        import sherpa_onnx
        return bool(d and _stt_files(d))
    except Exception:
        return False

def _recognizer(lang):
    """取(或建)某语言的识别器;不可用返回 None。"""
    d = _stt_model_dir(lang)
    if not d:
        return None
    f = _stt_files(d)
    if not f:
        return None
    if d not in _RECOG_CACHE:
        import sherpa_onnx
        _RECOG_CACHE[d] = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=f["tokens"], encoder=f["encoder"], decoder=f["decoder"],
            joiner=f["joiner"],
            num_threads=1, sample_rate=16000, feature_dim=80,
            decoding_method="greedy_search")
    return _RECOG_CACHE[d]

def transcribe_local(wav_path, lang="zh"):
    """本地 sherpa-onnx 流式模型转录(纯 CPU,快于实时)。可用则优先使用。"""
    try:
        import soundfile as sf
        r = _recognizer(lang) or _recognizer("zh")   # 所选语言缺失时退中文
        if r is None:
            return None
        data, sr = sf.read(wav_path, dtype="float32", always_2d=True)
        s = r.create_stream(); s.accept_waveform(sr, data[:, 0])
        while r.is_ready(s):
            r.decode_stream(s)
        text = r.get_result(s).strip()
        return text or None
    except Exception:
        return None

def transcribe(model, wav_path, lang="zh"):
    """转录:优先本地 sherpa-onnx(按语言),否则用 ollama 音频模型。返回文本(可能为空)。"""
    local = transcribe_local(wav_path, lang)
    if local:
        return local[:500]
    return transcribe_ollama(model, wav_path)

def transcribe_ollama(model, wav_path):
    """把 WAV 交给 ollama 音频模型转录。返回文本(可能为空)。"""
    with open(wav_path, "rb") as _w:
        b64 = base64.b64encode(_w.read()).decode()
    payload = {"model": model,
               "messages": [{"role": "user",
                             "content": "请把这段语音转录成文字,直接输出转录结果,不要解释。",
                             "images": [b64]}],
               "stream": False, "options": {"num_predict": 800, "think": False}}
    req = urllib.request.Request(f"{OLLAMA}/api/chat",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=600).read())
    msg = r.get("message", {})
    content = (msg.get("content") or "").strip()
    if not content:
        content = (msg.get("thinking") or "").strip()
    for marker in ("Thinking Process", "Analysis", "转录结果", "以下为转录"):
        if content.startswith(marker):
            content = content.split("\n", 1)[1] if "\n" in content else ""
            break
    return content[:500]

if __name__ == "__main__":
    model = "gemma4:e4b"
    print("audio capable:", model_audio_capable(model))
    print("audio models:", list_audio_models())
    print("stt model:", pick_stt_model(model))
