import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse


@pytest.mark.django_db
def test_anonymous_home_redirects_to_working_login_page(client):
    response = client.get(reverse("chat:home"))

    assert response.status_code == 302
    assert response.url == "/accounts/login/?next=/"

    login_response = client.get(response.url)
    assert login_response.status_code == 200
    assert b"Welcome back." in login_response.content
    assert b'name="csrfmiddlewaretoken"' in login_response.content


@pytest.mark.django_db
def test_login_authenticates_demo_user_and_honors_next(client):
    user_model = get_user_model()
    user_model.objects.create_user(username="login-test", password="test-password")
    next_url = reverse("chat:profile")

    response = client.post(
        reverse("login"),
        {
            "username": "login-test",
            "password": "test-password",
            "next": next_url,
        },
    )

    assert response.status_code == 302
    assert response.url == next_url
    assert client.get(next_url).status_code == 200


@pytest.mark.django_db
def test_direct_login_uses_home_as_default_redirect(client):
    get_user_model().objects.create_user(username="direct-login", password="test-password")

    response = client.post(
        reverse("login"),
        {"username": "direct-login", "password": "test-password"},
    )

    assert response.status_code == 302
    assert response.url == "/"
