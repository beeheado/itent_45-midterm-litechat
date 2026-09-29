import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse


@pytest.mark.django_db
def test_nested_page_uses_root_static_urls_and_loads_frontend_cdns(client):
    user = get_user_model().objects.create_user(username="static-assets-user")
    client.force_login(user)

    response = client.get(reverse("chat:profile"))

    assert response.status_code == 200
    assert b'href="/static/chat/css/app.css"' in response.content
    assert b'src="/static/chat/js/app.js"' in response.content
    assert b"bg-slate-900 text-slate-200 antialiased" in response.content
    assert b"rounded-xl border border-slate-700 bg-slate-800" in response.content
    assert b"https://cdn.tailwindcss.com" in response.content
    assert b"marked@15.0.12/marked.min.js" in response.content
    assert b"highlight.js@11.11.1/styles/github-dark.min.css" in response.content
    assert b"highlight.js@11.11.1/lib/common.min.js" in response.content
    assert b"dompurify@3.2.6/dist/purify.min.js" in response.content
    assert b"htmx.org@2.0.8/dist/htmx.min.js" in response.content
