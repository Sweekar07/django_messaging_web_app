from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib.auth.models import User
from .models import ChatMessage

# Create your views here.
@login_required
def chat_view(request):
    if not request.user.is_authenticated:
        return redirect('chat:login')
    users = User.objects.exclude(username=request.user.username)
    return render(request, 'chat/chat.html', {'users': users})

def register_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('chat:chat')
    else:
        form = UserCreationForm()
    return render(request, 'chat/register.html', {'form': form})
