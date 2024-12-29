import aiohttp.web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc import AudioStreamTrack
from aiortc.contrib.media import MediaRecorder
import asyncio
import numpy as np
import av
import json

def chunk_audio_frame(frame, chunk_size, sample_rate=48000):
    raw_audio = bytes(frame.planes[0])
    total_samples = len(raw_audio) // 2  # Each sample is 2 bytes (16-bit PCM)
    chunks = []
    for i in range(0, total_samples, chunk_size):
        chunk_data = raw_audio[i * 2 : (i + chunk_size) * 2]  # Convert samples to bytes range
        audio_array = np.frombuffer(chunk_data, dtype=np.int16).reshape((1, -1))
        chunk_frame = av.AudioFrame.from_ndarray(audio_array, format='s16', layout='mono')
        chunk_frame.pts = frame.pts + i
        chunk_frame.sample_rate = sample_rate
        chunks.append(chunk_frame)
    return chunks

class BusAudioOut(AudioStreamTrack):
    sample_rate = 48000
    def __init__(self, bus, session_id):
        super().__init__()
        self.bus = bus
        self.session_id = session_id
        self.queue = bus.subscribe(f'/sessions/{session_id}/speech_out')
        self.id_queue = bus.subscribe(f'/sessions/{session_id}/speech_out/id')
        self.last_audio_id = 0
        self.frames = []

    async def recv(self):
        while not self.queue.empty() or len(self.frames) == 0:
            frame = await self.queue.get()
            audio_id = await self.id_queue.get() 
            if audio_id > self.last_audio_id:
                self.frames.clear()
                self.last_audio_id = audio_id
            self.frames += chunk_audio_frame(frame, 960, self.sample_rate)
        frame = self.frames.pop(0)
        await self.bus.publish(f'/sessions/{self.session_id}/audio_out', frame)
        duration = frame.samples / self.sample_rate
        await asyncio.sleep(duration)
        return frame

    def stop(self):
        super().stop()
        self.bus.unsubscribe(f'/sessions/{self.session_id}/speech_out', self.queue)
        self.bus.unsubscribe(f'/sessions/{self.session_id}/speech_out/id', self.id_queue)

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