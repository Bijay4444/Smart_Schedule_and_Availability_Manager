"""Authenticated HTTP boundary. Schedule interpretation lives in services."""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.views.generic import TemplateView
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from . import services
from .provider import AssistantUnavailable

HISTORY_KEY = "schedule_chat"


class ChatPage(LoginRequiredMixin, TemplateView):
    template_name = "assistant/chat.html"


class MessageSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=2000, trim_whitespace=True)


class ChatThrottle(UserRateThrottle):
    rate = "10/min"
    scope = "schedule_chat"


class ConversationView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [ChatThrottle]

    def get(self, request):
        return Response({"messages": request.session.get(HISTORY_KEY, [])})

    def post(self, request):
        serializer = MessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.change(request, serializer.validated_data["message"])

    def delete(self, request):
        return self.change(request, None)

    def change(self, request, message):
        # LocMemCache serializes concurrent requests within the demo's single process.
        key = f"schedule-chat-busy:{request.user.pk}"
        if not cache.add(key, True, timeout=90):
            return Response({"detail": "A chat request is already running. Wait a moment and try again."}, status=409)
        try:
            if message is None:
                request.session.pop(HISTORY_KEY, None)
                return Response({"messages": []})
            history = request.session.get(HISTORY_KEY, [])
            try:
                content = services.answer(owner=request.user, history=history, message=message)
            except AssistantUnavailable as error:
                return Response({"detail": str(error)}, status=503)
            history = [*history, {"role": "user", "content": message}, {"role": "assistant", "content": content}][-12:]
            request.session[HISTORY_KEY] = history
            # Save before releasing the busy key so another tab can read this turn.
            request.session.save()
            return Response({"messages": history})
        finally:
            cache.delete(key)
