import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print('Navigating...')
        await page.goto('http://localhost:5000')
        await page.wait_for_timeout(2000)
        
        print('Typing password...')
        await page.fill('input[type="password"]', 'noodleboxadmin!')
        await page.keyboard.press('Enter')

        await page.wait_for_timeout(3000)
        
        screenshot_path = r'C:\Users\wenbi\.gemini\antigravity\brain\4ce65023-80d3-4dbe-85d5-bb65a47ed279\wait_queue_dashboard_admin_1772996141228.png'
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f'Screenshot saved to {screenshot_path}')
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
