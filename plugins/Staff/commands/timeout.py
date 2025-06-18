from discord.ext import commands
import discord
from plugins.Staff.util import StaffUtil
from plugins.common_ui import ModalInputView
from DataBase import update_guild_data, get_guild_data
import datetime

@commands.command(name="timeout")
async def timeout_cmd(ctx, member_or_id, seconds_str, *, reason=None):
    util = StaffUtil(ctx)
    role = util.get_staff_role()
    if not role:
        await ctx.send("スタッフロールが設定されていません。"); return
    member = member_or_id
    try:
        if isinstance(member_or_id, str) and member_or_id.isdigit():
            member = await ctx.guild.fetch_member(int(member_or_id))
        elif (
            isinstance(member_or_id, str)
            and member_or_id.startswith("<@")
            and member_or_id.endswith(">")
        ):
            import re
            mention_match = re.match(r"<@!?(\d+)>", member_or_id)
            if mention_match:
                user_id = int(mention_match.group(1))
                member = await ctx.guild.fetch_member(user_id)
            else:
                await ctx.send(f"無効なメンション形式です: {member_or_id}"); return
    except discord.NotFound:
        await ctx.send(f"ID: {member_or_id} のユーザーが見つかりません。"); return
    except Exception as e:
        await ctx.send(f"エラーが発生しました: {str(e)}"); return
    if not isinstance(member, discord.Member):
        await ctx.send(f"無効なユーザーです。メンションまたはIDで指定してください。"); return
    if role in member.roles:
        await ctx.send(f"{member.mention} はスタッフロールを持っているためタイムアウトできません。"); return
    if member.bot:
        await ctx.send("Botにはタイムアウトできません。"); return
    try:
        seconds = StaffUtil.parse_timestr(seconds_str)
    except Exception as e:
        await ctx.send(f"時間指定が不正です: {e}"); return
    # Discordの仕様: 60秒未満や28日(2419200秒)超はエラー
    if seconds < 60:
        await ctx.send("タイムアウトは60秒以上で指定してください。"); return
    if seconds > 28*24*60*60:
        await ctx.send("タイムアウトは最大28日(2419200秒)までです。"); return
    until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)
    try:
        timeout_reason = (
            f"スタッフによるタイムアウト: {reason}" if reason else "スタッフによるタイムアウト"
        )
        try:
            await member.edit(timed_out_until=until, reason=timeout_reason)
        except discord.Forbidden:
            await ctx.send(f"⚠️ 権限不足のためタイムアウトできませんでした。Botの権限を確認してください。"); return
        except discord.HTTPException as http_e:
            await ctx.send(f"⚠️ Discordサーバーエラー: {http_e}"); return
        except Exception as other_e:
            await ctx.send(f"⚠️ 予期せぬエラー: {other_e}"); return
        embed = discord.Embed(
            title="タイムアウト通知",
            description=f"{member.mention} に {seconds}秒のタイムアウトを付与しました。",
            color=0xF1C40F,
        )
        embed.set_author(
            name=f"{ctx.author.display_name}",
            icon_url=ctx.author.display_avatar.url,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="期間", value=f"{seconds}秒", inline=True)
        embed.add_field(
            name="終了時刻", value=f"<t:{int(until.timestamp())}:F>", inline=True
        )
        if reason:
            embed.add_field(name="理由", value=reason, inline=False)
        embed.timestamp = datetime.datetime.now()
        await ctx.send(embed=embed)
        await util.send_staff_alert(None, embed=embed)
        
        async def validate_hansei_text(text: str) -> tuple[bool, str]:
            """反省文の品質をチェックする関数"""
            import re
            
            # 基本チェック：空白のみや極端に短い文字列
            clean_text = text.strip()
            if not clean_text:
                return False, "❌ 空白のみの反省文は受け付けられません。"
            
            # 連続する同じ文字のチェック（5文字以上）
            if re.search(r'(.)\1{4,}', text):
                return False, "❌ 同じ文字を5回以上連続して使用することはできません。"
            
            # 繰り返しパターンのチェック（2-3文字のパターンが5回以上）
            for pattern_length in [2, 3]:
                for i in range(len(text) - pattern_length + 1):
                    pattern = text[i:i + pattern_length]
                    if len(pattern.strip()) > 0:
                        count = 1
                        pos = i + pattern_length
                        while pos <= len(text) - pattern_length:
                            if text[pos:pos + pattern_length] == pattern:
                                count += 1
                                pos += pattern_length
                            else:
                                break
                        if count >= 5:
                            return False, f"❌ 同じパターン「{pattern}」の繰り返しが多すぎます。"
            
            # 文字種の多様性チェック
            hiragana_count = len(re.findall(r'[ひらがな]', text))
            katakana_count = len(re.findall(r'[カタカナ]', text))
            kanji_count = len(re.findall(r'[一-龯]', text))
            alpha_count = len(re.findall(r'[a-zA-Z]', text))
            number_count = len(re.findall(r'[0-9]', text))
            
            # 数字や記号だけの文字列チェック
            meaningful_chars = hiragana_count + katakana_count + kanji_count + alpha_count
            if meaningful_chars < len(clean_text) * 0.7:
                return False, "❌ 数字や記号だけでなく、文字を使って反省文を書いてください。"
            
            # 適切な文章構造チェック
            sentences = re.split(r'[。！？]', text)
            meaningful_sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
            if len(meaningful_sentences) < 2:
                return False, "❌ 最低でも2つの文章（。！？で区切られた）で反省文を書いてください。"
            
            # キーボード配列チェック（qwerty、asdf等の連続）
            keyboard_patterns = [
                'qwertyuiop', 'asdfghjkl', 'zxcvbnm',
                'あいうえお', 'かきくけこ', 'さしすせそ',
                '12345', '67890'
            ]
            text_lower = text.lower()
            for pattern in keyboard_patterns:
                if pattern in text_lower:
                    return False, f"❌ キーボード配列の文字列「{pattern}」は使用できません。"
            
            # 単語の多様性チェック（同じ単語が文字数の30%以上を占める）
            words = re.findall(r'[ぁ-んァ-ヶ一-龯a-zA-Z]+', text)
            if words:
                most_common_word = max(set(words), key=words.count)
                if words.count(most_common_word) * len(most_common_word) > len(text) * 0.3:
                    return False, f"❌ 同じ単語「{most_common_word}」の使用が多すぎます。"
            
            # 禁止フレーズチェック
            prohibited_phrases = [
                'てすと', 'テスト', 'test', 'TEST',
                'ああああ', 'いいいい', 'ううううう',
                'わからない', 'しらない', 'べつに',
                'めんどくさい', 'だるい', 'やる気ない'
            ]
            text_lower = text.lower()
            for phrase in prohibited_phrases:
                if phrase in text_lower:
                    return False, f"❌ 不適切な表現「{phrase}」が含まれています。真摯な反省文を書いてください。"
            
            # 最小限の敬語・丁寧語チェック
            polite_expressions = ['ます', 'です', 'である', 'だ', 'した', 'しました', 'ません', 'でした']
            has_polite = any(expr in text for expr in polite_expressions)
            if not has_polite:
                return False, "❌ 丁寧語（です・ます調）で反省文を書いてください。"
            
            return True, "✅ 適切な反省文です。"

        async def on_submit(interaction, value, recipient, view):
            # 反省文の品質チェック
            is_valid, message = await validate_hansei_text(value)
            if not is_valid:
                error_embed = discord.Embed(
                    title="❌ 反省文提出エラー",
                    description=message,
                    color=0xE74C3C,
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                error_embed.add_field(
                    name="📝 改善してください",
                    value="• 真摯な気持ちで反省文を書く\n• 同じ文字や単語の繰り返しを避ける\n• 丁寧語（です・ます調）を使用する\n• 最低2文以上で構成する",
                    inline=False
                )
                error_embed.set_footer(text="再度ボタンを押して正しい反省文を提出してください")
                await interaction.response.send_message(embed=error_embed, ephemeral=True)
                return
            
            guild_id = ctx.guild.id
            user_id = member.id
            expire = until.isoformat()
            data = get_guild_data(guild_id)
            hansei = data.get("hansei_reports", {})
            hansei[str(user_id)] = {"text": value, "expire": expire, "user_name": member.display_name}
            data["hansei_reports"] = hansei
            update_guild_data(guild_id, "hansei_reports", hansei)
            # 反省文提出後、ボタンを無効化
            if view is not None:
                for item in view.children:
                    item.disabled = True
                view.stop()
                await interaction.message.edit(view=view)
            
            # 提出成功のEmbed
            success_embed = discord.Embed(
                title="✅ 反省文提出完了",
                description="反省文が正常に提出されました。",
                color=0x2ECC71,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            success_embed.add_field(
                name="📝 提出内容",
                value=f"```\n{value[:100]}{'...' if len(value) > 100 else ''}\n```",
                inline=False
            )
            success_embed.add_field(
                name="👥 確認状況",
                value="スタッフが確認中です。しばらくお待ちください。",
                inline=False
            )
            success_embed.add_field(
                name="⏰ タイムアウト解除予定",
                value=f"<t:{int(until.timestamp())}:F>まで\n（スタッフ承認により早期解除の可能性あり）",
                inline=False
            )
            success_embed.set_footer(
                text=f"{ctx.guild.name} タイムアウトシステム",
                icon_url=ctx.guild.icon.url if ctx.guild.icon else None
            )
            await interaction.response.send_message(embed=success_embed, ephemeral=True)

        view = ModalInputView(
            label="反省文を提出する",
            modal_title="反省文提出フォーム",
            placeholder="100文字以上400文字以内で反省文を入力してください",
            text_label="反省文",
            input_style="paragraph",
            min_length=100,
            max_length=400,
            ephemeral=True,
            allowed_user_id=member.id,
            on_submit=on_submit
        )
        
        # DM用のEmbed作成
        dm_embed = discord.Embed(
            title="⚠️ タイムアウト通知",
            description=f"**{ctx.guild.name}** サーバーでタイムアウトが付与されました。",
            color=0xFF6B6B,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        dm_embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else "https://cdn.discordapp.com/embed/avatars/0.png")
        dm_embed.add_field(
            name="🕒 タイムアウト期間", 
            value=f"{seconds}秒間", 
            inline=True
        )
        dm_embed.add_field(
            name="⏰ 解除予定時刻", 
            value=f"<t:{int(until.timestamp())}:F>", 
            inline=True
        )
        dm_embed.add_field(
            name="📅 解除まで", 
            value=f"<t:{int(until.timestamp())}:R>", 
            inline=True
        )
        if reason:
            dm_embed.add_field(
                name="📝 理由", 
                value=f"```\n{reason}\n```", 
                inline=False
            )
        dm_embed.add_field(
            name="📋 解除方法",
            value="下のボタンから **反省文** を提出してください。\nスタッフが確認後、タイムアウトが解除されます。",
            inline=False
        )
        dm_embed.set_footer(
            text=f"実行者: {ctx.author.display_name} | {ctx.guild.name}",
            icon_url=ctx.author.display_avatar.url
        )
        
        try:
            await member.send(embed=dm_embed, view=view)
        except Exception:
            # DM送信失敗時の詳細な案内
            fail_embed = discord.Embed(
                title="❌ DM送信失敗",
                description=f"{member.mention} にDMを送信できませんでした。",
                color=0xE74C3C
            )
            fail_embed.add_field(
                name="🔧 対処方法",
                value="• DMを有効にしてもらう\n• サーバー内で直接案内する\n• 管理者に相談する",
                inline=False
            )
            fail_embed.add_field(
                name="📋 手動案内用メッセージ",
                value=f"**タイムアウト解除には反省文の提出が必要です**\n期間: {seconds}秒\n解除予定: <t:{int(until.timestamp())}:F>",
                inline=False
            )
            await ctx.send(embed=fail_embed)
    except Exception as e:
        error_message = f"{member.mention} へのタイムアウト付与に失敗しました。"
        if (
            hasattr(member, "guild_permissions")
            and member.guild_permissions.administrator
        ):
            error_message += ("\n⚠️ 管理者権限を持つメンバーはタイムアウトできません。")
        elif hasattr(ctx.guild, "owner") and member.id == ctx.guild.owner.id:
            error_message += "\n⚠️ サーバーオーナーはタイムアウトできません。"
        elif hasattr(ctx.guild, "me") and member.top_role >= ctx.guild.me.top_role:
            error_message += ("\n⚠️ Botより上位のロールを持つメンバーはタイムアウトできません。")
        else:
            error_message += f"\nエラー詳細: {str(e)}"
        await ctx.send(error_message)
