import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from plugins.lotteryNotify.base_stock_checker import BaseStockChecker
from bs4 import BeautifulSoup
import aiohttp

class RakutenSwitch2LotteryChecker(BaseStockChecker):
    MODULE_NAME = "rakuten_switch2_lottery"
    PRODUCTS = [
        {
            "url": "https://books.rakuten.co.jp/event/game/switch2/",
            "key": "switch2_lottery",
            "image_url": "https://image.books.rakuten.co.jp/books/img/bnr/event/game/switch2/img/main-switch2-bnr1.png"
        }
    ]
    Debug = False

    @staticmethod
    def parse_stock_status(html):
        soup = BeautifulSoup(html, "html.parser")
        end_div = soup.find("div", class_="end-txt")
        if end_div:
            return end_div.get_text(strip=True)
        return ""

    @staticmethod
    def parse_product_name(html):
        return "楽天ブックス Switch2 抽選受付状況"

    @staticmethod
    def parse_price(html):
        return ""

    @classmethod
    def custom_notification_message(cls, stock_status, product_name, price, prod, last_status=None):
        return {
            "title": f"楽天Switch2抽選ページ状況: {stock_status if stock_status else '受付中?'}",
            "description": f"{product_name} の抽選受付状況が変化しました！\n前回: {last_status if last_status is not None else '-'}\n今回: {stock_status if stock_status else '受付中?'}",
            "url": prod.get("url", ""),
            "prize": stock_status,
            "image_url": prod.get("image_url", "")
        }

# Baseクラスにパース関数をセット
RakutenSwitch2LotteryChecker.parse_stock_status = RakutenSwitch2LotteryChecker.parse_stock_status
RakutenSwitch2LotteryChecker.parse_product_name = RakutenSwitch2LotteryChecker.parse_product_name
RakutenSwitch2LotteryChecker.parse_price = RakutenSwitch2LotteryChecker.parse_price

async def check_lottery(use_custom_notification: bool = True):
    return await RakutenSwitch2LotteryChecker.check_lottery(use_custom_notification=use_custom_notification)

if __name__ == "__main__":
    RakutenSwitch2LotteryChecker.debug_run()
