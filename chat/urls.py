from django.urls import path

from . import views


app_name = "chat"
urlpatterns = [
    path("", views.home, name="home"),
    path("simgen/", views.simgen_placeholder, name="simgen"),
    path("profile/", views.profile, name="profile"),
    path("profile/prompt/", views.save_global_prompt, name="save-global-prompt"),
    path("profile/memories/toggle/", views.toggle_ai_memories, name="toggle-memories"),
    path("profile/memories/add/", views.add_memory_item, name="add-memory"),
    path(
        "profile/memories/<int:memory_id>/delete/",
        views.delete_memory_item,
        name="delete-memory",
    ),
    path("billing/top-up/", views.mock_top_up, name="mock-top-up"),
    path("sessions/new/modal/", views.model_selector, name="model-selector"),
    path("sessions/new/modal/close/", views.close_model_selector, name="close-model-selector"),
    path("sessions/create/", views.create_session, name="create-session"),
    path(
        "api/chat/sessions/<int:session_id>/completions/",
        views.stream_chat_completion,
        name="stream-completion",
    ),
    path("sessions/<int:session_id>/", views.session_detail, name="session-detail"),
]
