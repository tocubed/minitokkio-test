import aiohttp.web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc import AudioStreamTrack
from aiortc.contrib.media import MediaRecorder
import asyncio
import numpy as np
import av
import json

AUDIO_OUT_CHUNK_SIZE_MS = 20
AUDIO_OUT_DELAY_MS = 400 # TODO Priyank: a static delay seems to work fine but dynamic sync may be necessary
AUDIO_OUT_SAMPLE_RATE = 48000 # TODO Priyank: this needs to match what webrtc peer expects

def chunk_audio_frame(frame, chunk_size, sample_rate):
    raw_audio = bytes(frame.planes[0])
    total_samples = len(raw_audio) // 2  # since each sample is 2 bytes (16-bit PCM)
    chunks = []
    for i in range(0, total_samples, chunk_size):
        chunk_data = raw_audio[i * 2 : (i + chunk_size) * 2]
        audio_array = np.frombuffer(chunk_data, dtype=np.int16).reshape((1, -1))
        chunk_frame = av.AudioFrame.from_ndarray(audio_array, format='s16', layout='mono')
        chunk_frame.pts = frame.pts + i
        chunk_frame.sample_rate = sample_rate
        chunks.append(chunk_frame)
    return chunks

def silent_frame(duration, pts, sample_rate):
    frame_size = int(duration * sample_rate)
    frame = av.AudioFrame.from_ndarray(np.zeros((1, frame_size), dtype=np.int16), format='s16', layout='mono')
    frame.pts = pts
    frame.sample_rate = sample_rate
    return frame

async def audio_out_handler(bus, session_id, sample_rate, out_topic=f'audio_out', delay_s=None):
    queue = bus.subscribe(f'/sessions/{session_id}/speech_out')
    id_queue = bus.subscribe(f'/sessions/{session_id}/speech_out/id')
    out_topic = f'/sessions/{session_id}/{out_topic}'

    chunk_size = int(sample_rate * AUDIO_OUT_CHUNK_SIZE_MS / 1000)
    frames = []
    last_audio_id = 0
    while True:
        while not queue.empty() or len(frames) == 0:
            frame = await queue.get()
            audio_id = await id_queue.get() 
            if audio_id > last_audio_id:
                frames.clear()
                last_audio_id = audio_id
                if delay_s is not None: 
                    frames += chunk_audio_frame(silent_frame(delay_s, frame.pts, sample_rate), chunk_size, sample_rate)
            if delay_s is not None: 
                frame.pts += int(delay_s * sample_rate)
            frames += chunk_audio_frame(frame, chunk_size, sample_rate)
        frame = frames.pop(0)
        await bus.publish(out_topic, frame)
        duration = frame.samples / sample_rate
        await asyncio.sleep(duration)

class BusAudioOut(AudioStreamTrack):
    sample_rate = 48000
    def __init__(self, bus, session_id):
        super().__init__()
        self.bus = bus
        self.session_id = session_id
        self.queue = bus.subscribe(f'/sessions/{session_id}/audio_out/delayed')

    async def recv(self):
        frame = await self.queue.get()
        return frame

    def stop(self):
        super().stop()
        self.bus.unsubscribe(f'/sessions/{self.session_id}/audio_out/delayed', self.queue)

async def channel_handler(bus, session_id, channel):
    text_in = bus.subscribe(f'/sessions/{session_id}/text_in')
    text_out = bus.subscribe(f'/sessions/{session_id}/text_out')
    anim_out = bus.subscribe(f'/sessions/{session_id}/anim_out')
    
    async def handle(queue, func):
        while True:
            item = await queue.get()
            func(item)
    handlers = [
        handle(text_in, lambda text: channel.send(json.dumps({'kind': 'log', 'message': 'User: ' + text}))),
        handle(text_out, lambda text: channel.send(json.dumps({'kind': 'log', 'message': 'Assistant: ' + text}))),
        handle(anim_out, lambda anim: channel.send(json.dumps({'kind': 'anim', 'message': anim})))
    ]
    await asyncio.gather(*handlers)

class Streaming:
    def __init__(self, bus):
        self.bus = bus
        self.pcs = {}
        self.channel_handlers = {}
        self.audio_handlers = {}
        app = aiohttp.web.Application()
        app.router.add_get('/', self.index)
        app.router.add_post('/offer', self.offer)
        app.router.add_static('/assets/', path='static/')
        self.runner = aiohttp.web.AppRunner(app)

    async def run(self):
        await self.runner.setup()
        site = aiohttp.web.TCPSite(self.runner, '0.0.0.0', 5000)
        await site.start()
        print("[ Serving on 0.0.0.0:5000 ]")
        while True: await asyncio.sleep(999)
    
    async def shutdown(self):
        tasks = [pc.close() for pc in self.pcs.values()]
        await asyncio.gather(*tasks)
        await self.runner.cleanup()

    async def index(self, request):
        return aiohttp.web.FileResponse('static/index.html')

    async def offer(self, request):
        params = await request.json()
        session_id = params.get('session_id')
        pc = self.pcs[session_id] = RTCPeerConnection()
        pc.addTrack(BusAudioOut(self.bus, session_id))
        self.audio_handlers[session_id] = {
            '':  asyncio.create_task(audio_out_handler(self.bus, session_id, sample_rate=AUDIO_OUT_SAMPLE_RATE, out_topic='audio_out')),
            'delayed':  asyncio.create_task(audio_out_handler(self.bus, session_id, sample_rate=AUDIO_OUT_SAMPLE_RATE, out_topic='audio_out/delayed', delay_s=(AUDIO_OUT_DELAY_MS/1000))),
        }
        await self.bus.publish('/session_new', session_id)

        @pc.on('track')
        async def on_track(track):
            pc.addTrack(track)
            if track.kind == 'video':
                while True:
                    frame = await track.recv()
                    await self.bus.publish(f'/sessions/{session_id}/video_in', frame)
            if track.kind == 'audio':
                while True:
                    frame = await track.recv()
                    await self.bus.publish(f'/sessions/{session_id}/audio_in', frame)

        @pc.on("datachannel")
        def on_datachannel(channel):
            self.channel_handlers[session_id] = asyncio.create_task(channel_handler(self.bus, session_id, channel))

        offer = RTCSessionDescription(sdp=params['sdp']['sdp'], type=params['sdp']['type'])
        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        return aiohttp.web.json_response({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})