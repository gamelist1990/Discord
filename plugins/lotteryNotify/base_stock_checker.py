import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict, Callable, Any, Optional

class BaseStockChecker:
    Debug = False
    MODULE_NAME = None
    PRODUCTS: List[Dict] = []
    # パース関数はサブクラスで上書き
    parse_stock_status: Optional[Callable[[str], str]] = None
    parse_product_name: Optional[Callable[[str], str]] = None
    parse_price: Optional[Callable[[str], str]] = None

    @classmethod
    async def fetch_html(cls, url):
        if cls.Debug:
            print(f"[DEBUG] Fetching: {url}")
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                text = await resp.text()
                if cls.Debug:
                    print(f"[DEBUG] Fetched {len(text)} bytes from {url}")
                return text

    @classmethod
    def custom_notification_message(cls, stock_status: str, product_name: str, price: str, prod: dict, last_status: Optional[str] = None) -> dict:
        # サブクラスでオーバーライド可能なカスタム通知メッセージ生成
        return {
            "title": product_name,
            "description": f"在庫状態が変化しました: {last_status} → {stock_status}",
            "url": prod["url"],
            "price": price,
            "prize": stock_status,
            "image_url": prod.get("image_url")
        }

    @classmethod
    async def check_lottery(cls, use_custom_notification: bool = False):
        from plugins.lotteryNotify.lottery_database import LotteryDatabase
        db = LotteryDatabase(cls.MODULE_NAME)
        notifications = []
        for prod in cls.PRODUCTS:
            if cls.Debug:
                print(f"[DEBUG] Checking product: {prod['key']}")
            html = await cls.fetch_html(prod["url"])
            if cls.parse_stock_status is None or cls.parse_product_name is None or cls.parse_price is None:
                raise NotImplementedError("パース関数(parse_stock_status, parse_product_name, parse_price)をサブクラスでセットしてください")
            stock_status = cls.parse_stock_status(html)
            product_name = cls.parse_product_name(html)
            price = cls.parse_price(html)
            last_status = db.get_state(f"stock_status_{prod['key']}")
            if cls.Debug:
                print(f"[DEBUG] {prod['key']} last_status={last_status}, now={stock_status}")
            if last_status is not None and stock_status != last_status:
                if use_custom_notification:
                    notification = cls.custom_notification_message(stock_status, product_name, price, prod, last_status)
                else:
                    notification = {
                        "title": product_name,
                        "description": f"在庫状態が変化しました: {last_status} → {stock_status}",
                        "url": prod["url"],
                        "price": price,
                        "prize": stock_status,
                        "image_url": prod.get("image_url")
                    }
                notifications.append(notification)
                if cls.Debug:
                    print(f"[DEBUG] Notification queued for {prod['key']}")
            db.save_state(f"stock_status_{prod['key']}", stock_status)
        return notifications

    @classmethod
    def debug_run(cls, use_custom_notification: bool = False):
        import sys, os, asyncio
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
        cls.Debug = True
        async def debug():
            notifications = await cls.check_lottery(use_custom_notification=use_custom_notification)
            for n in notifications:
                print(n)
        asyncio.run(debug())

# サブクラスで if __name__ == "__main__": BaseStockChecker.debug_run() でOK
