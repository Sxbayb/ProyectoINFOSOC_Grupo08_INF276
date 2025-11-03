from django.urls import path
from . import views

urlpatterns = [
    # Esta es la nueva página principal (el menú)
    path('', views.vista_principal, name='vista_principal'),
    
    # Las 3 páginas de la aplicación
    path('agendar/', views.vista_agendamiento, name='vista_agendamiento'),
    path('consejos/', views.vista_consejos, name='vista_consejos'),
    path('resultados/', views.vista_resultados, name='vista_resultados'),
]
