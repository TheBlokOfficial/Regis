import asyncio
import logging
from .node import SatelliteNode

async def main():
    node = SatelliteNode()
    await node.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Satelita zamykana.")
