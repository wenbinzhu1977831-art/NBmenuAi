import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  page.on('console', msg => {
    if (msg.type() === 'error') {
      console.log(`[Browser Error]: ${msg.text()}`);
    }
  });

  page.on('pageerror', exception => {
    console.log(`[Uncaught Exception]: ${exception}`);
  });

  await page.goto('http://127.0.0.1:5000/admin', { waitUntil: 'networkidle' });
  
  // Try to login
  await page.fill('input[type="password"]', 'noodleboxadmin!');
  await page.click('button:has-text("Login"), button:has-text("登录")');
  
  await page.waitForTimeout(3000);
  
  await browser.close();
})();
