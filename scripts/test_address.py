import asyncio
import json
from tools_address import search_address

async def main():
    print("Testing Eircode A92YDW7...")
    result = await search_address("A92YDW7")
    print("\nResult:")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
