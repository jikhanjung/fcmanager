from django.shortcuts import get_object_or_404, render

from .models import Notice


def notice_list(request):
    notices = Notice.objects.filter(is_published=True)
    return render(request, "notices/notice_list.html", {"notices": notices})


def notice_detail(request, pk):
    notice = get_object_or_404(Notice, pk=pk, is_published=True)
    return render(request, "notices/notice_detail.html", {"notice": notice})
