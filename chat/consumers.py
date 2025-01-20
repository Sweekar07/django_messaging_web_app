import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from .models import ChatMessage
import logging
from datetime import datetime

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Function to convert datetime to ISO 8601 string
def datetime_to_iso(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        # self.room_group_name = f'chat_{self.room_name}'
        self.room_group_name = f'chat_{min(self.scope["user"].username, self.room_name)}_{max(self.scope["user"].username, self.room_name)}'
        print("room name:", self.room_group_name)


        # Log the connection attempt
        logger.info(f"WebSocket connection attempt for room: {self.room_name}")
        print(f"WebSocket connection attempt for room: {self.room_name}")

        try:
            # Join the room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            # Accept the WebSocket connection
            await self.accept()
            logger.info(f"WebSocket connection accepted for room: {self.room_name}")

            # Fetch and send undelivered messages to the current user
            username = self.scope["user"].username
            undelivered_messages = await self.get_undelivered_messages(username)

            for msg in undelivered_messages:
                await self.send(text_data=json.dumps({
                    'message': msg['message'],
                    # 'sender': msg['sender'],
                    'sender': msg['sender__username'],  # Fix for nested sender username key
                    'timestamp': msg['timestamp'].isoformat()
                }))

                # Mark message as read after sending
                await self.mark_message_as_read(msg['id'])

            logger.info(f"WebSocket connection established for room: {self.room_name}")

        except Exception as e:
            logger.error(f"Error in WebSocket connection: {str(e)}")
            await self.close()


    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action')

        if action == 'load_messages':
            logged_in_user = self.scope["user"].username
            selected_user = data.get('selected_user')

            if selected_user:
                old_messages = await self.get_old_messages(logged_in_user, selected_user)
                json_serializable_messages = json.dumps(old_messages, default=datetime_to_iso)
                # Send old messages to the frontend
                await self.send(text_data=json.dumps({
                    'action': 'load_messages',
                    'messages': json.loads(json_serializable_messages)
                }))
        elif action == 'send_message':
            # Handle sending a new message
            message = data['message']
            sender = data['sender']
            receiver = data['receiver']
            
            await self.save_message(sender, receiver, message)
            
            # Notify the group about the new message
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'sender': sender
                }
            )


    async def chat_message(self, event):
        message = event['message']
        sender = event['sender']

        await self.send(text_data=json.dumps({
            'message': message,
            'sender': sender
        }))

    @database_sync_to_async
    def save_message(self, sender, receiver, message):
        try:
            sender_user = User.objects.get(username=sender)
            receiver_user = User.objects.get(username=receiver)
            ChatMessage.objects.create(sender=sender_user, receiver=receiver_user, message=message)
            logger.info(f"Message saved from {sender} to {receiver}: {message}")
        except Exception as e:
            logger.error(f"Error saving message to database: {str(e)}")

    @database_sync_to_async
    def get_old_messages(self, logged_in_user, selected_user):
        """Fetch all messages exchanged between the logged-in user and the selected user."""
        return list(ChatMessage.objects.filter(
            sender__username__in=[logged_in_user, selected_user],
            receiver__username__in=[logged_in_user, selected_user]
        ).order_by('timestamp').values('message', 'sender__username', 'timestamp'))
        
    @database_sync_to_async
    def mark_message_as_read(self, message_id):
        """Mark a message as read."""
        ChatMessage.objects.filter(id=message_id).update(is_read=True)

    @database_sync_to_async
    def get_undelivered_messages(self, username):
        """Fetch messages sent to the user that haven't been read yet."""
        return list(ChatMessage.objects.filter(
            receiver__username=username,
            is_read=False
        ).values('id', 'message', 'sender__username', 'timestamp'))
