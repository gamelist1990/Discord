import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from plugins.lotteryNotify.base_stock_checker import BaseStockChecker
from bs4 import BeautifulSoup

class YahooSwitch2MultiStockChecker(BaseStockChecker):
    MODULE_NAME = "yahoo_switch2_multi_stock"
    PRODUCTS = [
        {
            "url": "https://store.shopping.yahoo.co.jp/1932/83001.html",
            "key": "83001",
            "image_url": "https://item-shopping.c.yimg.jp/i/n/1932_83001_i_20250611181907"
        },
        {
            "url": "https://store.shopping.yahoo.co.jp/1932/83000.html",
            "key": "83000",
            "image_url": "https://item-shopping.c.yimg.jp/i/n/1932_83000_i_20250611181949"
        },
    ]
    Debug = False

    @staticmethod
    def parse_stock_status(html):
        soup = BeautifulSoup(html, "html.parser")
        label = soup.find("span", class_="Label Label--gray styles_label__qI5_r")
        if label:
            return label.get_text(strip=True)
        label2 = soup.find("span", class_="Label styles_label__qI5_r")
        if label2:
            return label2.get_text(strip=True)
        return ""

    @staticmethod
    def parse_product_name(html):
        soup = BeautifulSoup(html, "html.parser")
        name = soup.find("p", class_="styles_name__u228e")
        if name:
            return name.get_text(strip=True)
        return "Yahoo!商品"

    @staticmethod
    def parse_price(html):
        soup = BeautifulSoup(html, "html.parser")
        price = soup.find("p", class_="styles_price__CD3pM")
        if price:
            return price.get_text(strip=True)
        return ""

# Baseクラスにパース関数をセット
YahooSwitch2MultiStockChecker.parse_stock_status = YahooSwitch2MultiStockChecker.parse_stock_status
YahooSwitch2MultiStockChecker.parse_product_name = YahooSwitch2MultiStockChecker.parse_product_name
YahooSwitch2MultiStockChecker.parse_price = YahooSwitch2MultiStockChecker.parse_price

async def check_lottery():
    return await YahooSwitch2MultiStockChecker.check_lottery()

if __name__ == "__main__":
    YahooSwitch2MultiStockChecker.debug_run()
