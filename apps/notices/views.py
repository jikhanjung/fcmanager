from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from .forms import NoticeForm
from .models import Notice

staff_required = user_passes_test(lambda u: u.is_staff, login_url="login")


def notice_list(request):
    # 현재 클럽 한정. 운영진은 미게시 공지도 함께 본다(관리용).
    notices = Notice.objects.filter(club=request.club)
    if not request.user.is_staff:
        notices = notices.filter(is_published=True)
    return render(request, "notices/notice_list.html", {"notices": notices})


def notice_detail(request, pk):
    notice = get_object_or_404(Notice, pk=pk, club=request.club)
    if not notice.is_published and not request.user.is_staff:
        raise Http404()
    return render(request, "notices/notice_detail.html", {"notice": notice})


@staff_required
def notice_create(request):
    if request.method == "POST":
        form = NoticeForm(request.POST)
        if form.is_valid():
            notice = form.save(commit=False)
            notice.club = request.club
            notice.save()
            messages.success(request, "공지사항을 등록했습니다.")
            return redirect(notice.get_absolute_url())
    else:
        form = NoticeForm()
    return render(request, "notices/notice_form.html", {"form": form, "is_create": True})


@staff_required
def notice_edit(request, pk):
    notice = get_object_or_404(Notice, pk=pk, club=request.club)
    if request.method == "POST":
        form = NoticeForm(request.POST, instance=notice)
        if form.is_valid():
            form.save()
            messages.success(request, "공지사항을 저장했습니다.")
            return redirect(notice.get_absolute_url())
    else:
        form = NoticeForm(instance=notice)
    return render(request, "notices/notice_form.html",
                  {"form": form, "notice": notice, "is_create": False})


@staff_required
def notice_delete(request, pk):
    notice = get_object_or_404(Notice, pk=pk, club=request.club)
    if request.method == "POST":
        notice.delete()
        messages.success(request, "공지사항을 삭제했습니다.")
        return redirect("notices:list")
    return render(request, "notices/notice_confirm_delete.html", {"notice": notice})
