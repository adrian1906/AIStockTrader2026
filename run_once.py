import asyncio
from backend.trading_floor import create_traders


async def main():
    traders = create_traders()
    await asyncio.gather(*[t.run() for t in traders])


asyncio.run(main())
