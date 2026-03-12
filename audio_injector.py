import wave
import audioop
import base64
import os
import logging
import asyncio

# 获取名为 "AI-Waiter" 的日志记录器，统一管理项目输出
logger = logging.getLogger("AI-Waiter")

# 在内存中缓存音频数据，防止每次处理订单或打字时触发耗时的磁盘 I/O
_twilio_audio_buffer = None
_webrtc_audio_buffer = None

def load_typing_audio(filepath: str = "键盘.wav"):
    """
    功能说明：
        从磁盘加载给定的 WAV 音频文件（默认属于环境掩码音/打字音），
        并将其提前转码（Pre-transcode）为 Twilio 和 WebRTC WebSocket 要求的严格字节流格式。
        这种预处理可以极大节省通话过程中的 CPU 开销，做到零延迟注入。

    Args:
        filepath (str): 需要加载的 WAV 文件路径。

    Returns:
        bool: 成功加载并转码返回 True，否则返回 False。
    """
    global _twilio_audio_buffer, _webrtc_audio_buffer
    
    if not os.path.exists(filepath):
        logger.warning(f"音频注入文件 {filepath} 未找到。已禁用延迟掩码音效。")
        return False
        
    try:
        with wave.open(filepath, 'rb') as w:
            channels = w.getnchannels()
            sampwidth = w.getsampwidth()
            framerate = w.getframerate()
            nframes = w.getnframes()
            
            # 读取精确的原始 PCM 字节流
            raw_pcm = w.readframes(nframes)
            
            # 如果是立体声 (Stereo)，将其混合转化为单声道 (Mono)
            if channels == 2:
                raw_pcm = audioop.tomono(raw_pcm, sampwidth, 0.5, 0.5)
            
            # 1. 准备 WebRTC 格式 (要求：24kHz 采样率, 16-bit PCM)
            # ratecv 用于重采样，将原始帧率转换到明确的 24000
            webrtc_pcm, _ = audioop.ratecv(raw_pcm, sampwidth, 1, framerate, 24000, None)
            _webrtc_audio_buffer = webrtc_pcm
            
            # 2. 准备 Twilio 格式 (要求：8kHz 采样率, 8-bit mu-law/ulaw)
            # 第一步：先降频到 8000Hz PCM
            twilio_pcm, _ = audioop.ratecv(raw_pcm, sampwidth, 1, framerate, 8000, None)
            # 第二步：将 16-bit PCM 压缩成 8-bit ulaw 编码
            _twilio_audio_buffer = audioop.lin2ulaw(twilio_pcm, sampwidth)
            
            duration = nframes / framerate
            logger.info(f"✅ 成功加载延迟掩码音效缓存: {filepath} ({duration:.1f}s)")
            return True
            
    except Exception as e:
        logger.error(f"加载音频注入文件失败: {e}")
        return False

async def stream_audio_to_websocket(ws, format: str, cancel_event: asyncio.Event, stream_sid: str = None):
    """
    功能说明：
        将已经缓存在内存中的音频数组，以稳定的位率连续发送到指定的 WebSocket。
        发送逻辑是非阻塞的，并且会持续循环播放，直到外部显式触发 'cancel_event' 
        或者因网络断开而终止。
    
    Args:
        ws (WebSocket): 当前通话活跃的 FastAPI WebSocket 对象。
        format (str): 通话格式协议，取值 "twilio" 或 "webrtc"。
        cancel_event (asyncio.Event): 异步取消事件锁，一旦触发，立即切断音频循环。
        stream_sid (str, optional): Twilio 特有的媒体流 ID，WebRTC 环境下该值为空。
    """
    global _twilio_audio_buffer, _webrtc_audio_buffer
    
    # 依据系统格式路由到对应的预处理音频缓冲区
    buffer = _twilio_audio_buffer if format == "twilio" else _webrtc_audio_buffer
    if not buffer:
        return
        
    try:
        pointer = 0
        
        # 为了防止向 WebSocket 洪水倒灌数据导致套接字阻塞，我们将音频切片发送 (约 200 毫秒一块)
        # Twilio (8kHz 8bit) 速率 = 8000 字节/秒 -> 每次发送 200ms 就是 1600 字节
        # WebRTC (24kHz 16bit) 速率 = 48000 字节/秒 -> 每次发送 200ms 就是 9600 字节
        chunk_size = 1600 if format == "twilio" else 9600
        tick_delay = 0.20  # 等待周期，200毫秒同步心跳
        
        while not cancel_event.is_set():
            # 在内存中切出一块音频
            end_ptr = pointer + chunk_size
            chunk = buffer[pointer:end_ptr]
            
            # 如果这块音频切不到指定长度，说明到了文件尾部，那么重置指针从头实现“单曲循环”
            if len(chunk) < chunk_size:
                pointer = 0
                continue
                
            pointer = end_ptr
            
            # 发送给 Twilio 的 Media Packet 规范
            if format == "twilio" and stream_sid:
                await ws.send_json({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {
                        "payload": base64.b64encode(chunk).decode('utf-8')
                    }
                })
            # 发送给 WebRTC 的 payload 规范
            elif format == "webrtc":
                await ws.send_json({
                    "event": "media",
                    "payload": base64.b64encode(chunk).decode('utf-8'),
                    "sampleRate": 24000
                })
                
            # 为了防止霸占事件循环，使用 wait_for。
            # 这允许函数在 cancel_event 被外部 set() 的一瞬间立刻醒来并跳出，
            # 若没被 set()，则安静睡完 tick_delay 的 200 毫秒，接着发下一块音频。
            try:
                await asyncio.wait_for(cancel_event.wait(), timeout=tick_delay)
            except asyncio.TimeoutError:
                pass # 到时未触发取消，说明要继续循环
                
    except Exception as e:
        err_str = str(e).lower()
        # WebSocket closed is normal exit, downgrade to INFO
        if any(k in err_str for k in ["websocket.send", "websocket.close", "after sending", "close"]):
            logger.info("Audio injection task ended (WebSocket already closed - normal exit)")
        else:
            logger.error(f"Audio injection stream failed: {e}")
