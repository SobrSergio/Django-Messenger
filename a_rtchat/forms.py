from django.forms import ModelForm
from django import forms
from .models import *


class ChatmessageCreateForm(ModelForm):
    class Meta:
        model = GroupMessage
        fields = ('body', )
        widgets = {
            'body' : forms.TextInput(attrs={'placeholder' : 'Напишите сообщение...', 'class': 'p-4 text-black', 'maxlengh': '300', 'autofocus': True}),
        } #autofocus - при заходе на страницу автомотически выбирается пользователем, как поля для ввода.