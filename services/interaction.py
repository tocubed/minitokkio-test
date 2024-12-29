import asyncio
import aiohttp
import os
import openai
import json
from typing import cast

NVAPI_KEY = os.getenv('NVAPI_KEY')

SYSTEM_PROMPT = '''
You are a helpful assistant. You answer in a conversational tone.
Keep your messages brief to allow a quick exchange of dialogue.
'''

async def interaction_handler(bus, session_id):
    # return
    text_in = bus.subscribe(f'/sessions/{session_id}/text_in')

    async with aiohttp.ClientSession() as client:
        client.headers['Authorization'] = f'Bearer {NVAPI_KEY}'
        client.headers['Content-Type'] = 'application/json'

        async def completions_create(messages):
            payload = {
                "model": "meta/llama3-8b-instruct",
                "messages": messages,
                "temperature": 0.5,
                "top_p": 1,
                "max_tokens": 256,
                "stream": True,
            }
            try:
                async with client.post('https://integrate.api.nvidia.com/v1/chat/completions', json=payload) as response:
                    if response.status == 200:
                        async for line in response.content:
                            line = line.decode("utf-8").strip()
                            if line.startswith('data:'): line = line[5:].strip()
                            if line.startswith('[DONE]'): break
                            if not line: continue
                            try:
                                chunk = json.loads(line)
                                yield chunk
                            except json.JSONDecodeError as e:
                                print(f'LLM API Error: {e}')
                                continue
                    else:
                        print(f'LLM API Error: Status code {response.status}')
            except aiohttp.ClientError as e:
                print(f'HTTP Error: {e}')

        messages = [{'role':'system', 'content': SYSTEM_PROMPT}]

        while True:
            while messages[-1]['role'] != 'user':
                while True:
                    text = await text_in.get()
                    messages.append({'role': 'user', 'content': text})
                    if text_in.empty(): break

            print('User: ' + messages[-1]['content'])
            print('AI: ', end='', flush=True)

            assistant_response = ''
            async for chunk in completions_create(messages):
                if not text_in.empty():
                    print('\n[ User interruption ]\n')
                    break
                if 'content' in chunk['choices'][0]['delta']:
                    chunk = chunk['choices'][0]['delta']['content']
                    print(chunk, end="")
                    assistant_response += chunk
            else:
                print('\n')

            if assistant_response.strip():
                await bus.publish(f'/sessions/{session_id}/text_out', assistant_response)
                messages.append({'role': 'assistant', 'content': assistant_response})
    
class Interaction:
    def __init__(self, bus):
        self.bus = bus
        self.session_new = bus.subscribe('/session_new')
        self.handlers = {}

    async def run(self):
        while True:
            session_id = await self.session_new.get()
            self.handlers[session_id] = asyncio.create_task(interaction_handler(self.bus, session_id))

    async def shutdown(self):
        self.bus.unsubscribe('/session_new', self.session_new)
        await asyncio.gather(*self.handlers.values())