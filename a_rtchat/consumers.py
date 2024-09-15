from channels.generic.websocket import WebsocketConsumer
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from asgiref.sync import async_to_sync  # Преобразует асинхронные функции в синхронные (для работы с синхронным WebSocketConsumer)
import json
from .models import *  # Импортируем модели (ChatGroup, GroupMessage и т.д.)

class ChatroomConsumer(WebsocketConsumer):
    def connect(self):
        """
        Метод вызывается, когда клиент подключается к WebSocket.
        Здесь подключаем пользователя к нужной группе чата и принимаем WebSocket соединение.
        """
        # Получаем пользователя из текущего WebSocket соединения (scope содержит информацию о запросе, в том числе пользователя)
        self.user = self.scope['user']
        
        # Извлекаем имя комнаты (чата) из параметров URL 
        self.chatroom_name = self.scope['url_route']['kwargs']['chatroom_name']
        
        # Пытаемся найти комнату (чат) по её имени в базе данных. Если не находим — выбрасывается 404 ошибка.
        self.chatroom = get_object_or_404(ChatGroup, group_name=self.chatroom_name)
        
        # Добавляем текущее WebSocket-соединение в группу, связанную с чатом (через канал)
        # group_add добавляет канал пользователя в группу сообщений для конкретного чата
        async_to_sync(self.channel_layer.group_add)(
            self.chatroom_name,  # Имя группы (соответствует имени комнаты)
            self.channel_name    # Уникальное имя канала текущего WebSocket-соединения
        )
        
        # Логика для обработки онлайн-пользователей.
        # Проверяем, если текущего пользователя нет в списке пользователей, которые находятся онлайн, добавляем его.
        if self.user not in self.chatroom.users_online.all():
            self.chatroom.users_online.add(self.user) # это добавление в бд
            self.update_online_count()
        
        self.accept()

    def disconnect(self, close_code):
        """
        Метод вызывается, когда клиент отключается от WebSocket.
        Здесь удаляем пользователя из группы чата.
        """
        # Удаляем текущее WebSocket-соединение из группы чата
        async_to_sync(self.channel_layer.group_discard)(
            self.chatroom_name,
            self.channel_name  
        )
        
        # Убираем пользователя из списка онлайн-пользователей, если он есть.
        if self.user in self.chatroom.users_online.all():
            self.chatroom.users_online.remove(self.user)
            self.update_online_count()
    
    def receive(self, text_data):
        """
        Метод вызывается, когда клиент отправляет сообщение на сервер по WebSocket.
        Здесь обрабатываем полученные данные, сохраняем сообщение в базу данных и уведомляем всех пользователей чата.
        """
        # Преобразуем строку, переданную по WebSocket, из JSON-формата в Python-словарь
        text_data_json = json.loads(text_data)
        
        # Извлекаем тело сообщения (текст) из полученных данных
        body = text_data_json['body']
        
        # Сохраняем сообщение в базе данных с привязкой к пользователю и чату
        message = GroupMessage.objects.create(
            body=body,          # Текст сообщения
            author=self.user,   # Автор сообщения (текущий пользователь)
            group=self.chatroom # Чат (группа), в который отправляется сообщение
        )
        
        # Формируем событие для отправки в группу (уведомляем всех участников чата)
        event = {
            'type': 'message_handler',  # Указываем, какой метод будет обработчиком этого события (message_handler)
            'message_id': message.id,   # Передаем ID сообщения, чтобы потом его можно было извлечь из базы
        }
        
        # Отправляем событие в группу WebSocket (все подключённые пользователи этой группы получат его)
        async_to_sync(self.channel_layer.group_send)(
            self.chatroom_name,  # Имя группы, в которую отправляем событие (соответствует чату)
            event                # Событие, которое будет обработано (в данном случае это отправка нового сообщения)
        )

    def message_handler(self, event):
        """
        Этот метод вызывается, когда сообщение отправляется в группу WebSocket (событие 'message_handler').
        Здесь извлекаем сообщение из базы данных, рендерим его в HTML и отправляем клиенту.
        """
        # Извлекаем ID сообщения из события
        message_id = event['message_id']
        
        # Получаем сообщение из базы данных по его ID
        message = GroupMessage.objects.get(id=message_id)
        
        # Формируем контекст для рендеринга HTML-шаблона
        context = {
            'message': message,  # Само сообщение
            'user': self.user,   # Текущий пользователь
        }
        
        # Рендерим шаблон, чтобы преобразовать сообщение в HTML-формат (например, для вставки в чат)
        html = render_to_string("a_rtchat/partials/chat_message_p.html", context=context)
        
        # Отправляем сгенерированный HTML клиенту через WebSocket
        self.send(text_data=html)
    
    def update_online_count(self):
        """
        Этот метод обновляет количество онлайн-пользователей в чате и отправляет обновленное значение всем участникам.
        """
        online_count = self.chatroom.users_online.count() - 1
        
        event = {
            'type': 'online_count_handler',
            'online_count': online_count
        }
        
        # Отправляем событие в группу WebSocket (все подключённые пользователи чата получат это событие).
        async_to_sync(self.channel_layer.group_send)(self.chatroom_name, event)
        
    def online_count_handler(self, event):
        """
        Этот метод обрабатывает событие обновления числа онлайн-пользователей.
        Здесь мы рендерим HTML для обновленного значения и отправляем его клиенту.
        """
        online_count = event['online_count']
        
        html = render_to_string("a_rtchat/partials/online_count.html", {'online_count': online_count})
        
        self.send(text_data=html)