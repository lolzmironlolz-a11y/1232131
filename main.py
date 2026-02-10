import sys
sys.path.append('.')
from bot import mine
import asyncio

if __name__ == "__main__":
    asyncio.run(mine.main())