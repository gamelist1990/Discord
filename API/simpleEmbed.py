"""
汎用的なEmbed用クラス。title, description, url, image, site_name などを指定してOGP埋め込みHTMLを生成できる。
"""

class SimpleEmbed:
    @property
    def description_with_stats_text(self) -> str:
        """
        Discord向け: descriptionの末尾にstatsをテキストで付与した文字列を返す
        """
        stats_text = ""
        if self.stats:
            icon_map = {
                'replies': '💬',
                'retweets': '🔁',
                'likes': '❤️',
                'views': '👁️',
                '👁️ 視聴数': '👁️',
                '👍 いいね': '👍',
            }
            shown = set()
            stats_parts = []
            for k in ['replies', 'retweets', 'likes', 'views', '👁️ 視聴数', '👍 いいね']:
                if k in self.stats and self.stats[k] not in (None, ""):
                    stats_parts.append(f"{icon_map.get(k, k)} {self.stats[k]}")
                    shown.add(k)
            for k, v in self.stats.items():
                if k not in shown and v not in (None, ""):
                    stats_parts.append(f"{k}: {v}")
            if stats_parts:
                stats_text = "\n" + " ".join(stats_parts)
        return (self.description or "") + stats_text
    def __init__(
        self,
        title: str,
        description: str = "",
        url: str = "",
        image: str = "",
        site_name: str = "EmbedAPI",
        author_name: str = "",
        author_icon: str = "",
        quoted_author: str = "",
        quoted_text: str = "",
        stats: 'dict | None' = None,
        footer: str = "",
        iframe: str = ""
    ):
        self.title = title
        self.description = description
        self.url = url
        self.image = image
        self.site_name = site_name
        self.author_name = author_name
        self.author_icon = author_icon
        self.quoted_author = quoted_author
        self.quoted_text = quoted_text
        self.stats = stats or {}
        self.footer = footer
        self.iframe = iframe
    def to_ogp_html(self) -> str:
        import re, html
        stats_html = ""
        if self.stats:
            icon_map = {
                'replies': '💬',
                'retweets': '🔁',
                'likes': '❤️',
                'views': '👁️',
                '👁️ 視聴数': '👁️',
                '👍 いいね': '👍',
            }
            shown = set()
            stats_parts = []
            for k in ['replies', 'retweets', 'likes', 'views', '👁️ 視聴数', '👍 いいね']:
                if k in self.stats and self.stats[k] not in (None, ""):
                    stats_parts.append(f"{icon_map.get(k, k)} {self.stats[k]}")
                    shown.add(k)
            for k, v in self.stats.items():
                if k not in shown and v not in (None, ""):
                    stats_parts.append(f"{k}: {v}")
            if stats_parts:
                stats_html = f"<div style='margin:8px 0;'>" + '　'.join(stats_parts) + "</div>"

        quoted_html = ""
        if self.quoted_author or self.quoted_text:
            quoted_html = (
                f"<blockquote style='border-left:4px solid #ccc;padding-left:8px;margin:8px 0;background:#23272a22;'>"
                f"<b>{self.quoted_author}</b><br>{self.quoted_text.replace('\n','<br>')}</blockquote>"
            )
        author_html = ""
        if self.author_name:
            author_html = (
                f"<div style='display:flex;align-items:center;margin-bottom:8px;'>"
                f"{f'<img src=\"{self.author_icon}\" style=\"width:32px;height:32px;border-radius:50%;margin-right:8px;\">' if self.author_icon else ''}"
                f"<b>{self.author_name}</b>"
                f"</div>"
            )
        description_with_stats = self.description.replace('\n','<br>') + stats_html
        media_html = ""
        og_video_tags = ""
        ogp_tags_from_youtube = ""
        # --- YouTube動画IDが指定された場合はYouTube OGPタグを直接取得して挿入 ---
        if self.iframe and not self.iframe.strip().startswith("<iframe"):
            video_id = self.iframe.strip()
            import requests
            try:
                yt_url = f"https://www.youtube.com/watch?v={video_id}"
                resp = requests.get(yt_url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    # OGPタグのみ抽出
                    ogp_tags = re.findall(r'<meta[^>]+property=["\']og:([a-zA-Z0-9:_-]+)["\'][^>]+>', resp.text)
                    # すべてのog:タグを抽出
                    ogp_tag_htmls = re.findall(r'(<meta[^>]+property=["\']og:[a-zA-Z0-9:_-]+["\'][^>]+>)', resp.text)
                    # og:video, og:video:url, og:video:secure_url, og:video:type, og:video:width, og:video:height, og:title, og:description, og:image など
                    ogp_tags_from_youtube = "\n".join(ogp_tag_htmls)
            except Exception as e:
                ogp_tags_from_youtube = f"<!-- OGP fetch error: {e} -->"
            # サムネイル画像はYouTube OGPタグに含まれるためimageは空に
            self.image = ""
        elif self.iframe and self.iframe.strip().startswith("<iframe"):
            media_html = f"{self.iframe}<br>"
        elif self.image:
            media_html = f"<img src='{self.image}' alt='thumbnail' style='max-width:100%;border-radius:8px;'><br>"
        return f"""
        <!DOCTYPE html>
        <html lang='ja'>
        <head>
            <meta charset='utf-8'>
            <meta property='og:type' content='website'>
            <meta property='og:site_name' content='{self.site_name}'>
            <meta property='og:title' content='{self.title or self.author_name}'>
            <meta property='og:description' content='{self.description}'>
            <meta property='og:url' content='{self.url}'>
            {f"<meta property='og:image' content='{self.image}'>" if self.image else ''}
            {ogp_tags_from_youtube}
            <meta name='twitter:card' content='summary_large_image'>
            <meta name='twitter:title' content='{self.title or self.author_name}'>
            <meta name='twitter:description' content='{self.description}'>
            {f"<meta name='twitter:image' content='{self.image}'>" if self.image else ''}
            <title>{self.title or self.author_name}</title>
        </head>
        <body style='font-family:sans-serif;background:#23272a;color:#fff;padding:16px;max-width:480px;'>
            {author_html}
            <div style='margin-bottom:8px;'>{description_with_stats}</div>
            {quoted_html}
            {media_html}
            <div style='color:#aaa;font-size:12px;margin-top:8px;'>{self.footer}</div>
        </body>
        </html>
        """
