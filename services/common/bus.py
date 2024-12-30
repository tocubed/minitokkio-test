import asyncio
from collections import defaultdict

class Bus:
    def __init__(self):
        self.subscribers = defaultdict(list)

    async def publish(self, topic, message):
        for queue in self.subscribers[topic]:
            await queue.put(message)

    def subscribe(self, topic):
        queue = asyncio.Queue()
        self.subscribers[topic].append(queue)
        return queue

    def unsubscribe(self, topic, queue):
        if queue in self.subscribers[topic]:
            self.subscribers[topic].remove(queue)