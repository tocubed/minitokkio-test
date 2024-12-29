import asyncio
import riva.client
import os
import av
import numpy as np
import time

NVAPI_KEY = os.getenv('NVAPI_KEY')

ASR_SAMPLE_RATE = 48000
TTS_SAMPLE_RATE = 48000

def riva_asr_streaming_response(chunks):
    auth = riva.client.Auth(uri='grpc.nvcf.nvidia.com:443', use_ssl=True, metadata_args=[
        ('function-id', '1598d209-5e27-4d3c-8079-4751568b1081'),
        ('authorization', 'Bearer ' + NVAPI_KEY)
    ])
    service = riva.client.ASRService(auth)
    config = riva.client.StreamingRecognitionConfig(config=riva.client.RecognitionConfig(
        language_code = 'en-US',
        encoding = riva.client.AudioEncoding.LINEAR_PCM,
        sample_rate_hertz = ASR_SAMPLE_RATE,
        max_alternatives = 1,
        enable_automatic_punctuation = True,
        verbatim_transcripts = False,
    ), interim_results=False)
    return service.streaming_response_generator(chunks, config)

def riva_tts_service():
    auth = riva.client.Auth(uri='grpc.nvcf.nvidia.com:443', use_ssl=True, metadata_args=[
        ('function-id', '0149dedb-2be8-4195-b9a0-e57e0e14f972'),
        ('authorization', 'Bearer ' + NVAPI_KEY)
    ])
    service = riva.client.SpeechSynthesisService(auth)
    return service

async def resample_audio(audio, target_sample_rate=ASR_SAMPLE_RATE, chunk_size_ms=100):
    chunk_size = int(2 * target_sample_rate * chunk_size_ms / 1000)
    resampler = av.AudioResampler(
        format='s16',
        layout='mono',
        rate=target_sample_rate,
    )
    buffer = bytearray()
    async for frame in audio:
        resampled_frames = resampler.resample(frame)
        for frame in resampled_frames:
            buffer.extend(bytes(frame.planes[0]))
        while len(buffer) >= chunk_size:
            chunk = buffer[:chunk_size]
            yield bytes(chunk)
            buffer = buffer[chunk_size:]

async def asr_handler(bus, session_id):
    audio_in = bus.subscribe(f'/sessions/{session_id}/audio_in')
    
    async def speech_frames_async():
        while True:
            frame = await audio_in.get()
            yield frame

    loop = asyncio.get_running_loop()
    def speech_chunks():
        chunks = resample_audio(speech_frames_async())
        try:
            while True:
                result = asyncio.run_coroutine_threadsafe(anext(chunks), loop)
                yield result.result()
        except StopAsyncIteration:
            pass
    
    def stream_results():
        responses = riva_asr_streaming_response(speech_chunks())
        for res in responses:
            if not res.results: continue
            for r in res.results:
                if r.is_final:
                    transcript = r.alternatives[0].transcript
                    asyncio.run_coroutine_threadsafe(bus.publish(f'/sessions/{session_id}/text_in', transcript), loop)

    await asyncio.create_task(asyncio.to_thread(stream_results))

async def tts_handler(bus, session_id):
    tts_service = riva_tts_service()
    start = time.monotonic()

    loop = asyncio.get_running_loop()
    def stream_results(text, interrupt, audio_id):
        results = tts_service.synthesize_online(text, 
            voice_name='English-US.Male-1',
            language_code='en-US',
            encoding=riva.client.AudioEncoding.LINEAR_PCM,
            sample_rate_hz=TTS_SAMPLE_RATE
        )

        pts = int(TTS_SAMPLE_RATE * (time.monotonic() - start))
        for res in results:
            if interrupt.is_set(): break
            arr = np.frombuffer(res.audio, dtype=np.int16)
            frame = av.AudioFrame.from_ndarray(arr.reshape((1, -1)), format='s16', layout='mono')
            frame.pts = pts
            frame.sample_rate = TTS_SAMPLE_RATE
            pts += frame.samples
            async def update():
                await bus.publish(f'/sessions/{session_id}/speech_out', frame)
                await bus.publish(f'/sessions/{session_id}/speech_out/id', audio_id)
            future = asyncio.run_coroutine_threadsafe(update(), loop)
            future.result()
    
    audio_id = 0
    text_out = bus.subscribe(f'/sessions/{session_id}/text_out')
    interrupt = None
    while True:
        text = await text_out.get()
        if interrupt is not None: interrupt.set()
        audio_id += 1
        interrupt = asyncio.Event()
        asyncio.create_task(asyncio.to_thread(lambda: stream_results(text, interrupt, audio_id)))

async def speech_handler(bus, session_id):
    await asyncio.gather(asr_handler(bus, session_id), tts_handler(bus, session_id))

class Speech:
    def __init__(self, bus):
        self.bus = bus
        self.session_new = bus.subscribe('/session_new')
        self.handlers = {}

    async def run(self):
        while True:
            session_id = await self.session_new.get()
            self.handlers[session_id] = asyncio.create_task(speech_handler(self.bus, session_id))

    async def shutdown(self):
        self.bus.unsubscribe('/session_new', self.session_new)
        await asyncio.gather(*self.handlers.values())