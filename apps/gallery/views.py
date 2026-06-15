from django.shortcuts import render

from .models import GalleryItem


def gallery_list(request):
    items = GalleryItem.objects.filter(is_published=True)
    return render(request, "gallery/gallery_list.html", {"items": items})
