# scripts 를 패키지로 둬서 `manage.py test` 의 unittest 디스커버리가 test_backup_db.py 를
# 찾을 수 있게 한다(Python 3.11+ 는 네임스페이스 패키지를 디스커버리하지 않는다).
# 런타임 앱 코드는 여기 두지 않는다 — 운영 호스트에서 cron 이 직접 실행하는 스크립트 모음.
