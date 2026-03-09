from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda err: print("PageError:", err))
        page.on("console", lambda msg: print("Console:", msg.text) if msg.type == "error" else None)
        page.goto("http://localhost:5000/admin")
        page.fill("input[type=password]", "noodleboxadmin!")
        
        # Click login using evaluate since the DOM might differ slightly
        page.evaluate("""
            const btns = Array.from(document.querySelectorAll('button'));
            const loginBtn = btns.find(b => b.innerText.includes('Login') || b.innerText.includes('登录'));
            if(loginBtn) loginBtn.click();
        """)
        
        page.wait_for_timeout(3000)
        browser.close()

if __name__ == "__main__":
    run()
