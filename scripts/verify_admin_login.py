import asyncio
from playwright.async_api import async_playwright
import time

async def test_admin_login():
    async with async_playwright() as p:
        # Launch browser headlessly
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        try:
            print("Navigating to production dashboard...")
            await page.goto("https://gemini-live-api-44671253948.europe-west1.run.app/")
            
            # Wait for the login screen to appear
            await page.wait_for_selector('input[type="password"]', timeout=10000)
            
            print("Entering Admin password...")
            await page.fill('input[type="password"]', 'noodleboxadmin!')
            
            # Intercept network to see the settings payload (ignoring CORS preflights)
            settings_data = None
            async def handle_response(response):
                nonlocal settings_data
                if "/api/admin/settings" in response.url and response.status == 200:
                    if response.request.method != "OPTIONS":
                        try:
                            settings_data = await response.json()
                            print(f"Intercepted Settings GET Response: {settings_data}")
                        except Exception as e:
                            print(f"Failed to parse JSON from /api/admin/settings GET: {e}")
            page.on("response", handle_response)
            
            # Click the second login button (the Admin one)
            login_buttons = await page.query_selector_all('button:has-text("登录系统"), button:has-text("Login")')
            if len(login_buttons) > 1:
                await login_buttons[1].click()
            else:
                await login_buttons[0].click()
            
            # Wait for dashboard to load
            await asyncio.sleep(5)
            
            print(f"Final Captured Settings State: {settings_data}")
            
            # Verify status
            print("Checking AI status in dashboard header...")
            status_text = await page.evaluate('''() => {
                const statusSpan = Array.from(document.querySelectorAll('span')).find(s => s.textContent.includes('当前状态:'));
                return statusSpan ? statusSpan.textContent : 'Status not found';
            }''')
            print(f"Detected Status Component: {status_text}")
            
            if '运行中' in status_text or 'Active' in status_text:
                print("SUCCESS: System successfully transitioned to ACTIVE state after login.")
            else:
                print("ERROR: System still appears OFFLINE or failed to load settings.")
            
            # Take a screenshot to prove the UI state
            await page.screenshot(path="dashboard_verification_live.png")
            print("Saved screenshot of dashboard to dashboard_verification_live.png")

            # Click the WebCall Simulator Button
            print("Attempting to click WebRTC Start Call button...")
            
            # Since we just want to test if it connects, we can click it and see if errors pop up
            # (Note: Audio Context needs a real mic in Playwright to actually encode, but we can verify WS refusal)
            await page.click('button:has-text("开始语音通话")')
            await asyncio.sleep(2)
            
            print("Verification script finished.")
            
        except Exception as e:
            print(f"Exception during tests: {str(e)}")
            await page.screenshot(path="dashboard_error_live.png")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_admin_login())
