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
'''
# Example Usage
async def producer(pubsub):
    while True:
        await asyncio.sleep(1)
        await pubsub.publish("topic1", "message")

async def consumer(pubsub, name):
    queue = pubsub.subscribe("topic1")
    while True:
        message = await queue.get()
        print(f"{name} received: {message}")

async def main():
    pubsub = PubSub()
    await asyncio.gather(
        producer(pubsub),
        consumer(pubsub, "Consumer 1"),
        consumer(pubsub, "Consumer 2")
    )

asyncio.run(main())
'''