from django.urls import path

from .views import ChatPage, ConversationView

app_name = "assistant"
urlpatterns = [
    path("chat/", ChatPage.as_view(), name="chat"),
    path("api/chat/", ConversationView.as_view(), name="conversation"),
]
