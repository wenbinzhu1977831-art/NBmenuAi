"""
删除 Twilio 账号中多余的 AIQueue。
运行: python scripts/cleanup_queues.py
"""
import httpx
import asyncio

ACCOUNT_SID = "AC64218d10e2020564bad5e31183504509"
AUTH_TOKEN  = "04832844e8841539fafd5649bb813cb0"

# 两个同名队列的 SID
KEEP_SID   = "QU685657bca4bdfd9848b63c66c13dcc94"   # 保留 (Enqueue 实际用的)
DELETE_SID = "QU8f14f15479af58ea0c1b4e35a520e098"   # 删除 (REST 查找出的错误副本)

async def main():
    if not AUTH_TOKEN:
        print("❌ 请先在脚本中填入 TWILIO_AUTH_TOKEN！")
        return

    base = f"https://api.twilio.com/2010-04-01/Accounts/{ACCOUNT_SID}"
    auth = (ACCOUNT_SID, AUTH_TOKEN)

    # 1. 列出所有队列
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{base}/Queues.json", auth=auth)
    
    if r.status_code != 200:
        print(f"❌ 获取队列失败 ({r.status_code}): {r.text}")
        return

    queues = r.json().get("queues", [])
    print(f"\n当前账号所有队列（共 {len(queues)} 个）：\n" + "-"*60)
    for q in queues:
        tag = "★ 保留" if q["sid"] == KEEP_SID else ("✗ 待删除" if q["sid"] == DELETE_SID else "")
        print(f"  [{tag:8}] {q['sid']}  名称: {q['friendly_name']}  队列中通话数: {q['current_size']}")
    print()

    # 2. 删除多余队列
    to_del = next((q for q in queues if q["sid"] == DELETE_SID), None)
    if not to_del:
        print("✅ 未找到需要删除的队列，可能已删除。")
        return

    if to_del["current_size"] > 0:
        print(f"⚠️ 队列 {DELETE_SID} 里有 {to_del['current_size']} 个活跃通话，无法删除！")
        return

    confirm = input(f"确认删除队列 {to_del['friendly_name']} ({DELETE_SID})？输入 'yes' 确认: ").strip()
    if confirm != "yes":
        print("已取消。")
        return

    async with httpx.AsyncClient() as client:
        r = await client.delete(f"{base}/Queues/{DELETE_SID}.json", auth=auth)

    if r.status_code == 204:
        print(f"\n✅ 队列 {DELETE_SID} 已成功删除！")
    else:
        print(f"\n❌ 删除失败 ({r.status_code}): {r.text}")

asyncio.run(main())
