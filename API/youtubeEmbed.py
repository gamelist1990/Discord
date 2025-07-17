"""
YouTube埋め込み用の簡易クラス
https://url/youtube/VideoID でYouTube動画の埋め込み情報を返す
"""

import re

from API.simpleEmbed import SimpleEmbed


class YoutubeEmbed:
    @staticmethod
    def _format_count(num) -> str:
        try:
            n = int(str(num).replace(",", "").replace(" 回視聴", "").replace(" ", ""))
        except Exception:
            return str(num)
        if n >= 1_000_000_000:
            return f"{n/1_000_000_000:.1f}B"
        elif n >= 1_000_000:
            return f"{n/1_000_000:.1f}M"
        elif n >= 1_000:
            return f"{n/1_000:.1f}K"
        else:
            return str(n)
    @classmethod
    def get_ogp_html(
        cls,
        video_id: str,
        user_agent: "str | None" = None,
        title: str = "",
        description: str = "",
        author_name: str = "YouTube",
        author_icon: str = "https://www.youtube.com/s/desktop/6e8e7e2d/img/favicon_144x144.png",
        footer: str = "",
        views: str = "",
        published: str = "",
        likes: str = "",
    ) -> str:
        """
        Discord等のクローラーやbot向けにYouTube動画の埋め込み情報をHTMLで返す（OGP/Embed用・SimpleEmbed利用）
        """
        print(
            f"[YouTubeEmbed][DEBUG] get_ogp_html called: video_id={video_id}, title={title}, description={description}, author_name={author_name}, views={views}, likes={likes}, published={published}"
        )
        if not cls.is_valid_video_id(video_id):
            print(f"[YouTubeEmbed][DEBUG] Invalid video_id: {video_id}")
            return "<html><head><meta name='robots' content='noindex'></head><body>Invalid YouTube Video ID</body></html>"
        url = cls.YOUTUBE_URL.format(video_id=video_id)
        embed_url = cls.YOUTUBE_EMBED_URL.format(video_id=video_id)
        thumb_url = cls.YOUTUBE_THUMB_URL.format(video_id=video_id)
        # 必ず最初にRSSから取得
        try:
            from lib.youtubeRSS import YoutubeRssApi
            api = YoutubeRssApi()
            detail = api.get_video_detail(video_id)
            print(f"[YouTubeEmbed][DEBUG] RSS detail: {detail!r}")
            if detail:
                for k in dir(detail):
                    if not k.startswith("__"):
                        print(f"[YouTubeEmbed][DEBUG] detail.{k} = {getattr(detail, k)}")
        except Exception as e:
            print(f"[YouTubeEmbed][DEBUG] RSS取得失敗: {e}")
            import traceback
            traceback.print_exc()
            detail = None

        # detailから全ての情報を優先的にセット
        if detail:
            title = getattr(detail, "title", title) or title or author_name or "YouTube"
            description = getattr(detail, "description", description) or description or ""
            author_name = getattr(detail, "author", author_name) or author_name or "YouTube"
            # サムネイル
            thumb_url = getattr(detail, "image_url", thumb_url) or thumb_url
            # 視聴数
            if hasattr(detail, "view_count_text") and getattr(detail, "view_count_text", None):
                views = getattr(detail, "view_count_text")
            elif hasattr(detail, "view_count") and getattr(detail, "view_count", None):
                views = f"{getattr(detail, 'view_count'):,} 回視聴"
            # いいね数（like_count_text優先、なければlike_count、どちらもなければ'-'）
            if hasattr(detail, "like_count_text") and getattr(detail, "like_count_text", None):
                likes = getattr(detail, "like_count_text")
            elif hasattr(detail, "like_count") and getattr(detail, "like_count", None):
                likes = f"{getattr(detail, 'like_count'):,}"
            else:
                likes = "-"
            # 投稿日時
            if hasattr(detail, "published") and getattr(detail, "published", None):
                published = getattr(detail, "published")

        # descriptionを50文字に制限
        if description and isinstance(description, str):
            description = description.strip()
            if len(description) > 100:
                description = description[:100] + "..."
        if user_agent:
            print(f"[YouTubeEmbed][DEBUG] User-Agent: {user_agent}")
        print(f"[YouTubeEmbed][DEBUG] OGP HTML requested for video_id={video_id} (url={url})")
        # stats: 視聴数・いいね数（多国籍対応: 英語表記も併記）
        stats = {}
        if views:
            views_en = cls._format_count(views)
            stats["👁️ Views"] = f"{views_en} views"
        if likes:
            likes_en = cls._format_count(likes)
            stats["👍 Likes"] = f"{likes_en} likes"
        print(f"[YouTubeEmbed][DEBUG] stats dict: {stats}")
        # フッターに投稿日時を追加
        footer_text = footer
        if published:
            if footer_text:
                footer_text += " ・ "
            footer_text += f"{published}"
        # 著者アイコンは動画のサムネイルを使用
        author_icon_final = thumb_url
        # SimpleEmbedのiframe引数にYouTube動画IDを直接渡す
        embed = SimpleEmbed(
            title=title,
            description=description,
            url=url,
            image="",  
            iframe=video_id,  # 動画IDのみ渡す
            site_name="YouTube",
            author_name=author_name,
            author_icon=author_icon_final,
            stats=stats,
            footer=footer_text,
        )
        # description_with_stats_textをdescriptionとしてHTML生成
        embed.description = embed.description_with_stats_text
        print(f"[YouTubeEmbed][DEBUG] SimpleEmbed.stats: {embed.stats}")
        html = embed.to_ogp_html()
        return html

    YOUTUBE_URL = "https://www.youtube.com/watch?v={video_id}"
    YOUTUBE_EMBED_URL = "https://www.youtube.com/embed/{video_id}"
    YOUTUBE_THUMB_URL = "https://img.youtube.com/vi/{video_id}/hqdefault.jpg"

    @staticmethod
    def is_valid_video_id(video_id: str) -> bool:
        return bool(re.match(r"^[\w-]{11}$", video_id))

    @classmethod
    def get_embed_info(cls, video_id: str) -> dict:
        if not cls.is_valid_video_id(video_id):
            return {"success": False, "error": "Invalid YouTube Video ID"}
        return {
            "success": True,
            "video_id": video_id,
            "url": cls.YOUTUBE_URL.format(video_id=video_id),
            "embed_url": cls.YOUTUBE_EMBED_URL.format(video_id=video_id),
            "thumbnail_url": cls.YOUTUBE_THUMB_URL.format(video_id=video_id),
        }
