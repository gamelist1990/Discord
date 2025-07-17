"""
YouTube RSS API Utility (Python版)

TypeScript版(index.ts)と完全にAPI・仕様・使い方を統一したPython実装。
- YouTube Data APIは使わず、RSSとHTMLのみで動作
- 動画タイプ(shorts, normal, live, liveContents)・ライブ状態(live, ended, none, etc.)を正確に判定
- 強力な型定義(型ヒント/Enum)
- 直感的なAPI設計・拡張性
- サムネイル・チャンネル画像取得、デバッグ出力も完全再現

【インストール】
- 必要パッケージ: requests, feedparser, beautifulsoup4
  pip install requests feedparser beautifulsoup4

【使い方例】
from youtube.index import YoutubeRssApi, YoutubeLiveStatus, YoutubeVideoType

api = YoutubeRssApi(debug_mode=True)
channel_id = api.extract_channel_id('https://www.youtube.com/@GoogleJapan')
print('Channel ID:', channel_id)
name = api.get_channel_name(channel_id)
print('Channel Name:', name)
videos = api.get_latest_videos(channel_id)
for v in videos:
    print(v)

# 詳細取得
video_detail = api.get_video_detail(videos[0].video_id)
print(video_detail)

# チャンネル画像
owner_img = api.get_channel_owner_image(channel_id)
print(owner_img)

# バージョン
print(YoutubeRssApi.version)

【API仕様】
- YoutubeLiveStatus: Enum('none', 'upcoming', 'live', 'ended')
- YoutubeVideoType: Enum('normal', 'shorts', 'liveContents', 'isLive', 'unknown')
- YoutubeVideoInfo: video_id, title, author, published, url, live_status, type
- YoutubeVideoDetail: (上記+description, thumbnails, image_url)
- YoutubeRssApi: extract_channel_id, get_channel_name, get_latest_videos, get_video_detail, get_channel_owner_image, get_latest_videos_with_details, version

"""

import re
import requests
import feedparser
from enum import Enum
from typing import List, Optional, Dict, Any

class YoutubeLiveStatus(str, Enum):
    NONE = 'none'
    UPCOMING = 'upcoming'
    LIVE = 'live'
    ENDED = 'ended'

class YoutubeVideoType(str, Enum):
    NORMAL = 'normal'
    SHORTS = 'shorts'
    LIVECONTENTS = 'liveContents'
    ISLIVE = 'isLive'
    UNKNOWN = 'unknown'

class YoutubeVideoInfo:
    def __init__(self, video_id: str, title: str, author: str, published: str, url: str,
                 live_status: Optional[YoutubeLiveStatus] = None,
                 type: Optional[YoutubeVideoType] = None):
        self.video_id = video_id
        self.title = title
        self.author = author
        self.published = published
        self.url = url
        self.live_status = live_status
        self.type = type
    def __repr__(self):
        return f"<YoutubeVideoInfo {self.video_id} {self.title} {self.type} {self.live_status}>"

class YoutubeVideoDetail(YoutubeVideoInfo):
    def __init__(self, video_id: str, title: str, author: str, published: str, url: str,
                 description: Optional[str] = None, thumbnails: Optional[List[str]] = None,
                 image_url: Optional[str] = None, live_status: Optional[YoutubeLiveStatus] = None,
                 type: Optional[YoutubeVideoType] = None,
                 view_count: Optional[int] = None, like_count: Optional[int] = None):
        super().__init__(video_id, title, author, published, url, live_status, type)
        self.description = description
        self.thumbnails = thumbnails or []
        self.image_url = image_url
        self.view_count = view_count
        self.like_count = like_count
    def __repr__(self):
        return f"<YoutubeVideoDetail {self.video_id} {self.title} {self.type} {self.live_status} {self.image_url}>"

class YoutubeRssApi:
    version = '1.0.0'
    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode

    def extract_channel_id(self, url: str) -> Optional[str]:
        patterns = [
            r"youtube\.com\/channel\/([a-zA-Z0-9_-]+)",
            r"youtube\.com\/c\/([a-zA-Z0-9_-]+)",
            r"youtube\.com\/user\/([a-zA-Z0-9_-]+)",
            r"youtube\.com\/@([a-zA-Z0-9_-]+)",
        ]
        for pat in patterns:
            m = re.search(pat, url)
            if m:
                if m.group(1).startswith('UC'):
                    return m.group(1)
                return self.extract_channel_id_from_html(url)
        return None

    def extract_channel_id_from_html(self, url: str) -> Optional[str]:
        try:
            res = requests.get(url, timeout=10)
            if not res.ok:
                return None
            html = res.text
            m1 = re.search(r'"channelId":"(UC[^"]+)"', html)
            if m1:
                return m1.group(1)
            m2 = re.search(r'<meta property="og:url" content="https://www.youtube.com/channel/(UC[^"]+)">', html)
            if m2:
                return m2.group(1)
        except Exception:
            pass
        return None

    def get_channel_name(self, channel_id: str) -> Optional[str]:
        feed_url = f'https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}'
        try:
            feed = feedparser.parse(feed_url)
            title = getattr(feed.feed, 'title', None)
            if isinstance(title, list):
                title = title[0] if title else None
            if title is not None and not isinstance(title, str):
                title = str(title)
            return title
        except Exception:
            return None

    def get_latest_videos(self, channel_id: str) -> Optional[List[YoutubeVideoInfo]]:
        feed_url = f'https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}'
        try:
            feed = feedparser.parse(feed_url)
            videos = []
            for entry in feed.entries:
                video_id = getattr(entry, 'yt_videoid', '')
                if isinstance(video_id, list):
                    video_id = video_id[0] if video_id else ''
                if not isinstance(video_id, str):
                    video_id = str(video_id)
                title = getattr(entry, 'title', '')
                if isinstance(title, list):
                    title = title[0] if title else ''
                if not isinstance(title, str):
                    title = str(title)
                author = getattr(entry, 'author', '')
                if isinstance(author, list):
                    author = author[0] if author else ''
                if not isinstance(author, str):
                    author = str(author)
                published = getattr(entry, 'published', '')
                if isinstance(published, list):
                    published = published[0] if published else ''
                if not isinstance(published, str):
                    published = str(published)
                url = getattr(entry, 'link', '')
                if isinstance(url, list):
                    url = url[0] if url else ''
                if not isinstance(url, str):
                    url = str(url)
                type_ = YoutubeVideoType.SHORTS if '/shorts/' in url else YoutubeVideoType.NORMAL
                videos.append(YoutubeVideoInfo(
                    video_id=video_id,
                    title=title,
                    author=author,
                    published=published,
                    url=url,
                    type=type_,
                ))
            return videos
        except Exception:
            return None

    def get_live_status(self, video_id: str) -> YoutubeLiveStatus:
        video_url = f'https://www.youtube.com/watch?v={video_id}'
        try:
            res = requests.get(video_url, timeout=10)
            if not res.ok:
                return YoutubeLiveStatus.NONE
            content = res.text
            if '"isLive":true' in content or '"liveBroadcastContent":"live"' in content:
                return YoutubeLiveStatus.LIVE
            if '"liveBroadcastContent":"upcoming"' in content or '"isUpcoming":true' in content:
                return YoutubeLiveStatus.UPCOMING
            if '"ended":true' in content:
                return YoutubeLiveStatus.ENDED
            return YoutubeLiveStatus.NONE
        except Exception:
            return YoutubeLiveStatus.NONE

    def get_latest_video_info(self, channel_id: str) -> Optional[YoutubeVideoInfo]:
        videos = self.get_latest_videos(channel_id)
        if not videos:
            return None
        latest = videos[0]
        status = self.get_live_status(latest.video_id)
        latest.live_status = status
        return latest

    def get_videos_with_paging(self, channel_id: str, page: int = 1, page_size: int = 10) -> Optional[Dict[str, Any]]:
        videos = self.get_latest_videos(channel_id)
        if not videos:
            return None
        total = len(videos)
        start = (page - 1) * page_size
        end = start + page_size
        return {
            'videos': videos[start:end],
            'page': page,
            'page_size': page_size,
            'total': total,
        }

    def get_video_detail(self, video_id: str) -> Optional[YoutubeVideoDetail]:
        url = f'https://www.youtube.com/watch?v={video_id}'
        try:
            res = requests.get(url, timeout=10)
            if not res.ok:
                return None
            html = res.text
            title = re.search(r'<title>(.*?)</title>', html)
            title = title.group(1).replace(' - YouTube', '') if title else ''
            author = re.search(r'"author":"([^"]+)"', html)
            author = author.group(1) if author else ''
            description = re.search(r'"shortDescription":"([^"]+)"', html)
            description = description.group(1).replace('\\n', '\n') if description else ''
            thumbnails = [m.replace('\\/', '/') for m in re.findall(r'"thumbnailUrl":"(https://i\.ytimg\.com[^"]+)"', html)]
            image_url = thumbnails[0] if thumbnails else f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg'
            # --- BeautifulSoup方式は廃止。正規表現・JSON断片のみで検知 ---
            # 視聴数（日本語表記）
            view_count_text = None
            m_simple_view = re.search(r'"viewCount":\{"videoViewCountRenderer":\{"viewCount":\{"simpleText":"([\d,]+ 回視聴)"', html)
            if m_simple_view:
                view_count_text = m_simple_view.group(1)
            # fallback: 旧正規表現
            if not view_count_text:
                m_view_text = re.search(r'<span[^>]*class="[^"]*bold[^"]*"[^>]*>([\d,]+) 回視聴<', html)
                if m_view_text:
                    view_count_text = m_view_text.group(1) + " 回視聴"

            # 投稿日時（metaタグ優先: 正規表現でmetaタグ抽出）
            published = ''
            m_meta_upload = re.search(r'<meta[^>]+itemprop=["\']uploadDate["\'][^>]+content=["\']([^"\']+)["\']', html)
            if m_meta_upload:
                published = m_meta_upload.group(1)
            # fallback: 旧正規表現
            if not published:
                m_pub = re.search(r'"dateText":\{"simpleText":"([^"]+)"\}', html)
                if m_pub:
                    published = m_pub.group(1)
            # 視聴数（数値）
            view_count = None
            m_view = re.search(r'"viewCount":"(\d+)"', html)
            if m_view:
                try:
                    view_count = int(m_view.group(1))
                except Exception:
                    view_count = None
            # いいね数（likeCountのみ検知＋metaタグも対応）
            like_count_text = None
            m_like_json = re.search(r'likeCount":"(\d+)"', html)
            if m_like_json:
                like_count_text = m_like_json.group(1)
            # metaタグ fallback
            if not like_count_text:
                m_like_meta = re.search(r'<meta[^>]+itemprop=["\']userInteractionCount["\'][^>]+content=["\'](\d+)["\']', html)
                if m_like_meta:
                    like_count_text = m_like_meta.group(1)
            if self.debug_mode:
                print(f'[DEBUG] like_count_text (likeCount/meta): {like_count_text}')
            # いいね数（数値）
            like_count = None
            if like_count_text:
                try:
                    like_count = int(like_count_text.replace(',', ''))
                except Exception:
                    like_count = None
            # 投稿日時
            published = ''
            m_pub = re.search(r'"dateText":\{"simpleText":"([^"]+)"\}', html)
            if m_pub:
                published = m_pub.group(1)
            # Shorts判定
            is_shorts = False
            if '/shorts/' in url or re.search(r'"canonicalUrl":"https://www.youtube.com/shorts/', html):
                is_shorts = True
            if not is_shorts and re.search(r'"shortsUrl":"https://www.youtube.com/shorts/', html):
                is_shorts = True
            # ライブ判定
            is_live_content = None
            m_live_content = re.search(r'"isLiveContent"\s*:\s*(true|false)', html)
            if m_live_content:
                is_live_content = m_live_content.group(1) == 'true'
            if self.debug_mode:
                print('[DEBUG] isLiveContent:', is_live_content)
            live_broadcast_details = {}
            m_live_broadcast = re.search(r'"liveBroadcastDetails"\s*:\s*\{([^}]*)\}', html)
            if m_live_broadcast:
                fragment = '{' + m_live_broadcast.group(1) + '}'
                try:
                    is_live_now = re.search(r'"isLiveNow"\s*:\s*(true|false)', fragment)
                    start_timestamp = re.search(r'"startTimestamp"\s*:\s*"([^"]+)"', fragment)
                    end_timestamp = re.search(r'"endTimestamp"\s*:\s*"([^"]+)"', fragment)
                    live_broadcast_details = {
                        'isLiveNow': is_live_now.group(1) == 'true' if is_live_now else None,
                        'startTimestamp': start_timestamp.group(1) if start_timestamp else None,
                        'endTimestamp': end_timestamp.group(1) if end_timestamp else None,
                    }
                except Exception:
                    pass
            if self.debug_mode:
                print('[DEBUG] liveBroadcastDetails:', live_broadcast_details)
            # type判定
            type_ = YoutubeVideoType.UNKNOWN
            if is_shorts:
                type_ = YoutubeVideoType.SHORTS
            elif is_live_content is True:
                if live_broadcast_details.get('isLiveNow') is True:
                    type_ = YoutubeVideoType.ISLIVE
                else:
                    type_ = YoutubeVideoType.LIVECONTENTS
            elif is_live_content is False:
                type_ = YoutubeVideoType.NORMAL
            elif m_live_broadcast:
                if live_broadcast_details.get('isLiveNow') is True:
                    type_ = YoutubeVideoType.ISLIVE
                else:
                    type_ = YoutubeVideoType.LIVECONTENTS
            else:
                if (title and re.search(r'ライブ|配信|生放送|live', title, re.I)) or (description and re.search(r'ライブ|配信|生放送|live', description, re.I)):
                    type_ = YoutubeVideoType.LIVECONTENTS
                else:
                    type_ = YoutubeVideoType.NORMAL
            if self.debug_mode:
                print('[DEBUG] type:', type_)
            # liveStatus
            live_status = None
            if live_broadcast_details.get('isLiveNow') is True:
                live_status = YoutubeLiveStatus.LIVE
            elif live_broadcast_details.get('isLiveNow') is False:
                if live_broadcast_details.get('endTimestamp'):
                    live_status = YoutubeLiveStatus.ENDED
                else:
                    live_status = YoutubeLiveStatus.UPCOMING
            elif type_ == YoutubeVideoType.LIVECONTENTS:
                live_status = YoutubeLiveStatus.UPCOMING
            if live_status is None:
                live_status = YoutubeLiveStatus.NONE
            if self.debug_mode:
                print('[DEBUG] liveStatus:', live_status)
            return YoutubeVideoDetail(
                video_id=video_id,
                title=title,
                author=author,
                published=published,
                url=url,
                description=description,
                thumbnails=thumbnails,
                image_url=image_url,
                type=type_,
                live_status=live_status,
                view_count=view_count,
                like_count=like_count,
            )
        except Exception as e:
            if self.debug_mode:
                print('[DEBUG] get_video_detail error:', e)
            return None

    def get_channel_owner_image(self, channel_id: str) -> Optional[str]:
        url = f'https://www.youtube.com/channel/{channel_id}'
        try:
            res = requests.get(url, timeout=10)
            if not res.ok:
                return None
            html = res.text
            m = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            if m:
                return m.group(1)
        except Exception:
            pass
        return None

    def get_latest_videos_with_details(self, channel_id: str, concurrency: int = 3) -> List[YoutubeVideoDetail]:
        videos = self.get_latest_videos(channel_id)
        if not videos:
            return []
        results = []
        for i in range(0, len(videos), concurrency):
            chunk = videos[i:i+concurrency]
            details = [self.get_video_detail(v.video_id) for v in chunk]
            for d in details:
                if d:
                    results.append(d)
                    if self.debug_mode:
                        print('[DETAIL]', d.video_id, d.title, d.type, d.live_status)
        return results
