"""
dショッピング Nintendo Switch2 在庫監視モジュール
Nintendo Switch2の在庫を監視して、新しい商品が見つかったら通知する
"""

from bs4 import BeautifulSoup, Tag
from datetime import datetime
from typing import List, Dict, Optional
import aiohttp
import sys, os

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
)
from plugins.lotteryNotify.base_stock_checker import BaseStockChecker


class DShoppingSwitch2Checker(BaseStockChecker):
    MODULE_NAME = "dshopping_switch2"
    PRODUCTS = [
        {
            "url": "https://dshopping.docomo.ne.jp/products_search?category_uri=1812000000%2F1812005000%2F1812005002&min_price=15000&genre_code=18",
            "key": "switch2_search",
            "image_url": None,  # 商品ごとに取得
        }
    ]
    Debug = False

    SEARCH_KEYWORDS = ["Nintendo Switch2", "Switch2"]

    @staticmethod
    def parse_stock_status(html: str) -> str:
        # 商品リストページから在庫あり商品数を返す（なければ"在庫なし"）
        soup = BeautifulSoup(html, "html.parser")
        search_container = soup.find(
            "div", {"id": "search-item-list", "class": "item-list"}
        )
        if not (search_container and isinstance(search_container, Tag)):
            return "在庫なし"
        item_divs = search_container.find_all("div", class_="item")
        count = 0
        for item_div in item_divs:
            product = DShoppingSwitch2Checker.parse_product_item(item_div)
            if product and DShoppingSwitch2Checker.is_target_product(product):
                count += 1
        return f"{count}件在庫あり" if count > 0 else "在庫なし"

    @staticmethod
    def parse_product_name(html: str) -> str:
        # 商品リストページなので固定名
        return "dショッピング Nintendo Switch2 検索結果"

    @staticmethod
    def parse_price(html: str) -> str:
        # 最安値を返す（なければ空）
        soup = BeautifulSoup(html, "html.parser")
        search_container = soup.find(
            "div", {"id": "search-item-list", "class": "item-list"}
        )
        if not (search_container and isinstance(search_container, Tag)):
            return ""
        item_divs = search_container.find_all("div", class_="item")
        prices = []
        for item_div in item_divs:
            product = DShoppingSwitch2Checker.parse_product_item(item_div)
            if product and DShoppingSwitch2Checker.is_target_product(product):
                try:
                    price = int(
                        product.get("price", "0").replace(",", "").replace("円", "")
                    )
                    prices.append(price)
                except Exception:
                    continue
        return f"{min(prices)}円~" if prices else ""

    @staticmethod
    def parse_product_item(item_div) -> Optional[Dict]:
        try:
            if not hasattr(item_div, "find"):
                return None
            link_elem = item_div.find("a")
            if not link_elem:
                return None
            href = link_elem.get("href", "")
            sku = link_elem.get("s", "")
            name_elem = item_div.find("p", class_="name-list")
            title = (
                name_elem.get_text(strip=True)
                if name_elem and hasattr(name_elem, "get_text")
                else "Unknown"
            )
            price_elem = item_div.find("div", class_="product-price")
            price = "0"
            if price_elem and hasattr(price_elem, "find"):
                price_font = price_elem.find("font")
                if price_font and hasattr(price_font, "get_text"):
                    price = price_font.get_text(strip=True)
            partner_elem = item_div.find("p", class_="partner-name")
            shop = (
                partner_elem.get_text(strip=True)
                if partner_elem and hasattr(partner_elem, "get_text")
                else "Unknown"
            )
            img_elem = item_div.find("img")
            image_url = img_elem.get("src", "") if img_elem else ""
            tags = []
            if hasattr(item_div, "find_all"):
                tag_elems = item_div.find_all("li", class_="tag")
                for tag_elem in tag_elems:
                    if hasattr(tag_elem, "get_text"):
                        tag_text = tag_elem.get_text(strip=True)
                        if tag_text:
                            tags.append(tag_text)
            product = {
                "id": sku or href,
                "title": title,
                "price": price,
                "shop": shop,
                "url": (
                    f"https://dshopping.docomo.ne.jp{href}"
                    if href.startswith("/")
                    else href
                ),
                "image_url": image_url,
                "tags": tags,
                "timestamp": datetime.now(),
            }
            return product
        except Exception as e:
            if DShoppingSwitch2Checker.Debug:
                print(f"[dshopping_switch2] 商品パースエラー: {e}")
            return None

    @staticmethod
    def is_target_product(product: Dict) -> bool:
        title = product.get("title", "").lower()
        for keyword in DShoppingSwitch2Checker.SEARCH_KEYWORDS:
            if keyword.lower() in title:
                return True
        return False

    @classmethod
    def custom_notification_message(
        cls,
        stock_status: str,
        product_name: str,
        price: str,
        prod: dict,
        last_status: Optional[str] = None,
    ) -> dict:
        # カスタム通知メッセージを生成（必要に応じてprodや他情報を利用）
        # stock_status, product_name, price, prod(dict), last_statusを使って柔軟に通知内容を作成
        return {
            "title": f"🎮 Nintendo Switch2 在庫状況: {stock_status}",
            "description": f'{product_name} の在庫状況が更新されました！\n前回: {last_status if last_status is not None else "-"} → 今回: {stock_status}',
            "url": prod.get("url", ""),
            "price": price,
            "prize": stock_status,
            "image_url": prod.get("image_url", ""),
            # 追加情報もここで付与可能
        }

    @classmethod
    async def check_lottery(cls, use_custom_notification: bool = True):
        from plugins.lotteryNotify.lottery_database import LotteryDatabase

        db = LotteryDatabase(cls.MODULE_NAME)
        notifications = []
        for prod in cls.PRODUCTS:
            if cls.Debug:
                print(f"[DEBUG] Checking product: {prod['key']}")
            html = await cls.fetch_html(prod["url"])
            if (
                cls.parse_stock_status is None
                or cls.parse_product_name is None
                or cls.parse_price is None
            ):
                raise NotImplementedError(
                    "パース関数(parse_stock_status, parse_product_name, parse_price)をサブクラスでセットしてください"
                )
            stock_status = cls.parse_stock_status(html)
            product_name = cls.parse_product_name(html)
            price = cls.parse_price(html)
            last_status = db.get_state(f"stock_status_{prod['key']}")
            if cls.Debug:
                print(
                    f"[DEBUG] {prod['key']} last_status={last_status}, now={stock_status}"
                )
            if last_status is not None and stock_status != last_status:
                if use_custom_notification:
                    notification = cls.custom_notification_message(
                        stock_status, product_name, price, prod, last_status
                    )
                else:
                    notification = {
                        "title": product_name,
                        "description": f"在庫状態が変化しました: {last_status} → {stock_status}",
                        "url": prod["url"],
                        "price": price,
                        "prize": stock_status,
                        "image_url": prod.get("image_url"),
                    }
                notifications.append(notification)
                if cls.Debug:
                    print(f"[DEBUG] Notification queued for {prod['key']}")
            db.save_state(f"stock_status_{prod['key']}", stock_status)
        return notifications


# Baseクラスにパース関数をセット
DShoppingSwitch2Checker.parse_stock_status = DShoppingSwitch2Checker.parse_stock_status
DShoppingSwitch2Checker.parse_product_name = DShoppingSwitch2Checker.parse_product_name
DShoppingSwitch2Checker.parse_price = DShoppingSwitch2Checker.parse_price


async def check_lottery(use_custom_notification: bool = True):
    return await DShoppingSwitch2Checker.check_lottery(
        use_custom_notification=use_custom_notification
    )


if __name__ == "__main__":
    DShoppingSwitch2Checker.debug_run()
