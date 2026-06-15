"""KFA 참가신청 페이지(matchApplyTeam.html)에서 선수 사진을 일괄 반영하는 명령.

저장된 웹페이지의 카드 구조(<img src="...사진_xxx.jpg"> + <h4>이름　No.번호</h4>)를
파싱해 이름으로 선수를 찾아 Player.photo 에 사진을 저장한다. 멱등.

사용 예:
    python manage.py import_player_photos \\
        /tmp/sky/sky_files/matchApplyTeam.html /tmp/sky/sky_files \\
        --team sky-k7 [--overwrite]
"""
import html as html_mod
import os
import re

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from apps.teams.models import Player

# 카드 1개에서 (사진경로, 제목="이름　No.n") 추출
CARD_RE = re.compile(r'<img[^>]*src="([^"]+)"[^>]*>.*?<h4[^>]*>(.*?)</h4>', re.S)
PHOTO_PREFIXES = ("사진_", "선수사진_")


class Command(BaseCommand):
    help = "저장된 KFA 페이지에서 선수 사진을 파싱해 Player.photo 에 일괄 반영한다."

    def add_arguments(self, parser):
        parser.add_argument("html_path", help="matchApplyTeam.html 경로")
        parser.add_argument("images_dir", help="사진 파일들이 있는 디렉터리(sky_files)")
        parser.add_argument("--team", help="이 팀(slug) 소속 선수만 매칭")
        parser.add_argument("--overwrite", action="store_true",
                            help="이미 사진이 있어도 덮어쓰기")
        parser.add_argument("--dry-run", action="store_true",
                            help="저장 없이 매칭 결과만 출력")

    def handle(self, *args, **opts):
        if not os.path.exists(opts["html_path"]):
            raise CommandError(f"HTML 없음: {opts['html_path']}")
        cards = self._parse(opts["html_path"])

        players = Player.objects.all()
        if opts["team"]:
            players = players.filter(memberships__team__slug=opts["team"]).distinct()
        by_name = {p.name: p for p in players}

        saved = skipped = nomatch = nofile = 0
        for src, name in cards:
            if not src.startswith(PHOTO_PREFIXES):
                continue  # 기본 아이콘/템플릿 노이즈
            path = os.path.join(opts["images_dir"], src)
            if not os.path.exists(path):
                nofile += 1
                continue
            player = by_name.get(name) or by_name.get(self._strip_suffix(name))
            if not player:
                nomatch += 1
                self.stdout.write(f"  매칭실패: {name} ({src})")
                continue
            if player.photo and not opts["overwrite"]:
                skipped += 1
                continue
            if not opts["dry_run"]:
                ext = os.path.splitext(src)[1].lower()
                with open(path, "rb") as fh:
                    player.photo.save(f"{player.pk}{ext}", File(fh), save=True)
            saved += 1
            self.stdout.write(f"  ✓ {player.name} ← {src}")

        mode = " (DRY-RUN)" if opts["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(
            f"완료{mode}: 저장 {saved} · 건너뜀(이미있음) {skipped} · "
            f"매칭실패 {nomatch} · 파일없음 {nofile}"
        ))

    def _parse(self, path):
        s = open(path, encoding="utf-8").read()
        out = []
        for src, title in CARD_RE.findall(s):
            title = html_mod.unescape(title)
            name = re.split(r"[　\s]*No\.", title)[0].strip()
            src = html_mod.unescape(src).replace("./", "").lstrip("/")
            src = os.path.basename(src)
            out.append((src, name))
        return out

    @staticmethod
    def _strip_suffix(name):
        """KFA 동명이인 접미 숫자 제거 (예: 이상호1 → 이상호)."""
        return re.sub(r"\d+$", "", name).strip()
