import asyncio
from services.streaming import Streaming 
from services.speech import Speech
from services.interaction import Interaction
from services.animation import Animation
from services.common.bus import Bus

if __name__ == '__main__':
    bus = Bus()
    services = [Streaming(bus), Speech(bus), Interaction(bus), Animation(bus)]
    loop = asyncio.get_event_loop()
    try:
        tasks = [service.run() for service in services]
        loop.run_until_complete(asyncio.gather(*tasks))
    except KeyboardInterrupt:
        print('Shutting down...')
        pass
    tasks = [service.shutdown() for service in services]
    loop.run_until_complete(asyncio.gather(*tasks))