from django.contrib import admin
from .models import BloqueHorario, Reserva

# Opcional, pero muy recomendado para una mejor vista:
class ReservaAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'bloque', 'usuario') # Columnas que se verán en la lista
    list_filter = ('fecha', 'bloque')           # Filtros en la barra lateral
    search_fields = ('usuario__username', 'bloque__nombre') # Barra de búsqueda
    date_hierarchy = 'fecha'                    # Navegación por fechas

# Registra tus modelos en el admin
admin.site.register(BloqueHorario)
admin.site.register(Reserva, ReservaAdmin) # Registra Reservas usando la vista personalizada
