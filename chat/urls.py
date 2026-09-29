from django.urls import path

from .views import stream_chat_completion


app_name = "chat"
urlpatterns = [
    path(
        "sessions/<int:session_id>/completions/",
        stream_chat_completion,
        name="stream-completion",
    ),
]
