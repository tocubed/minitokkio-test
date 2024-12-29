import asyncio
import os
import grpc
import av
from nvidia_ace.a2f.v1_pb2 import AudioWithEmotion, EmotionPostProcessingParameters, FaceParameters, BlendShapeParameters
from nvidia_ace.services.a2f_controller.v1_pb2_grpc import A2FControllerServiceStub
from nvidia_ace.audio.v1_pb2 import AudioHeader
from nvidia_ace.controller.v1_pb2 import AudioStream, AudioStreamHeader

NVAPI_KEY = os.getenv('NVAPI_KEY')

A2F_SAMPLE_RATE = 48000

async def nv_a2f_service_stream():
    metadata=[
        ('function-id', '52f51a79-324c-4dbe-90ad-798ab665ad64'),
        ('authorization', 'Bearer ' + NVAPI_KEY)
    ]
    creds = grpc.ssl_channel_credentials(None)
    def metadata_callback(context, callback):
        callback(metadata, None)
    auth_creds = grpc.metadata_call_credentials(metadata_callback)
    creds = grpc.composite_channel_credentials(creds, auth_creds)
    channel = grpc.aio.secure_channel("grpc.nvcf.nvidia.com:443", creds)
    stub = A2FControllerServiceStub(channel)
    return stub.ProcessAudioStream()

async def resample_audio(audio, target_sample_rate=48000, chunk_size_ms=100):
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

async def a2f_write_to_stream(stream, audio, sample_rate=A2F_SAMPLE_RATE):
    audio_stream_header = AudioStream(
        audio_stream_header=AudioStreamHeader(
            audio_header=AudioHeader(
                samples_per_second=sample_rate,
                bits_per_sample=16,
                channel_count=1,
                audio_format=AudioHeader.AUDIO_FORMAT_PCM
            ),
            emotion_post_processing_params=EmotionPostProcessingParameters(),
            face_params=FaceParameters(),
            blendshape_params=BlendShapeParameters()
        )
    )
    await stream.write(audio_stream_header)
    async for chunk in resample_audio(audio, target_sample_rate=A2F_SAMPLE_RATE):
        await stream.write(AudioStream(audio_with_emotion=AudioWithEmotion(audio_buffer=chunk)))

async def a2f_read_from_stream(stream):
    bs_names = []    
    while True:
        message = await stream.read()
        if message == grpc.aio.EOF:
            break
        elif message.HasField("animation_data_stream_header"):
            animation_data_stream_header = message.animation_data_stream_header
            bs_names = animation_data_stream_header.skel_animation_header.blend_shapes
        elif message.HasField("animation_data"):
            animation_data = message.animation_data
            bs_list = animation_data.skel_animation.blend_shape_weights
            for blendshapes in bs_list:
                bs_values_dict = dict(zip(bs_names, blendshapes.values))
                yield {
                    "timeCode": blendshapes.time_code,
                    "blendShapes": bs_values_dict
                }

async def animation_handler(bus, session_id):
    audio_out = bus.subscribe(f'/sessions/{session_id}/audio_out')

    async def audio():
        while True:
            frame = await audio_out.get()
            yield frame
    
    stream = await nv_a2f_service_stream()
    writer = asyncio.create_task(a2f_write_to_stream(stream, audio()))

    async for keyframe in a2f_read_from_stream(stream):
        await bus.publish(f'/sessions/{session_id}/anim_out', keyframe)

class Animation:
    def __init__(self, bus):
        self.bus = bus
        self.session_new = bus.subscribe('/session_new')
        self.handlers = {}

    async def run(self):
        while True:
            session_id = await self.session_new.get()
            self.handlers[session_id] = asyncio.create_task(animation_handler(self.bus, session_id))

    async def shutdown(self):
        self.bus.unsubscribe('/session_new', self.session_new)
        await asyncio.gather(*self.handlers.values())
